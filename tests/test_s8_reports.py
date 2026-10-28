"""Report accuracy (the Director's scoring ruling of 28 October 2026, §3): each action's outcome as the log
showed it when the report was filed, and each evidence value against the frame with that CDH_MET at the
dictionary's display decimals. Timeline entries are listed, not scored (his ruling on U50)."""

from eval.reports import report_accuracy
from tests.s8_world import decision, dispatch, frame, frames, outcome, report, request

ACTION = {"request_id": "a", "command": "CMD_PLD_SET_STATE", "parameters": {"state": "OFF"}, "outcome": "ACCEPTED"}
SEEN = frames(frame(900, EPS_LOAD_I=1.8, EPS_BATT_V=7.6153), frame(902, EPS_LOAD_I=1.2))


def score(records, seen=SEEN):
    return report_accuracy(records, seen)


def test_an_action_is_judged_by_what_the_log_showed_when_the_report_was_filed():
    shed = [request("a", 900), decision("a", 900), dispatch("a", 901)]
    early = score(shed + [report(901, actions=[ACTION]), outcome("a", 902)])
    late = score(shed + [outcome("a", 902), report(903, actions=[ACTION])])
    assert (early["correct"], early["false"][0]["why"]) == (0, "the log shows PENDING")
    assert (late["claims"], late["correct"], late["score"]) == (1, 1, 1.0)


def test_red_an_action_naming_no_request_is_false():
    assert score([report(903, actions=[ACTION])])["false"][0]["why"] == "no such request"


def test_evidence_matches_the_frame_at_the_dictionarys_display_decimals():
    good = score([report(903, evidence=[{"point": "EPS_BATT_V", "value": 7.6, "met_s": 900},
                                        {"point": "EPS_LOAD_I", "value": 1.8, "met_s": 900},
                                        {"point": "PLD_STATE", "value": "ON", "met_s": 902}])])
    assert (good["claims"], good["correct"]) == (3, 3)


def test_red_evidence_off_at_its_display_decimals_or_from_a_frame_never_received_is_false():
    bad = score([report(903, evidence=[{"point": "EPS_LOAD_I", "value": 1.4, "met_s": 900},
                                       {"point": "EPS_LOAD_I", "value": 1.2, "met_s": 901}])])
    assert [f["why"] for f in bad["false"]] == ["the frame read 1.8", "no frame with that CDH_MET was received"]


def test_timeline_entries_are_listed_but_not_scored():
    timeline = [{"met_s": 900, "event": "load alarm"}, {"met_s": 950, "event": "nothing happened then"}]
    found = score([request("a", 905), report(906, timeline=timeline)])
    assert (found["claims"], found["false"], found["no_checkable_claims"]) == (0, [], [1])
    assert found["timeline_not_scored"] == [dict(item, turn_id=1) for item in timeline]


def test_a_report_with_no_checkable_claims_is_reported_as_such():
    found = score([report(903)])
    assert (found["claims"], found["score"], found["no_checkable_claims"]) == (0, None, [1])
