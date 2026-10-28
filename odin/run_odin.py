"""ODIN's start command: run ODIN as its own process for one run.

    python -m odin.run_odin <spark|spark_open|glimmer_local|stand_in>

Reads the harness, BALDUR-0 and log addresses from config/ports.yaml and
runs the turn loop until the harness says the run is complete. The adapter
is built with build_adapter from config/models.yaml; no command-line
option, flag or environment variable can change its endpoint (tests may
inject a fake transport into main()/build_run_adapter() in code, never
through the command line). Before anything else, every ODIN_COSMOS_*
variable is removed from this process's environment (U38): ODIN never
holds COSMOS's credentials. API keys come only from META_API_KEY and
BASETEN_API_KEY; the signing key only from ODIN_KEY_PATH.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS = ("spark", "spark_open", "glimmer_local", "stand_in")
KEY_FOR_MODEL = {"spark": "META_API_KEY", "spark_open": "BASETEN_API_KEY"}


def strip_cosmos_env(env=None) -> None:
    """U38: ODIN never holds COSMOS's credentials. Runs before anything."""
    env = os.environ if env is None else env
    for name in [n for n in env if n.startswith("ODIN_COSMOS_")]:
        del env[name]


def verify_frozen(repo_root) -> bool:
    """Refuse to start if the frozen instructions or prompt.py differ."""
    repo_root = Path(repo_root)
    record_path = repo_root / "odin" / "instructions" / "system_prompt.sha256.json"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    def digest(path):
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

    try:
        return (
            digest(repo_root / "odin" / "instructions" / "system_prompt.md")
            == record["sha256"]
            and digest(repo_root / "odin" / "loop" / "prompt.py")
            == record["prompt_template_sha256"]
        )
    except Exception:
        return False


def stand_in_answer(turn_id, bundle):
    """The start command's stand-in: none on an ACT turn; on a REPORT turn,
    a minimal valid report of the form that turn asks for."""
    if bundle.get("turn_kind") == "REPORT":
        body = {
            "timeline": [],
            "actions": [],
            "condition": {"summary": "Stand-in report: nothing to report.",
                          "evidence": []},
            "deferred": [],
            "open_issues": [],
        }
        if bundle.get("report_kind") == "CHECK_IN":
            body["answer"] = "Stand-in: no comment."
        return json.dumps(body)
    return '{"kind":"none"}'


def build_run_adapter(model, http_post=None):
    """The adapter exactly as config/models.yaml builds it (U57). No
    endpoint override exists here: build_adapter is never given one."""
    from odin.adapters.settings import build_adapter
    from odin.adapters.stand_in import StandInAdapter

    if model == "stand_in":
        return StandInAdapter(script=stand_in_answer)
    return build_adapter(model, http_post=http_post)


def _service_urls(repo_root):
    config = yaml.safe_load(
        (Path(repo_root) / "config" / "ports.yaml").read_text(encoding="utf-8"))
    host, ports = config["host"], config["ports"]
    return (f"http://{host}:{ports['harness']}",
            f"http://{host}:{ports['baldur0']}",
            f"http://{host}:{ports['log']}")


def main(argv=None, *, transport=None, repo_root=None, private_key_path=None,
         urls=None, http_post=None, adapter_factory=None, max_turns=None) -> int:
    strip_cosmos_env()  # before anything else (U38)
    repo_root = Path(repo_root or REPO_ROOT)
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m odin.run_odin "
              "<spark|spark_open|glimmer_local|stand_in>")
        return 2
    model = argv[0]
    if model not in MODELS:
        print(f"unknown model {model!r}: choose one of {', '.join(MODELS)}")
        return 2
    if not verify_frozen(repo_root):
        print("refusing to start: odin/instructions/system_prompt.md or "
              "odin/loop/prompt.py differs from the frozen record")
        return 2
    key_var = KEY_FOR_MODEL.get(model)
    if key_var and not os.environ.get(key_var):
        print(f"refusing to start: {key_var} is not set")
        return 2
    if not os.environ.get("ODIN_KEY_PATH"):
        print("refusing to start: ODIN_KEY_PATH is not set")
        return 2
    try:
        adapter = (adapter_factory(model) if adapter_factory is not None
                   else build_run_adapter(model, http_post=http_post))
    except (RuntimeError, ValueError) as exc:
        print(f"refusing to start: {exc}")
        return 2

    from odin.loop.loop import TurnLoop
    from odin.spend.meter import SpendMeter

    harness_url, baldur_url, log_url = urls or _service_urls(repo_root)
    instructions = (repo_root / "odin" / "instructions" / "system_prompt.md") \
        .read_text(encoding="utf-8")

    def submit(record_type, body):
        from odin.loop.loop import _http_json

        _http_json("POST", f"{log_url}/log/agent",
                   {"type": record_type, "body": body}, transport=transport)

    meter = SpendMeter(
        ledger_path=repo_root / "runs" / "spend.jsonl",
        prices_path=repo_root / "config" / "prices.yaml", submit=submit)
    loop = TurnLoop(
        harness_url=harness_url, baldur_url=baldur_url, log_url=log_url,
        adapter=adapter, repo_root=repo_root, transport=transport,
        private_key_path=private_key_path, instructions=instructions,
        meter=meter)
    try:
        results = loop.run(max_turns=max_turns)  # no cap unless a test sets one
    except (ConnectionError, OSError) as exc:
        print(f"harness unreachable: {exc}")
        return 3
    if any(r["outcome"] == "spend_stop" for r in results):
        print("stopped: spend stop reached; ODIN sends nothing more (exit 4)")
        return 4
    if not loop.run_completed:
        print("stopped before run_complete: the run did not finish (exit 5)")
        return 5
    print(f"run complete: {len(results)} turn(s), model {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
