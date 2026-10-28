"""M3: one real check and the reasoning measurement (AGENTS §7, M3).

Part 1 sends one short spark call (reasoning low) through the whole loop
against the fake harness, fake BALDUR-0 and fake log. Part 2 sends one
fixed small ACT bundle once through spark and once through spark_open at
each configured reasoning level. Every call is metered (reserve first,
actual after) with a MODEL_CALL record; one attempt per call, no retries.

    python -m odin.devtools.m3_check --dry-run   # no network, lists the plan
    python -m odin.devtools.m3_check             # the real run (Director only)

Never run the real run without the Director: it makes paid calls.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = Path(__file__).resolve().parent / "m3_settings.yaml"
REQUIRED_ENV = ["META_API_KEY", "BASETEN_API_KEY", "ODIN_KEY_PATH"]

sys.path.insert(0, str(REPO_ROOT))

from odin.adapters.openai_compat import ProviderError, estimate_tokens  # noqa: E402
from odin.adapters.spark import SparkAdapter  # noqa: E402
from odin.adapters.spark_open import SparkOpenAdapter, convert_tool_calls  # noqa: E402
from odin.devtools.fake_harness import FakeServices  # noqa: E402
from odin.devtools.fixtures import bundle_bytes, make_m3_bundle  # noqa: E402
from odin.loop.loop import TurnLoop  # noqa: E402
from odin.loop.prompt import build_prompt  # noqa: E402
from odin.loop.validate import validate_act_text  # noqa: E402
from odin.spend.meter import SpendMeter  # noqa: E402

ADAPTERS = {"spark": SparkAdapter, "spark_open": SparkOpenAdapter}


def load_settings(settings_path=None):
    return yaml.safe_load(Path(settings_path or SETTINGS_PATH).read_text(encoding="utf-8"))


def planned_calls(settings=None):
    settings = settings or load_settings()
    cap, timeout = settings["output_tokens"], settings["timeout_s"]
    plan = [{"part": 1, "config": "spark", "reasoning_effort": "low",
             "endpoint": SparkAdapter.endpoint, "model_id": SparkAdapter.model_id,
             "max_output_tokens": cap, "timeout_s": timeout}]
    for config in ("spark", "spark_open"):
        cls = ADAPTERS[config]
        for level in settings["levels"][config]:
            plan.append({"part": 2, "config": config, "reasoning_effort": level,
                         "endpoint": cls.endpoint, "model_id": cls.model_id,
                         "max_output_tokens": cap, "timeout_s": timeout})
    return plan


def _instructions():
    path = REPO_ROOT / "odin" / "instructions" / "system_prompt.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _check_keys(env):
    missing = [name for name in REQUIRED_ENV if not env.get(name)]
    if missing:
        raise RuntimeError("missing required environment: " + ", ".join(missing))


def run_check(*, repo_root, env=None, http_post=None, odin_public_key_path=None,
              dry_run=False, settings_path=None):
    env = dict(os.environ if env is None else env)
    repo_root = Path(repo_root)
    settings = load_settings(settings_path)
    bundle = make_m3_bundle()
    prompt = build_prompt(bundle, _instructions())
    meter = SpendMeter(ledger_path=repo_root / "runs" / "_m3_spend_tmp.jsonl",
                       prices_path=REPO_ROOT / "config" / "prices.yaml")
    plan = []
    for entry in planned_calls(settings):
        reserved = meter.worst_case(entry["config"], estimate_tokens(prompt),
                                    entry["max_output_tokens"])
        plan.append({**entry, "reserved_usd": reserved})
    total = sum(entry["reserved_usd"] for entry in plan)
    if dry_run:
        return {"planned": plan, "rows": [], "total_reserved_usd": total}

    _check_keys(env)  # stops before any call; names only, never values
    date = datetime.now(timezone.utc).date().isoformat()
    out_dir = repo_root / "runs" / f"m3-{date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    meter = SpendMeter(ledger_path=out_dir / "spend.jsonl",
                       prices_path=REPO_ROOT / "config" / "prices.yaml")

    services = FakeServices(
        bundles=[bundle_bytes(bundle)],
        public_key_path=odin_public_key_path or (REPO_ROOT / "keys" / "odin.pub"))

    def submit(record_type, body):
        status, raw = services.transport(
            "POST", "/log/agent", json.dumps({"type": record_type, "body": body}).encode())
        if status != 200:
            raise RuntimeError(f"log refused {record_type}: {raw!r}")

    meter._submit = submit
    rows = []

    def make_adapter(config, level):
        return ADAPTERS[config](
            reasoning_effort=level, max_output_tokens=settings["output_tokens"],
            timeout_s=settings["timeout_s"], http_post=http_post,
            api_key=env["META_API_KEY"] if config == "spark" else env["BASETEN_API_KEY"])

    # Part 1: one spark call at low through the whole loop.
    loop = TurnLoop(
        harness_url=services.url, baldur_url=services.url, log_url=services.url,
        adapter=make_adapter("spark", "low"), repo_root=repo_root,
        transport=services.transport, private_key_path=env["ODIN_KEY_PATH"],
        instructions=_instructions(), frozen_reference="", meter=meter)
    results = loop.run(max_turns=5)
    calls = [r["body"] for r in services.log_records
             if r["type"] == "MODEL_CALL" and r["body"]["status"] == "OK"]
    first = calls[-1] if calls else {}
    outcome = results[0] if results else {"outcome": "error", "detail": "no turn"}
    rows.append({
        "part": 1, "config": "spark", "endpoint": SparkAdapter.endpoint,
        "model_id": SparkAdapter.model_id, "reasoning_effort": "low",
        "input_tokens": first.get("input_tokens") or 0,
        "cached_input_tokens": first.get("cached_input_tokens") or 0,
        "output_tokens": first.get("output_tokens") or 0,
        "reasoning_tokens": first.get("reasoning_tokens"),
        "cost_usd": first.get("actual_cost_usd") or 0.0,
        "seconds": first.get("latency_s") or 0.0,
        "cut_off": bool(outcome.get("cut_off")),
        "well_formed": outcome["outcome"] in ("request", "refused", "none", "escalation"),
        "detail": outcome["outcome"], "provider_usage": first.get("provider_usage"),
    })

    # Part 2: the fixed bundle, once per model per level, one attempt each.
    (out_dir / "inputs").mkdir(exist_ok=True)
    from odin.loop.canonical import sha256_hex

    (out_dir / "inputs" / sha256_hex(bundle_bytes(bundle))).write_bytes(bundle_bytes(bundle))
    (out_dir / "inputs" / sha256_hex(prompt)).write_bytes(prompt)
    for entry in plan:
        if entry["part"] != 2:
            continue
        adapter = make_adapter(entry["config"], entry["reasoning_effort"])
        sink = []
        try:
            result = adapter.complete(prompt=prompt, bundle=bundle, turn_id=1,
                                      meter=meter, model_call_sink=sink)
            if entry["config"] == "spark":
                ok, _obj, reason, detail = validate_act_text(result["raw"])
            else:
                ok, _obj, reason, detail = convert_tool_calls(
                    json.loads(result["raw"]), turn_kind="ACT")
            record = sink[-1] if sink else {}
            rows.append({
                "part": 2, "config": entry["config"], "endpoint": entry["endpoint"],
                "model_id": entry["model_id"],
                "reasoning_effort": entry["reasoning_effort"],
                "input_tokens": result.get("input_tokens") or 0,
                "cached_input_tokens": result.get("cached_input_tokens") or 0,
                "output_tokens": result.get("output_tokens") or 0,
                "reasoning_tokens": result.get("reasoning_tokens"),
                "cost_usd": record.get("actual_cost_usd") or 0.0,
                "seconds": result.get("latency_s") or 0.0,
                "cut_off": bool(result.get("cut_off")),
                "well_formed": bool(ok),
                "detail": "ok" if ok else f"{reason}: {detail}",
                "provider_usage": result.get("provider_usage"),
            })
        except ProviderError as exc:
            record = sink[-1] if sink else {}
            offered = "not offered" in str(exc) or "reasoning" in str(exc)
            rows.append({
                "part": 2, "config": entry["config"], "endpoint": entry["endpoint"],
                "model_id": entry["model_id"],
                "reasoning_effort": entry["reasoning_effort"],
                "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
                "reasoning_tokens": None, "cost_usd": 0.0,
                "seconds": record.get("latency_s") or 0.0, "cut_off": False,
                "well_formed": False,
                "detail": f"not offered ({exc})" if offered else f"provider error: {exc}",
                "provider_usage": None,
            })
        for record in sink:
            record["run_id"] = bundle["run_id"]
            submit("MODEL_CALL", record)

    header = ("| Part | Model | Endpoint | Model ID | Level | Input | Cached | Output "
              "| Reasoning | Cost USD | Seconds | Cut off | Well formed | Detail |\n"
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    lines = [header]
    for row in rows:
        lines.append(
            f"| {row['part']} | {row['config']} | {row['endpoint']} | {row['model_id']} "
            f"| {row['reasoning_effort']} | {row['input_tokens']} "
            f"| {row['cached_input_tokens']} | {row['output_tokens']} "
            f"| {row['reasoning_tokens']} | {row['cost_usd']:.6f} | {row['seconds']:.3f} "
            f"| {row['cut_off']} | {row['well_formed']} | {row['detail']} |\n")
    (out_dir / "table.md").write_text("".join(lines), encoding="utf-8")
    (out_dir / "table.json").write_text(
        json.dumps({"planned": plan, "rows": rows}, indent=2), encoding="utf-8")
    return {"planned": plan, "rows": rows, "total_reserved_usd": total,
            "out_dir": str(out_dir)}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="m3_check")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    if args.dry_run:
        result = run_check(repo_root=REPO_ROOT, env=env, dry_run=True)
        for entry in result["planned"]:
            print(f"part {entry['part']}  {entry['config']}  {entry['endpoint']}  "
                  f"{entry['model_id']}  level={entry['reasoning_effort']}  "
                  f"cap={entry['max_output_tokens']}  timeout_s={entry['timeout_s']}  "
                  f"reserved=${entry['reserved_usd']:.4f}")
        print(f"total worst-case reserved: ${result['total_reserved_usd']:.4f}")
        for name in REQUIRED_ENV:
            print(f"{name}: {'present' if env.get(name) else 'missing'}")
        return 0
    try:
        result = run_check(repo_root=REPO_ROOT, env=env)
    except RuntimeError as exc:
        print(str(exc))
        return 2
    print(f"table written to {result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
