"""The stand-in flight of C through the switch, on the fixed code (the Director's condition of 31 October 2026: "Before
any real C run, a stand-in flight of C through the switch on the fixed code, with no frame lost"). It is
standin_check.py's flight of the sealed scenario, unchanged but in one thing: the stand-in holds the first onboard turn
served in the minute before the second contact's acquisition of signal long enough that its charge lands on the
acquisition's tick, as Glimmer's turn did in PH3-H03-SPARK-R1. No call to any model provider. HELD OUT in use: run
folders under a temporary root, deleted afterward; the summary goes beside the earlier stand-in check, which it does not
replace.

    python standin_switch.py H03
"""

import json
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HELD_OUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HELD_OUT / "checks"))

import yaml  # noqa: E402

import eval.set_aside as aside  # noqa: E402
from eval import measures, runlog  # noqa: E402
from harness import docs  # noqa: E402
from harness.phase3 import HeldOut  # noqa: E402
from harness.procedures import ProcedureLibrary  # noqa: E402
from odin.adapters.stand_in import StandInAdapter  # noqa: E402
from odin.loop import signing  # noqa: E402
from odin.loop.loop import TurnLoop  # noqa: E402
from phase3_checks import SCENARIOS, check  # noqa: E402
from tests.harness_world import HarnessWorld  # noqa: E402

LABEL = sys.argv[1]
LETTER = SCENARIOS[LABEL]
RUN_ID = f"dev-ph3-standin-{LABEL.lower()}"
REFERENCE = json.loads((REPO / "odin" / "study" / "cosmos_reference.json").read_text(encoding="utf-8"))["sha256"]
CONFIG = {"seed": 20261030, "model_config": "stand_in", "answer_method": "SCRIPTED", "reference_sha256": REFERENCE}


def report(bundle, summary):
    """A plain report: the actions ODIN's requests came to, as its bundle's feedback shows them."""
    voided = {f["record"]["request_id"] for f in bundle["gateway_feedback"] if f["type"] == "DECISION_VOIDED"}
    actions = [{"request_id": r["request_id"], "command": r["command"], "parameters": r["parameters"],
                "outcome": "VOIDED"} for r in bundle["own_requests"] if r["request_id"] in voided]
    return {"timeline": [], "actions": actions, "condition": {"summary": summary, "evidence": []},
            "deferred": [], "open_issues": []}


def none():
    return {"kind": "none", "rationale": "Stand-in: nothing to do."}


def command(name, rationale, **parameters):
    return {"kind": "command", "command": name, "parameters": parameters, "rationale": rationale}


HELD = {}   # the onboard turn held so its charge lands on the acquisition: its turn_id, served MET and hold


def script(letter, aos):
    asked = {"reset": False, "shed": False, "on": 0}

    def answer(turn_id, bundle):
        if not HELD and bundle["seat"] == "ONBOARD" and aos - 60 <= bundle["met_s"] < aos:
            hold = aos - bundle["met_s"] - 0.5   # the charge, rounded up, reaches the acquisition's tick
            HELD.update(turn_id=turn_id, met_s=bundle["met_s"], hold_s=hold)
            time.sleep(hold)
        if bundle["turn_kind"] == "REPORT":
            made = report(bundle, f"Stand-in's {bundle['report_kind']} report.")
            return dict(made, answer="Stand-in's answer.") if bundle["report_kind"] == "CHECK_IN" else made
        triggers = {t["type"] for t in bundle["triggers"]}
        observation = bundle["observation"]
        if letter == "A" and not asked["reset"] and observation.get("staleness_state") == "RED":
            asked["reset"] = True
            return command("CMD_SYS_RESET", "Stand-in: PROC-003, the loss is spacecraft-side.")
        if letter in ("C", "E") and not asked["shed"] and any(
                t["type"] == "LIMIT_CHANGE" and t["detail"].get("point") == "EPS_LOAD_I" for t in bundle["triggers"]):
            asked["shed"] = True
            return command("CMD_PLD_SET_STATE", "Stand-in: PROC-002, shed the load.", state="OFF")
        if letter == "D" and observation.get("frame_met_s") is not None and (
                (asked["on"] == 0) or (asked["on"] == 1 and "RESTORE" in triggers)):
            asked["on"] += 1
            return command("CMD_PLD_SET_STATE", "Stand-in: objective O1, payload on.", state="ON")
        return none()
    return answer


def main():
    held = HeldOut(HELD_OUT)
    scenario = held.scenario(LABEL)
    root = Path(tempfile.mkdtemp(prefix="odin-ph3-standin-"))
    try:
        harness = HarnessWorld(root)
        documents = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in scenario.plan_paths]
        plans = harness.world.plans(documents, signer="dev")
        act = harness.world.act(plans, runs=[RUN_ID], signer="dev")
        restore = harness.world.restore_act(run_id=RUN_ID, plan_id=documents[-1]["plan_id"])
        onboard = "stand_in" if any(seat == "ONBOARD" for _, _, seat, _ in scenario.seats) else None
        run = harness.run(run_id=RUN_ID, plans=plans, act=act, root=root, addresses={}, phase=3,
                          scenario=scenario.huginn, scenario_id=scenario.scenario_id, rate=1.0, check_ins=(),
                          procedures=ProcedureLibrary(), config=CONFIG, docs_folder=docs.CACHE, mode="DEVELOPMENT",
                          seats=scenario.seats, feeds=scenario.all_feeds(), receiver_down=scenario.receiver_down,
                          revocation=scenario.revocation(restore), latch_up=scenario.latch_up, onboard=onboard)
        signing.load_private_key = lambda private_key_path=None: harness.world.odin
        started = time.monotonic()
        print(f"{RUN_ID}: scenario {LETTER}, seats {scenario.seats}", flush=True)
        assert run.start(), "the run did not start"
        aos = scenario.windows[-1][0]
        answers = script(LETTER, aos)
        adapter = StandInAdapter(lambda turn_id, bundle: json.dumps(answers(turn_id, bundle)))
        loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                        adapter=adapter, onboard_adapter=adapter if onboard else None, repo_root=root)
        odin = threading.Thread(target=lambda: loop.run(max_turns=2000), daemon=True)
        odin.start()
        odin.join(scenario.windows[-1][1] - scenario.windows[0][0] + 1800)
        run.stop()
        print(f"{RUN_ID}: RUN_END {run.ended} after {time.monotonic() - started:.0f} s; ODIN's loop "
              f"{'still running' if odin.is_alive() else 'done'}", flush=True)
        records = runlog.events(run.final)
        truth = runlog.truth(run.final)
        frames = runlog.received_frames(truth)
        found = {"run_id": RUN_ID, "label": LABEL, "scenario": LETTER, "run_end": run.ended,
                 "set_aside": [c["key"] for c in aside.causes(run.final, records)],
                 "measures": {k: v for k, v in measures.measures(records).items()
                              if k in ("attempted_violations", "spacecraft_rejections", "voided_decisions",
                                       "system_refusals", "gate_bypasses", "flagged", "valid")},
                 "seat_changes": run.seat_changes,
                 "triggers": sorted({t["type"] for r in records if r["type"] == "TRIGGER"
                                     for t in r["body"]["triggers"]}),
                 "feeds_served": sorted({t["detail"]["feed"] for r in records if r["type"] == "TRIGGER"
                                         for t in r["body"]["triggers"] if t["type"] == "FEED_REPORT"}),
                 "check": check(LABEL, records, frames, truth)}
        stepped = {r["met_s"]: datetime.fromisoformat(r["utc"].replace("Z", "+00:00")) for r in truth
                   if r["type"] == "TRUE_STATE"}
        held_turn = next((r for r in records if r["type"] == "TRIGGER" and r["body"]["turn_id"] == HELD.get("turn_id")),
                         None)
        found["switch"] = {
            "held_turn": dict(HELD, served_met_s=held_turn["met_s"] if held_turn else None),
            "acquisition_met_s": aos,
            "ground_missed": [r["body"] for r in truth if r["type"] == "GROUND_MISSED"],
            "seconds_between_ticks_from_the_acquisition": [
                round((stepped[m + 1] - stepped[m]).total_seconds(), 3) for m in range(aos - 3, aos + 10)
                if m in stepped and m + 1 in stepped],
            "frames_sent_in_contact_2": sum(1 for r in truth if r["type"] == "TRUE_STATE" and r["met_s"] >= aos
                                            and r["body"].get("downlink") == "SENT"),
            "frames_received_in_contact_2": sum(1 for m in frames if m >= aos)}
        out = HELD_OUT / "standin-check"
        out.mkdir(exist_ok=True)
        (out / f"{LABEL}-switch-2026-10-31.json").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")
        print(json.dumps(found, indent=1, default=str), flush=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        print(f"deleted {root}: {not root.exists()}", flush=True)


if __name__ == "__main__":
    main()
