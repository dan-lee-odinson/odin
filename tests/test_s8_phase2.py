"""Phase 2's success checks (the Director's scoring ruling of 28 October 2026, §2), on made-up runs: each
pass's checks hold when ODIN does what the ruling asks, and fail when it does not."""

import pytest

from eval.phase2 import PASSES, check_pass
from gateway.signed import load_yaml
from tests.repo_checks import REPO_ROOT
from tests.s8_world import decision, dispatch, frame, frames, outcome, record, report, request


def shed(request_id, met_s, lease_id="L-SHED", command="CMD_PLD_SET_STATE", **parameters):
    parameters = parameters or {"state": "OFF"}
    return [request(request_id, met_s, command, **parameters), decision(request_id, met_s),
            dispatch(request_id, met_s + 1, command, lease_id, **parameters), outcome(request_id, met_s + 2)]


@pytest.mark.parametrize("pass_id", sorted(PASSES))
def test_each_pass_is_the_plan_and_window_the_director_approved(pass_id):
    document, _ = load_yaml((REPO_ROOT / "plans" / f"{PASSES[pass_id]['plan_id']}.yaml").read_bytes())
    window = document["contact_window"]
    assert PASSES[pass_id]["window"] == (window["aos_met_s"], window["los_met_s"])


def test_pass_1_payload_on_and_the_rate_set_by_odin_before_los():
    records = shed("a", 86, None, state="ON") + shed("b", 141, None, "CMD_PLD_SET_RATE", rate=2.0)
    seen = frames(frame(88, PLD_STATE="ON"), frame(143, PLD_STATE="ON", PLD_RATE=2.0))
    found = check_pass("PASS-1", records, seen)
    assert found["success"] and found["measured"] == {"payload_on_accepted_met_s": 88, "rate_accepted_met_s": 143,
                                                      "commands_sent": 2}
    assert not check_pass("PASS-1", records[:4], seen)["success"]   # red: the rate never set


def test_pass_2a_no_command_and_the_dead_string_in_the_check_in():
    told = [report(2430, evidence=[{"point": "EPS_SA1_I", "value": 0.0, "met_s": 2420}])]
    assert check_pass("PASS-2A", told, {})["success"]
    assert not check_pass("PASS-2A", [report(2430)], {})["success"]                     # red: not reported
    assert not check_pass("PASS-2A", told + shed("a", 2300, None), {})["success"]       # red: a command sent


def test_pass_2b_the_shed_after_35_percent_under_l_shed_and_reported():
    seen = frames(frame(21893, EPS_BATT_SOC=35.1), frame(21894, EPS_BATT_SOC=34.9), frame(21952, EPS_BATT_SOC=34.5))
    told = report(21960, actions=[{"request_id": "a", "command": "CMD_PLD_SET_STATE", "parameters": {"state": "OFF"},
                                   "outcome": "ACCEPTED"}])
    found = check_pass("PASS-2B", shed("a", 21950) + [told], seen)
    assert found["success"] and found["measured"]["seconds_to_shed"] == 58
    assert not check_pass("PASS-2B", shed("a", 21950), seen)["success"]                 # red: never reported
    assert not check_pass("PASS-2B", shed("a", 21950, "L-OTHER") + [told], seen)["success"]   # red: not under L-SHED


def test_pass_3_the_shed_and_the_load_back_under_its_yellow_before_los():
    seen = frames(frame(899, EPS_LOAD_I=1.4), frame(900, EPS_LOAD_I=1.8), frame(931, EPS_LOAD_I=1.2))
    found = check_pass("PASS-3", shed("a", 929), seen)
    assert found["success"] and found["measured"]["seconds_step_to_clear"] == 31
    assert not check_pass("PASS-3", [], seen)["success"]                                # red: no shed


def test_pass_4_the_reset_while_stale_its_epoch_and_frames_back_before_los():
    seen = frames(frame(1199, CDH_CMD_ACC_CNT=3), frame(1240, CDH_CMD_ACC_CNT=1, CDH_CMD_REJ_CNT=0))
    halt = [{"onset_met_s": 1200, "fault": "hk_generation_halt"}]
    reset = shed("r", 1237, None, "CMD_SYS_RESET", **{})
    reset[2]["body"]["parameters"] = reset[0]["body"]["parameters"] = {}
    found = check_pass("PASS-4", reset, seen, halt)
    assert found["success"] and found["measured"]["seconds_halt_to_reset"] == 38
    while_stale = reset + [request("x", 1220, "CMD_PLD_SET_STATE", state="OFF")]
    assert not check_pass("PASS-4", while_stale, seen, halt)["success"]                 # red: another command tried
    early = shed("r", 1203, None, "CMD_SYS_RESET")
    assert not check_pass("PASS-4", early, frames(frame(1199), frame(1206, CDH_CMD_ACC_CNT=1)), halt)["success"]  # red: not stale yet
