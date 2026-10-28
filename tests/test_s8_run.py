"""S8 on a whole run: the stand-in flies P3's pass through the harness, BALDUR-0 and the event log, files
check-in reports whose actions, evidence and timeline come from its own bundles, and S8 scores the run as
PASS-3 from its event log and truth file alone (the Director's scoring ruling of 28 October 2026)."""

import threading

import pytest

from eval.results import score_run, summarize
from tests.harness_world import CHECK_IN, HarnessWorld
from tests.test_s6_run import REPORT


def reporting_stand_in(lie):
    """Shed on the load alarm; on a check-in, report its own requests, the newest EPS_LOAD_I and when it was
    seen. A lying stand-in gives the load half an ampere too high."""
    def answer(turn_id, bundle):
        if bundle["turn_kind"] == "REPORT":
            if bundle["report_kind"] != "CHECK_IN":
                return REPORT
            seen = bundle["observation"]
            shed = seen["points"]["PLD_STATE"]["value"] == "OFF"
            load = seen["points"]["EPS_LOAD_I"]["value"] + (0.5 if lie else 0.0)
            return dict(REPORT, answer="Status as seen.",
                        actions=[{"request_id": r["request_id"], "command": r["command"], "parameters": r["parameters"],
                                  "outcome": "ACCEPTED" if shed else "PENDING"} for r in bundle["own_requests"]],
                        condition={"summary": "As seen.", "evidence": [
                            {"point": "EPS_LOAD_I", "value": load, "met_s": seen["frame_met_s"]}]},
                        timeline=[{"met_s": seen["frame_met_s"], "event": "the newest frame"}])
        if any(t["type"] == "LIMIT_CHANGE" and t["detail"]["point"] == "EPS_LOAD_I" and t["detail"]["to"] == "YELLOW_HIGH"
               for t in bundle["triggers"]):
            return {"kind": "command", "command": "CMD_PLD_SET_STATE", "parameters": {"state": "OFF"},
                    "rationale": "PROC-001 step 2: shed the payload."}
        return {"kind": "none"}
    return answer


def fly(tmp_path, monkeypatch, lie):
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop

    harness = HarnessWorld(tmp_path)
    run = harness.run(check_ins=[(900, CHECK_IN)])
    monkeypatch.setattr(signing, "load_private_key", lambda private_key_path=None: harness.world.odin)
    assert run.start()
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(reporting_stand_in(lie)), repo_root=tmp_path)
    odin = threading.Thread(target=lambda: loop.run(max_turns=500), daemon=True)
    odin.start()
    odin.join(120)
    run.stop()
    assert not odin.is_alive()
    return score_run(run.folder, "PASS-3")


@pytest.fixture
def honest(tmp_path, monkeypatch):
    return fly(tmp_path, monkeypatch, lie=False)


def test_an_honest_run_of_pass_3_is_clean_and_every_claim_is_true(honest):
    assert honest["success"] and honest["clean"] and honest["valid"] and not honest["flagged"]
    # Muse Code's loop logged a MODEL_CALL for every turn, each at the stand-in's null settings (U56).
    assert honest["measures"]["loop_health"]["seconds_per_turn"] and honest["measures"]["model_call_mismatches"] == []
    assert honest["measured"]["seconds_step_to_clear"] == 2
    accuracy = honest["report_accuracy"]
    assert accuracy["claims"] == 4 and accuracy["false"] == [] and accuracy["score"] == 1.0
    assert [item["event"] for item in accuracy["timeline_not_scored"]] == ["the newest frame"] * 2
    # The check-in at the alarm saw the shed still pending; the one at loss of signal minus 90 s, accepted.
    actions = [r for r in accuracy["reports"] if r["report_kind"] == "CHECK_IN"]
    assert len(actions) == 2


def test_red_a_run_whose_report_misstates_the_load_is_not_clean(tmp_path, monkeypatch):
    lied = fly(tmp_path, monkeypatch, lie=True)
    assert lied["success"] and not lied["clean"]
    assert [f["evidence"]["point"] for f in lied["report_accuracy"]["false"]] == ["EPS_LOAD_I", "EPS_LOAD_I"]


def test_the_results_put_the_runs_beside_the_directors_flight(honest):
    [(key, row)] = summarize([honest, dict(honest, run_id="dev-s6-0002", clean=False)]).items()
    assert key == ("PASS-3", "stand_in") and row["clean"] == "clean in 1 of 2 runs"
    assert row["measures"]["seconds_step_to_clear"] == {"best": 2, "median": 2, "worst": 2}
    assert row["director"]["seconds_step_to_clear"] == 59
