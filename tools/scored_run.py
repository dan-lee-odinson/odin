"""Start a scored run (the Director's ruling of 28 October 2026), his signed plan and the arming act that names the
run, ODIN through Muse Code's start command, the ground seat on ODIN's COSMOS in real time. Phase 3 will start its
scored runs with it too.

    python tools/scored_run.py check <run>    everything short of starting: nothing is written to runs/, no model is
                                              called
    python tools/scored_run.py go <run>       start the run, fly ODIN as its own process, and stop the run by its exit

Phase 1: <run> is PH1-SHAKEDOWN-SPARK-R1 (ARM-PH1), PH1-SHAKEDOWN-SPARK-R2 (ARM-PH1-R2, after R1's build defect),
PH1-SHAKEDOWN-SPARK-R3 (ARM-PH1-R3, after R2's) or PH1-SHAKEDOWN-SPARK-R4 (ARM-PH1-R4, after R3's), by the
Director's rulings of 29 October 2026: spark, on COSMOS's demo INST target, for 1,800 s. check then needs ODIN's
COSMOS up with the demo plugin loaded (python -m connector.cosmos up, then demo-load).

Phase 2 (his word of 30 October 2026): <run> is PH2-<pass>-<arm>-R<n>, for the passes PASS1, PASS2A, PASS2B, PASS3
and PASS4, the arms SPARK (spark) and OPEN (spark_open), and n from 1 to 5, the runs each pass's signed act,
acts/ARM-PH2-<pass>.yaml, names. Each flies TYR0-P2-<pass>-v1 on its HUGINN scenario, rolled silently to the
pass's contact and flown in real time to its end. check then needs ODIN's COSMOS up with HUGINN's plugin and no
demo plugin.

A second set-aside for the same cause stops the series: while a stop stands, go refuses to start any run. ODIN's
standard output and error are kept for every run, whatever its exit, in runs/odin-output/<run>/, which git ignores,
since a traceback carries private paths. No credential, key or token value is printed; only whether each is present.
The harness and BALDUR-0 refuse a bad start themselves, whatever this checks.
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

from connector.api import CosmosApi, inst  # noqa: E402
from connector.cosmos import _user_environment, credentials, demo_installed, environment  # noqa: E402
from eval.set_aside import stops as series_stops  # noqa: E402
from gateway.acts import verify_arming_act  # noqa: E402
from gateway.plans import verify_chain  # noqa: E402
from harness import freeze, instructions  # noqa: E402
from harness.adapter import adapter_settings  # noqa: E402
from harness.launch import fly  # noqa: E402
from harness.procedures import ProcedureLibrary  # noqa: E402
from harness.run import Run  # noqa: E402
from wrapper.huginn import load_scenario  # noqa: E402

RUNS = {"PH1-SHAKEDOWN-SPARK-R1": ROOT / "acts" / "ARM-PH1.yaml",
        "PH1-SHAKEDOWN-SPARK-R2": ROOT / "acts" / "ARM-PH1-R2.yaml",
        "PH1-SHAKEDOWN-SPARK-R3": ROOT / "acts" / "ARM-PH1-R3.yaml",
        "PH1-SHAKEDOWN-SPARK-R4": ROOT / "acts" / "ARM-PH1-R4.yaml"}
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

# Phase 2: each pass's runs on each arm, as its signed act names them.
PASSES_PH2 = ("PASS1", "PASS2A", "PASS2B", "PASS3", "PASS4")
ARMS = {"SPARK": "spark", "OPEN": "spark_open"}
RUNS_PH2 = {f"PH2-{pass_name}-{arm}-R{n}": (pass_name, model)
            for pass_name in PASSES_PH2 for arm, model in ARMS.items() for n in range(1, 6)}
# RUN_START records a seed; nothing in phase 2 uses it either: HUGINN's scenarios are scripted, and the simulator
# draws nothing at random.
SEED_PH2 = 20261030
ANSWER_METHODS = {"spark": "STRUCTURED_OUTPUT", "spark_open": "ANSWER_TOOLS"}
KEYS = {"spark": "META_API_KEY", "spark_open": "BASETEN_API_KEY"}
# Each model's stop (CONTRACT.md §11.3), which ODIN's spend meter enforces: its bucket, its limit, its name.
STOPS = {"spark": ("META_CREDIT", 125.0, "Meta"), "spark_open": ("BASETEN_CREDIT", 90.0, "Baseten")}


def plan_ph2(pass_name):
    return ROOT / "plans" / f"TYR0-P2-{pass_name}-v1.yaml"


def act_ph2(pass_name):
    return ROOT / "acts" / f"ARM-PH2-{pass_name}.yaml"


def model_of(run_id):
    return RUNS_PH2[run_id][1] if run_id in RUNS_PH2 else "spark"


def needed(run_id):
    return (KEYS[model_of(run_id)], "ODIN_KEY_PATH")


def timeout_of(run_id):
    """How long ODIN may run: the pass's contact in real time, and 900 s more."""
    if run_id not in RUNS_PH2:
        return TIMEOUT_S
    window = yaml.safe_load(plan_ph2(RUNS_PH2[run_id][0]).read_bytes())["contact_window"]
    return window["los_met_s"] - window["aos_met_s"] + 900


def odin_environ(run_id=None):
    """This process's environment, with the run's model key and ODIN_KEY_PATH from the user's environment where this
    process lacks them. harness.launch strips every ODIN_COSMOS_* and OPENC3_* name before ODIN sees it."""
    environ = dict(os.environ)
    for name in needed(run_id) if run_id else NEEDED:
        if not environ.get(name) and _user_environment(name):
            environ[name] = _user_environment(name)
    return environ


def make_run(run_id):
    if run_id not in RUNS_PH2:
        return Run(run_id=run_id, scenario=None, scenario_id="PH1-SHAKEDOWN", phase=1, mode="SCORED",
                   plan_paths=[PLAN], act_path=RUNS[run_id], root=ROOT, procedures=ProcedureLibrary(), config=CONFIG,
                   seat="GROUND", pacing="REAL_TIME", rate=1.0)
    pass_name, model = RUNS_PH2[run_id]
    scenario_id = yaml.safe_load(plan_ph2(pass_name).read_bytes())["scenario_id"]
    config = {"seed": SEED_PH2, "model_config": model, "answer_method": ANSWER_METHODS[model],
              "reference_sha256": REFERENCE}
    return Run(run_id=run_id, scenario=load_scenario(scenario_id), scenario_id=scenario_id, phase=2, mode="SCORED",
               plan_paths=[plan_ph2(pass_name)], act_path=act_ph2(pass_name), root=ROOT, procedures=ProcedureLibrary(),
               config=config, seat="GROUND", pacing="REAL_TIME", rate=1.0)


def spent(ledger, bucket="META_CREDIT"):
    """What ODIN's spend meter has settled against one of its buckets so far, from its ledger."""
    if not ledger.exists():
        return 0.0
    events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sum(e["actual_usd"] for e in events if e.get("kind") == "SETTLE" and e.get("bucket") == bucket)


meta_spent = spent


def check(run_id):
    results = []

    def step(what, ok, seen=""):
        results.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {what}{': ' + str(seen) if seen != '' else ''}", flush=True)

    model = model_of(run_id)
    if run_id in RUNS_PH2:
        pass_name = RUNS_PH2[run_id][0]
        plan, act = plan_ph2(pass_name), act_ph2(pass_name)
        scenario_id = yaml.safe_load(plan.read_bytes())["scenario_id"]
        cosmos = CosmosApi()
        names = cosmos.call("get_interface_names")
        step("ODIN's COSMOS: HUGINN's plugin, its HUGINN_INT dialing the run's link", names == ["HUGINN_INT"],
             {"interfaces": names, "HUGINN_INT": cosmos.ground_link()["state"]})
        step("no demo plugin in ODIN's COSMOS", demo_installed(environment(credentials())) == [])
    else:
        plan, act, scenario_id = PLAN, RUNS[run_id], "PH1-SHAKEDOWN"
        cosmos = inst(DICTIONARY)
        link, packet = cosmos.ground_link(), cosmos.packet()
        step("ODIN's COSMOS: the demo's INST_INT", link["state"] == "CONNECTED", link)
        step("INST HEALTH_STATUS coming in", packet["received_count"] > 0,
             {k: packet["frame"][k] for k in ("COLLECTS", "CMD_ACPT_CNT", "TEMP1")} if packet["frame"] else None)
        step("COSMOS's command history readable (U62)", isinstance(cosmos.commands_by_others(), int))
        step("the demo plugin, alone, in ODIN's COSMOS", demo_installed(environment(credentials())) == DEMO)
    chain_record, chain = verify_chain([plan], scenario_id=scenario_id, mode="SCORED")
    step("the plan chain, as BALDUR-0 verifies it in SCORED mode", chain_record["result"] == "PASS",
         [(p["plan_id"], p["sha256"][:19] + "...") for p in chain_record["plans"]])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    act_record, _ = verify_arming_act(act, run_id=run_id, chain_hashes=chain.hashes if chain else [],
                                      utc=now, mode="SCORED")
    step(f"{act.stem} for {run_id}", act_record["result"] == "PASS", (act_record["rung"], act_record["reason"]))
    frozen = instructions.frozen(model)
    block = freeze.check(model)
    step("ODIN's instructions and prompt template as frozen (U54)", bool(frozen),
         {k: (v[:19] + "...") if isinstance(v, str) else v for k, v in frozen.items()})
    step(f"{model}'s settings and the six schemas as frozen (U55)", bool(block),
         {k: block[k] for k in ("model", "reasoning_effort", "max_output_tokens", "timeout_s")} if block else block)
    settings = adapter_settings(model, block, mode="SCORED", endpoint=None)
    step(f"{model}'s provider and endpoint from its adapter (U57)", settings.get("endpoint"), settings)
    environ = odin_environ(run_id)
    for name in needed(run_id):
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
    bucket, limit, who = STOPS[model]
    so_far = spent(ledger, bucket)
    step(f"{who} spent so far by ODIN's spend meter, against the ${limit:.0f} stop", so_far < limit,
         f"${so_far:.4f}" + ("" if ledger.exists() else " (no ledger yet)"))
    stopped = series_stops()
    step("no series stopped by a second set-aside for the same cause (marks/set_aside.yaml)", not stopped,
         stopped_text(stopped) if stopped else "")
    print("every check holds" if all(results) else f"{results.count(False)} check(s) failed")
    return 0 if all(results) else 1


def stopped_text(stopped):
    return "; ".join(f"phase {phase}, {key}, {count} runs" for (phase, key), count in sorted(stopped.items()))


def go(run_id):
    # A second set-aside for the same cause stops the series until the Director lifts it once the fix is committed
    # (his rulings of 29 October 2026): while a stop stands, no scored run starts (his word of 30 October 2026).
    stopped = series_stops()
    if stopped:
        print(f"refused: the series is stopped until the Director lifts it: {stopped_text(stopped)}", flush=True)
        return 1
    run = make_run(run_id)
    print(f"starting {run_id} at {datetime.now(timezone.utc).isoformat(timespec='seconds')}", flush=True)
    code = fly(run, environ=odin_environ(run_id), timeout_s=timeout_of(run_id), output_dir=OUTPUT / run_id)
    print(f"ODIN's process exited {code}; RUN_END {run.ended}; folder {run.final.relative_to(ROOT).as_posix()}; "
          f"ODIN's output in {(OUTPUT / run_id).relative_to(ROOT).as_posix()}", flush=True)
    return 0 if code == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("check", "go") or sys.argv[2] not in {**RUNS, **RUNS_PH2}:
        sys.exit(__doc__)
    sys.exit({"check": check, "go": go}[sys.argv[1]](sys.argv[2]))
