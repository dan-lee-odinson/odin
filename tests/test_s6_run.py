"""S6's run, done when (00_HANDOFF.md §4): a stand-in run of a full pass, with a check-in landing on an
alarm, runs the action turn first and the report next.

ODIN here is Muse Code's own turn loop with its stand-in adapter (CONTRACT.md §11.4), talking HTTP to
the harness, BALDUR-0 and the event log as it would in a run. The pass is P3's, MET 800 to 1230 as the
Director flew it: the payload is ON from before contact, the stuck load raises EPS_LOAD_I to its yellow
high limit at MET 900, and a recorded check-in plays at that same tick. The run sits in the onboard
seat with CHARGED pacing, so it needs no COSMOS and runs faster than real time; every key is made in
memory, and the plan and act are signed with the development test key. When it stops, its folder moves
from runs/<run_id>/ to runs/dev/<run_id>/ (U46).
"""

import json
import threading

import pytest

from contract.validate import check
from harness.checkins import WORDS
from log.event_log import verify_event_log, verify_truth
from tests.harness_world import CHECK_IN, PASS_PLAN, PASS_PLAN_SHA256, PROCEDURE, HarnessWorld

REPORT = {"timeline": [], "actions": [], "condition": {"summary": "Load current high; payload being shed.",
                                                        "evidence": []}, "deferred": [], "open_issues": []}


def stand_in(seen):
    """Scripted answers: shed the payload on the load-current alarm, a report on every report turn,
    no action otherwise."""
    def answer(turn_id, bundle):
        seen.append(bundle)
        if bundle["turn_kind"] == "REPORT":
            return dict(REPORT, answer="The load current crossed its yellow limit.") \
                if bundle["report_kind"] == "CHECK_IN" else REPORT
        if any(t["type"] == "LIMIT_CHANGE" and t["detail"] == {"point": "EPS_LOAD_I", "from": "GREEN",
                                                               "to": "YELLOW_HIGH"} for t in bundle["triggers"]):
            return {"kind": "command", "command": "CMD_PLD_SET_STATE", "parameters": {"state": "OFF"},
                    "rationale": "PROC-001 step 2: shed the payload."}
        return {"kind": "none"}
    return answer


@pytest.fixture
def flown(tmp_path, monkeypatch):
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop

    harness = HarnessWorld(tmp_path)
    run = harness.run(check_ins=[(900, CHECK_IN)])
    monkeypatch.setattr(signing, "load_private_key", lambda private_key_path=None: harness.world.odin)
    assert run.start()
    seen = []
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(stand_in(seen)), repo_root=tmp_path)
    results = []
    odin = threading.Thread(target=lambda: results.extend(loop.run(max_turns=500)), daemon=True)
    odin.start()
    odin.join(120)
    run.stop()
    assert not odin.is_alive(), "ODIN's loop did not reach run_complete"
    records = [json.loads(line) for line in (run.folder / "events.jsonl").read_bytes().splitlines()]
    return run, seen, results, records


def kinds(bundle):
    return bundle["turn_kind"], bundle["report_kind"], [t["type"] for t in bundle["triggers"]]


def test_a_check_in_landing_on_an_alarm_runs_the_action_turn_first_and_the_report_next(flown):
    _, seen, _, _ = flown
    [alarm] = [b for b in seen if any(t["type"] == "LIMIT_CHANGE" and t["met_s"] == 900 for t in b["triggers"])]
    assert alarm["turn_kind"] == "ACT" and alarm["met_s"] == 900
    assert {"type": "LIMIT_CHANGE", "met_s": 900, "detail": {"point": "EPS_LOAD_I", "from": "GREEN",
                                                              "to": "YELLOW_HIGH"}} in alarm["triggers"]
    report, follow_up = seen[seen.index(alarm) + 1:seen.index(alarm) + 3]
    assert kinds(report) == ("REPORT", "CHECK_IN", ["CHECK_IN"])
    assert report["check_in_text"] == CHECK_IN["text"] and report["triggers"][0]["met_s"] == 900
    # The report waits only behind the action triggers that arrived before it or with it (U47): the
    # follow-up for ODIN's own shed, its DECISION, its OUTCOME and the load current back below its
    # limit, comes after it.
    assert kinds(follow_up) == ("ACT", None, ["DECISION", "LIMIT_CHANGE", "OUTCOME"])


def test_the_pass_opens_with_its_action_turn_then_its_pass_start_report(flown):
    _, seen, _, _ = flown
    assert kinds(seen[0]) == ("ACT", None, ["AOS"]) and seen[0]["met_s"] == 800
    assert kinds(seen[1]) == ("REPORT", "PASS_START", ["PLAN_START"])
    assert seen[0]["observation"]["points"]["PLD_STATE"]["value"] == "ON"   # kept from before contact (U35)


def test_odins_shed_goes_through_baldur0_and_its_outcome_is_read_from_telemetry(flown):
    _, _, results, records = flown
    [request] = [r["request"] for r in results if r["outcome"] == "request"]
    by_type = {t: [r["body"] for r in records if r["type"] == t] for t in ("DECISION", "DISPATCH", "OUTCOME")}
    assert [d["decision"] for d in by_type["DECISION"]] == ["ALLOW"]
    assert [d["route"] for d in by_type["DISPATCH"]] == ["UPLINK"]
    [outcome] = by_type["OUTCOME"]
    assert (outcome["request_id"], outcome["outcome"], outcome["point"]) == (
        request["request_id"], "ACCEPTED", {"mnemonic": "PLD_STATE", "value": "OFF"})


def test_every_bundle_served_is_the_one_odin_saved_and_conforms(flown):
    run, seen, _, records = flown
    served = {r["body"]["turn_id"]: r["body"]["bundle_sha256"] for r in records if r["type"] == "TRIGGER"}
    saved = {r["body"]["turn_id"]: r["body"]["bundle_sha256"] for r in records if r["type"] == "AGENT_INPUT"}
    assert served == saved and len(served) == len(seen)
    for turn_id, digest in served.items():
        bundle = json.loads((run.folder / "inputs" / digest.split(":")[1]).read_bytes())
        assert check("turn_bundle", bundle) == [], turn_id
    assert seen[-1]["procedures"][0]["text"] == PROCEDURE.decode()
    assert seen[-1]["history"]["columns"] == ["met_s", "EPS_BATT_SOC", "EPS_LOAD_I", "PLD_STATE"]


def test_the_plans_reference_rides_beside_proc_001_with_the_plans_hash(flown):
    _, seen, _, _ = flown
    assert all(b["procedures"][0]["attachments"] == [{"name": "Pass plan (made up)", "sha256": PASS_PLAN_SHA256,
                                                       "text": PASS_PLAN.decode()}] for b in seen)


def test_the_run_ends_in_runs_dev_and_leaves_nothing_in_runs(flown, tmp_path):
    run, _, _, _ = flown
    assert run.folder == tmp_path / "runs" / "dev" / run.run_id
    assert sorted(p.name for p in (tmp_path / "runs").iterdir()) == ["dev"]
    assert (run.folder / "inputs").is_dir()   # ODIN's inputs moved with the run (§16.1 U16)


def test_the_run_is_recorded_whole_from_run_start_to_run_end(flown):
    run, seen, _, records = flown
    assert verify_event_log(run.folder / "events.jsonl") == []
    assert verify_truth(run.folder / "truth.jsonl") == []
    assert records[0]["type"] == "RUN_START" and records[-1]["type"] == "RUN_END"
    assert records[-1]["body"] == {"reason": "COMPLETE", "turns": len(seen)}
    assert [r["body"]["state"] for r in records if r["type"] == "CONTACT"] == ["AOS", "LOS"]
    assert [r["body"]["text"] for r in records if r["type"] == "CHECK_IN"] == [CHECK_IN["text"], WORDS]


def test_the_pass_carries_the_directors_check_in_at_loss_of_signal_minus_90_s(flown):
    # The Director's scoring ruling of 28 October 2026, §4: as text until his recording is transcribed.
    _, seen, _, records = flown
    [report] = [b for b in seen if b["report_kind"] == "CHECK_IN" and b["triggers"][0]["met_s"] == 1140]
    assert (report["check_in_text"], report["met_s"]) == (WORDS, 1140)
    [logged] = [r for r in records if r["type"] == "CHECK_IN" and r["met_s"] == 1140]
    assert (logged["body"]["source"], logged["body"]["audio_sha256"]) == ("TEXT", None)
    assert check("checkin", logged["body"]) == []
