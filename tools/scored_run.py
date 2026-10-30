"""Start a scored run (the Director's ruling of 28 October 2026), his signed plan and the arming act that names the
run, ODIN through Muse Code's start command, the ground seat on ODIN's COSMOS in real time. Phase 3 starts its
scored runs with it too.

    python tools/scored_run.py check <run> [--held-out <folder>]    everything short of starting: nothing is written
                                                                    to runs/, no model is called
    python tools/scored_run.py go <run> [--held-out <folder>]       start the run, fly ODIN as its own process, and
                                                                    stop the run by its exit

Phase 1: <run> is PH1-SHAKEDOWN-SPARK-R1 (ARM-PH1), PH1-SHAKEDOWN-SPARK-R2 (ARM-PH1-R2, after R1's build defect),
PH1-SHAKEDOWN-SPARK-R3 (ARM-PH1-R3, after R2's) or PH1-SHAKEDOWN-SPARK-R4 (ARM-PH1-R4, after R3's), by the
Director's rulings of 29 October 2026: spark, on COSMOS's demo INST target, for 1,800 s. check then needs ODIN's
COSMOS up with the demo plugin loaded (python -m connector.cosmos up, then demo-load).

Phase 2 (his word of 30 October 2026): <run> is PH2-<pass>-<arm>-R<n>, for the passes PASS1, PASS2A, PASS2B, PASS3
and PASS4, the arms SPARK (spark) and OPEN (spark_open), and n from 1 to 5, the runs each pass's signed act,
acts/ARM-PH2-<pass>.yaml, names. Each flies TYR0-P2-<pass>-v1 on its HUGINN scenario, rolled silently to the
pass's contact and flown in real time to its end. check then needs ODIN's COSMOS up with HUGINN's plugin and no
demo plugin.

Phase 3 (CONTRACT.md §10.3): <run> is PH3-<label>-<arm>-R<n>, as the held-out arming acts name them, five per model
as in phase 2, and check and go need --held-out, the held-out folder outside the repository. Everything a run flies is
read from it at run time, once it checks against the seals (harness/phase3.py), so nothing here names a scenario or
holds any of its values: the sealed scenario, its seats, faults and feeds; its plans as signed, each the sealed plan's
bytes with its .sig beside it in plans-to-sign/; the arming act in acts/ that names the run; and, where the scenario
scripts a revocation, the restore act signed in advance for the run, acts/RST-PH3-<label>-<arm>-R<n>.yaml.
RUN_START's seed is the scenario's own HUGINN seed. A scenario with an onboard seat starts ODIN with Glimmer on Modal
beside the arm's model (M17; the Director's ruling of 29 October 2026), and go first keeps Glimmer's endpoint warm
(tools/glimmer_modal.py warm), so no cold start lands in a turn; tools/glimmer_modal.py cold lets it scale to zero
once the series is done. Modal's own token warms it, and is never in ODIN's environment (harness/launch.py).

A second set-aside for the same cause stops the series: while a stop stands, go refuses to start any run. ODIN's
standard output and error are kept for every run, whatever its exit, in runs/odin-output/<run>/, which git ignores,
since a traceback carries private paths. No credential, key or token value is printed; only whether each is present.
The harness and BALDUR-0 refuse a bad start themselves, whatever this checks.
"""

import json
import os
import re
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
from eval.phase3 import load_checks  # noqa: E402
from eval.set_aside import stops as series_stops  # noqa: E402
from gateway.acts import verify_arming_act, verify_restore_act  # noqa: E402
from gateway.plans import verify_chain  # noqa: E402
from harness import freeze, instructions  # noqa: E402
from harness.adapter import adapter_settings  # noqa: E402
from harness.launch import fly  # noqa: E402
from harness.phase3 import HeldOut  # noqa: E402
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
STOPS = {"spark": ("META_CREDIT", 125.0, "Meta"), "spark_open": ("BASETEN_CREDIT", 90.0, "Baseten"),
         "glimmer_modal": ("MODAL_CREDIT", 125.0, "Modal")}

# Phase 3: the runs the held-out arming acts name. The onboard seat's model is Glimmer on Modal (the Director's ruling
# of 29 October 2026), on the endpoint its frozen block names. Its proxy key and secret go to ODIN; Modal's own token
# goes only to tools/glimmer_modal.py.
PH3_RUN = re.compile(r"PH3-(H\d\d)-(SPARK|OPEN)-R([1-5])")
ONBOARD_PH3 = "glimmer_modal"
GLIMMER_GPU = "h100"
ONBOARD_KEYS = ("ODIN_MODAL_PROXY_KEY", "ODIN_MODAL_PROXY_SECRET")
MODAL_TOKENS = ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET")


def plan_ph2(pass_name):
    return ROOT / "plans" / f"TYR0-P2-{pass_name}-v1.yaml"


def act_ph2(pass_name):
    return ROOT / "acts" / f"ARM-PH2-{pass_name}.yaml"


def phase3_of(run_id):
    """(label, arm, n) of a phase-3 run ID, or None for any other."""
    found = PH3_RUN.fullmatch(run_id)
    return (found[1], found[2], int(found[3])) if found else None


class Phase3:
    """What a phase-3 run flies, from the held-out folder, every part checked or the run refused: its sealed scenario,
    its plans as signed (each the sealed plan's bytes, its .sig beside it in plans-to-sign/), the arming act that
    names the run, its arm's model and, where a seat is ONBOARD, the onboard model, and the restore act signed in
    advance for the run where its scenario scripts a revocation. seal: the seal to check against, the seal in force by
    default (tests use their own)."""

    def __init__(self, run_id, folder, seal=None):
        label, arm, n = phase3_of(run_id)
        folder = Path(folder)
        held = HeldOut(folder, seal=seal)
        self.scenario = held.scenario(label)
        self.seed = yaml.safe_load(held.files[f"{label}.scenario.yaml"])["huginn"]["seed"]
        self.model = ARMS[arm]
        self.act = folder / "acts" / f"ARM-PH3-{label}.yaml"
        if run_id not in yaml.safe_load(self.act.read_bytes())["runs"]:
            raise ValueError(f"{self.act.name} does not name {run_id}")
        self.plans = []
        for sealed in self.scenario.plan_paths:
            signed = folder / "plans-to-sign" / sealed.name
            if signed.read_bytes() != sealed.read_bytes():
                raise ValueError(f"plans-to-sign/{sealed.name} is not the sealed plan's bytes")
            self.plans.append(signed)
        self.onboard = ONBOARD_PH3 if any(seat == "ONBOARD" for _, _, seat, _ in self.scenario.seats) else None
        self.restore = (folder / "acts" / f"RST-PH3-{label}-{arm}-R{n}.yaml"
                        if "revocation" in self.scenario.script else None)

    def timeout_s(self):
        """How long ODIN may run: from the first seat to the run's end in real time, and 900 s more."""
        return self.scenario.run["end_met_s"] - self.scenario.seats[0][0] + 900


def model_of(run_id):
    if phase3_of(run_id):
        return ARMS[phase3_of(run_id)[1]]
    return RUNS_PH2[run_id][1] if run_id in RUNS_PH2 else "spark"


def needed(run_id, onboard=None):
    return (KEYS[model_of(run_id)], "ODIN_KEY_PATH", *(ONBOARD_KEYS if onboard else ()))


def timeout_of(run_id):
    """How long ODIN may run: the pass's contact in real time, and 900 s more."""
    if run_id not in RUNS_PH2:
        return TIMEOUT_S
    window = yaml.safe_load(plan_ph2(RUNS_PH2[run_id][0]).read_bytes())["contact_window"]
    return window["los_met_s"] - window["aos_met_s"] + 900


def odin_environ(run_id=None, onboard=None):
    """This process's environment, with the run's model keys and ODIN_KEY_PATH from the user's environment where this
    process lacks them. harness.launch strips every ODIN_COSMOS_*, OPENC3_* and MODAL_TOKEN_* name before ODIN sees
    it."""
    environ = dict(os.environ)
    for name in needed(run_id, onboard) if run_id else NEEDED:
        if not environ.get(name) and _user_environment(name):
            environ[name] = _user_environment(name)
    return environ


def glimmer(action):
    """tools/glimmer_modal.py <action> on the onboard endpoint, with Modal's own token and the endpoint's proxy key
    and secret (its warm-up request goes through the proxy) from the user's environment where this process lacks
    them; its exit code. Nothing prints any of them."""
    environ = dict(os.environ)
    for name in MODAL_TOKENS + ONBOARD_KEYS:
        if not environ.get(name) and _user_environment(name):
            environ[name] = _user_environment(name)
    return subprocess.run([sys.executable, str(ROOT / "tools" / "glimmer_modal.py"), action, GLIMMER_GPU],
                          cwd=ROOT, env=environ).returncode


def make_run(run_id, held_out=None, seal=None):
    if phase3_of(run_id):
        flown = Phase3(run_id, held_out, seal=seal)
        scenario = flown.scenario
        config = {"seed": flown.seed, "model_config": flown.model, "answer_method": ANSWER_METHODS[flown.model],
                  "reference_sha256": REFERENCE}
        return Run(run_id=run_id, scenario=scenario.huginn, scenario_id=scenario.scenario_id, phase=3, mode="SCORED",
                   plan_paths=flown.plans, act_path=flown.act, root=ROOT, procedures=ProcedureLibrary(), config=config,
                   rate=1.0, seats=scenario.seats, feeds=scenario.all_feeds(), receiver_down=scenario.receiver_down,
                   revocation=scenario.revocation(flown.restore), latch_up=scenario.latch_up, onboard=flown.onboard)
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


def check(run_id, held_out=None):
    results = []

    def step(what, ok, seen=""):
        results.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {what}{': ' + str(seen) if seen != '' else ''}", flush=True)

    model, onboard, restore = model_of(run_id), None, None
    if phase3_of(run_id):
        try:
            flown = Phase3(run_id, held_out)
        except Exception as refused:   # the seal, the scenario, the act or a signed plan: each refuses the run
            step("the held-out folder: the sealed scenario, the act that names the run, its plans as signed", False,
                 f"{type(refused).__name__}: {refused}")
            print("1 check(s) failed")
            return 1
        step("the sealed scenario, against the seal in force, and the act that names the run", True,
             flown.scenario.scenario_id)
        step("its plans as signed, each the sealed plan's bytes", True, [p.name for p in flown.plans])
        sys.dont_write_bytecode = True   # nothing written into the held-out folder
        try:
            load_checks(Path(held_out) / "checks")
            step("S8's phase-3 checks, against their seal in force", True)
        except Exception as refused:
            step("S8's phase-3 checks, against their seal in force", False, f"{type(refused).__name__}: {refused}")
        plans, act, scenario_id, onboard, restore = flown.plans, flown.act, flown.scenario.scenario_id, \
            flown.onboard, flown.restore
        step("the onboard seat's model", True, onboard or "none: no seat is ONBOARD")
    if run_id in RUNS_PH2 or phase3_of(run_id):
        if run_id in RUNS_PH2:
            pass_name = RUNS_PH2[run_id][0]
            plans, act = [plan_ph2(pass_name)], act_ph2(pass_name)
            scenario_id = yaml.safe_load(plans[0].read_bytes())["scenario_id"]
        cosmos = CosmosApi()
        names = cosmos.call("get_interface_names")
        step("ODIN's COSMOS: HUGINN's plugin, its HUGINN_INT dialing the run's link", names == ["HUGINN_INT"],
             {"interfaces": names, "HUGINN_INT": cosmos.ground_link()["state"]})
        step("no demo plugin in ODIN's COSMOS", demo_installed(environment(credentials())) == [])
    else:
        plans, act, scenario_id = [PLAN], RUNS[run_id], "PH1-SHAKEDOWN"
        cosmos = inst(DICTIONARY)
        link, packet = cosmos.ground_link(), cosmos.packet()
        step("ODIN's COSMOS: the demo's INST_INT", link["state"] == "CONNECTED", link)
        step("INST HEALTH_STATUS coming in", packet["received_count"] > 0,
             {k: packet["frame"][k] for k in ("COLLECTS", "CMD_ACPT_CNT", "TEMP1")} if packet["frame"] else None)
        step("COSMOS's command history readable (U62)", isinstance(cosmos.commands_by_others(), int))
        step("the demo plugin, alone, in ODIN's COSMOS", demo_installed(environment(credentials())) == DEMO)
    chain_record, chain = verify_chain(plans, scenario_id=scenario_id, mode="SCORED")
    step("the plan chain, as BALDUR-0 verifies it in SCORED mode", chain_record["result"] == "PASS",
         [(p["plan_id"], p["sha256"][:19] + "...") for p in chain_record["plans"]])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    act_record, _ = verify_arming_act(act, run_id=run_id, chain_hashes=chain.hashes if chain else [],
                                      utc=now, mode="SCORED")
    step(f"{act.stem} for {run_id}", act_record["result"] == "PASS", (act_record["rung"], act_record["reason"]))
    if restore is not None:
        plan_id = yaml.safe_load(plans[-1].read_bytes())["plan_id"]
        restore_record, _ = verify_restore_act(restore, run_id=run_id, plan_id=plan_id, revoked=True, used=set(),
                                               utc=now, mode="SCORED")
        step(f"{restore.stem}, the restore act signed in advance for {run_id}", restore_record["result"] == "ACCEPTED",
             (restore_record["result"], restore_record.get("reason")))
    frozen = instructions.frozen(model)
    step("ODIN's instructions and prompt template as frozen (U54)", bool(frozen),
         {k: (v[:19] + "...") if isinstance(v, str) else v for k, v in frozen.items()})
    for one in (model, onboard) if onboard else (model,):
        block = freeze.check(one)
        step(f"{one}'s settings and the six schemas as frozen (U55)", bool(block),
             {k: block[k] for k in ("model", "reasoning_effort", "max_output_tokens", "timeout_s")} if block else block)
        settings = adapter_settings(one, block, mode="SCORED", endpoint=None)
        step(f"{one}'s provider and endpoint from its adapter (U57)", settings.get("endpoint"), settings)
    environ = odin_environ(run_id, onboard)
    for name in needed(run_id, onboard) + (MODAL_TOKENS if onboard else ()):
        present = os.environ.get(name) or (_user_environment(name) if name in MODAL_TOKENS else environ.get(name))
        source = "this process" if os.environ.get(name) else "the user's environment" if present else None
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
    for one in (model, onboard) if onboard else (model,):
        bucket, limit, who = STOPS[one]
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


def go(run_id, held_out=None):
    # A second set-aside for the same cause stops the series until the Director lifts it once the fix is committed
    # (his rulings of 29 October 2026): while a stop stands, no scored run starts (his word of 30 October 2026).
    stopped = series_stops()
    if stopped:
        print(f"refused: the series is stopped until the Director lifts it: {stopped_text(stopped)}", flush=True)
        return 1
    flown = Phase3(run_id, held_out) if phase3_of(run_id) else None
    if flown and flown.onboard and glimmer("warm") != 0:
        print(f"refused: {flown.onboard}'s endpoint did not come up warm", flush=True)
        return 1
    run = make_run(run_id, held_out)
    print(f"starting {run_id} at {datetime.now(timezone.utc).isoformat(timespec='seconds')}", flush=True)
    code = fly(run, environ=odin_environ(run_id, flown.onboard if flown else None),
               timeout_s=flown.timeout_s() if flown else timeout_of(run_id), output_dir=OUTPUT / run_id)
    print(f"ODIN's process exited {code}; RUN_END {run.ended}; folder {run.final.relative_to(ROOT).as_posix()}; "
          f"ODIN's output in {(OUTPUT / run_id).relative_to(ROOT).as_posix()}", flush=True)
    return 0 if code == 0 else 1


if __name__ == "__main__":
    arguments = sys.argv[1:]
    held_out = None
    if arguments[2:3] == ["--held-out"] and len(arguments) == 4:
        held_out, arguments = arguments[3], arguments[:2]
    known = len(arguments) == 2 and (arguments[1] in {**RUNS, **RUNS_PH2}
                                     or (phase3_of(arguments[1]) and held_out is not None))
    if not known or arguments[0] not in ("check", "go"):
        sys.exit(__doc__)
    sys.exit({"check": check, "go": go}[arguments[0]](arguments[1], held_out))
