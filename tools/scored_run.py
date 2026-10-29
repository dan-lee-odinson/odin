"""Start a scored run (the Director's ruling of 28 October 2026): phase 1's, his signed plan and the arming act that
names the run, ODIN on spark through Muse Code's start command, the ground seat on ODIN's COSMOS with the demo's INST
target, in real time for 1,800 s. Phases 2 and 3 will start their scored runs with it too.

    python tools/scored_run.py check <run>    everything short of starting: nothing is written to runs/, no model is
                                              called
    python tools/scored_run.py go <run>       start the run, fly ODIN as its own process on spark, and stop the run
                                              by its exit

<run> is PH1-SHAKEDOWN-SPARK-R1 (ARM-PH1) or PH1-SHAKEDOWN-SPARK-R2 (ARM-PH1-R2, after R1's build defect, the
Director's ruling of 29 October 2026). ODIN's standard output and error are kept for every run, whatever its exit,
in runs/odin-output/<run>/, which git ignores, since a traceback carries private paths.

check needs ODIN's COSMOS up with the demo plugin loaded (python -m connector.cosmos up, then demo-load). No
credential, key or token value is printed; only whether each is present. The harness and BALDUR-0 refuse a bad
start themselves, whatever this checks.
"""

import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from connector.api import inst  # noqa: E402
from connector.cosmos import _user_environment, credentials, demo_installed, environment  # noqa: E402
from gateway.acts import verify_arming_act  # noqa: E402
from gateway.plans import verify_chain  # noqa: E402
from harness import freeze, instructions  # noqa: E402
from harness.adapter import adapter_settings  # noqa: E402
from harness.launch import fly  # noqa: E402
from harness.procedures import ProcedureLibrary  # noqa: E402
from harness.run import Run  # noqa: E402

RUNS = {"PH1-SHAKEDOWN-SPARK-R1": ROOT / "acts" / "ARM-PH1.yaml",
        "PH1-SHAKEDOWN-SPARK-R2": ROOT / "acts" / "ARM-PH1-R2.yaml"}
PLAN = ROOT / "plans" / "TYR0-PH1-SHAKEDOWN-v1.yaml"
OUTPUT = ROOT / "runs" / "odin-output"
DICTIONARY = yaml.safe_load((ROOT / "config" / "dictionaries" / "INST.yaml").read_text(encoding="utf-8"))
REFERENCE = json.loads((ROOT / "odin" / "study" / "cosmos_reference.json").read_text(encoding="utf-8"))["sha256"]
# RUN_START records a seed; nothing in phase 1 uses it: COSMOS's demo simulates itself and ODIN never receives it.
# The Director's word of 28 October 2026: 20261028.
SEED = 20261028
CONFIG = {"seed": SEED, "model_config": "spark", "answer_method": "STRUCTURED_OUTPUT", "reference_sha256": REFERENCE}
NEEDED = ("META_API_KEY", "ODIN_KEY_PATH")
DEMO = ["openc3-cosmos-demo-7.2.1.gem__0"]
STOP_USD = 125.0   # the Meta stop (CONTRACT.md §11.3), which ODIN's spend meter enforces
TIMEOUT_S = 1800 + 900


def odin_environ():
    """This process's environment, with META_API_KEY and ODIN_KEY_PATH from the user's environment where this
    process lacks them. harness.launch strips every ODIN_COSMOS_* and OPENC3_* name before ODIN sees it."""
    environ = dict(os.environ)
    for name in NEEDED:
        if not environ.get(name) and _user_environment(name):
            environ[name] = _user_environment(name)
    return environ


def make_run(run_id):
    return Run(run_id=run_id, scenario=None, scenario_id="PH1-SHAKEDOWN", phase=1, mode="SCORED", plan_paths=[PLAN],
               act_path=RUNS[run_id], root=ROOT, procedures=ProcedureLibrary(), config=CONFIG, seat="GROUND",
               pacing="REAL_TIME", rate=1.0)


def meta_spent(ledger):
    """What ODIN's spend meter has settled against Meta's credit so far, from its ledger."""
    if not ledger.exists():
        return 0.0
    events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sum(e["actual_usd"] for e in events if e.get("kind") == "SETTLE" and e.get("bucket") == "META_CREDIT")


def check(run_id):
    results = []

    def step(what, ok, seen=""):
        results.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {what}{': ' + str(seen) if seen != '' else ''}", flush=True)

    cosmos = inst(DICTIONARY)
    link, packet = cosmos.ground_link(), cosmos.packet()
    step("ODIN's COSMOS: the demo's INST_INT", link["state"] == "CONNECTED", link)
    step("INST HEALTH_STATUS coming in", packet["received_count"] > 0,
         {k: packet["frame"][k] for k in ("COLLECTS", "CMD_ACPT_CNT", "TEMP1")} if packet["frame"] else None)
    step("COSMOS's command history readable (U62)", isinstance(cosmos.commands_by_others(), int))
    step("the demo plugin, alone, in ODIN's COSMOS", demo_installed(environment(credentials())) == DEMO)
    chain_record, chain = verify_chain([PLAN], scenario_id="PH1-SHAKEDOWN", mode="SCORED")
    step("the plan chain, as BALDUR-0 verifies it in SCORED mode", chain_record["result"] == "PASS",
         [(p["plan_id"], p["sha256"][:19] + "...") for p in chain_record["plans"]])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    act_record, _ = verify_arming_act(RUNS[run_id], run_id=run_id, chain_hashes=chain.hashes if chain else [],
                                      utc=now, mode="SCORED")
    step(f"{RUNS[run_id].stem} for {run_id}", act_record["result"] == "PASS",
         (act_record["rung"], act_record["reason"]))
    frozen = instructions.frozen("spark")
    block = freeze.check("spark")
    step("ODIN's instructions and prompt template as frozen (U54)", bool(frozen),
         {k: (v[:19] + "...") if isinstance(v, str) else v for k, v in frozen.items()})
    step("spark's settings and the six schemas as frozen (U55)", bool(block),
         {k: block[k] for k in ("model", "reasoning_effort", "max_output_tokens", "timeout_s")})
    settings = adapter_settings("spark", block, mode="SCORED", endpoint=None)
    step("spark's provider and endpoint from its adapter (U57)", settings.get("endpoint"), settings)
    environ = odin_environ()
    for name in NEEDED:
        source = "this process" if os.environ.get(name) else "the user's environment" if environ.get(name) else None
        step(f"{name} present (value not shown)", source, source or "missing")
    key_path = environ.get("ODIN_KEY_PATH")
    if key_path:
        derived = subprocess.run(["ssh-keygen", "-y", "-f", key_path], capture_output=True, text=True)
        pub = (ROOT / "keys" / "odin.pub").read_text(encoding="utf-8").split()[:2]
        step("ODIN's signing key matches keys/odin.pub", derived.returncode == 0 and derived.stdout.split()[:2] == pub,
             "match" if derived.stdout.split()[:2] == pub else "no match or unreadable")
    for folder in (ROOT / "runs" / run_id, ROOT / "runs" / "scored" / run_id, OUTPUT / run_id):
        step(f"{folder.relative_to(ROOT).as_posix()} does not exist yet", not folder.exists())
    ports = yaml.safe_load((ROOT / "config" / "ports.yaml").read_text(encoding="utf-8"))
    for name, port in ports["ports"].items():
        with socket.socket() as probe:
            free = probe.connect_ex((ports["host"], port)) != 0
        step(f"port {port} ({name}) free", free)
    ledger = ROOT / "runs" / "spend.jsonl"
    spent = meta_spent(ledger)
    step(f"Meta spent so far by ODIN's spend meter, against the ${STOP_USD:.0f} stop", spent < STOP_USD,
         f"${spent:.4f}" + ("" if ledger.exists() else " (no ledger yet)"))
    print("every check holds" if all(results) else f"{results.count(False)} check(s) failed")
    return 0 if all(results) else 1


def go(run_id):
    run = make_run(run_id)
    print(f"starting {run_id} at {datetime.now(timezone.utc).isoformat(timespec='seconds')}", flush=True)
    code = fly(run, environ=odin_environ(), timeout_s=TIMEOUT_S, output_dir=OUTPUT / run_id)
    print(f"ODIN's process exited {code}; RUN_END {run.ended}; folder {run.final.relative_to(ROOT).as_posix()}; "
          f"ODIN's output in {(OUTPUT / run_id).relative_to(ROOT).as_posix()}", flush=True)
    return 0 if code == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("check", "go") or sys.argv[2] not in RUNS:
        sys.exit(__doc__)
    sys.exit({"check": check, "go": go}[sys.argv[1]](sys.argv[2]))
