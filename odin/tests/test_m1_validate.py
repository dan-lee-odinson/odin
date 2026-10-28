"""M1: answer checking (CONTRACT §7.1, §7.2, §16.5). Every malformed form rejected."""
import json

import pytest

from odin.loop.validate import validate_act_text, validate_report_text


def act(raw: str):
    return validate_act_text(raw)


def test_valid_command_accepted():
    ok, obj, reason, _ = act('{"kind":"command","command":"CMD_PLD_SET_STATE","parameters":{"state":"ON"}}')
    assert ok and obj["kind"] == "command" and reason is None


def test_valid_none_and_escalation_accepted():
    ok, _, _, _ = act('{"kind":"none"}')
    assert ok
    ok, _, _, _ = act(
        '{"kind":"escalation","escalation_kind":"MALFUNCTION","refs":[],"proposed":null,"urgency":"ROUTINE"}'
    )
    assert ok


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json at all",
        "```json\n{\"kind\":\"none\"}\n```",
        '{"kind":"none"} trailing text',
        'prefix {"kind":"none"}',
        '{"kind":"none"}{"kind":"none"}',
        '[{"kind":"none"}]',
        '"just a string"',
        "42",
        "null",
    ],
)
def test_not_one_json_object(raw):
    ok, _, reason, _ = act(raw)
    assert not ok and reason == "NOT_ONE_JSON_OBJECT"


@pytest.mark.parametrize(
    "raw",
    [
        '{"kind":"command","command":"CMD_PLD_SET_STATE"}',
        '{"kind":"command","command":"CMD_PLD_SET_STATE","parameters":{"state":"ON"},"extra":1}',
        '{"kind":"escalation","escalation_kind":"WHATEVER","refs":[],"proposed":null,"urgency":"ROUTINE"}',
        '{"kind":"escalation","escalation_kind":"MALFUNCTION","refs":[],"proposed":null,"urgency":"WHENEVER"}',
        '{"kind":"escalation","escalation_kind":"MALFUNCTION","refs":"oops","proposed":null,"urgency":"ROUTINE"}',
        '{"kind":"none","surprise":true}',
        '{"kind":"unknown"}',
        '{"command":"CMD_PLD_SET_STATE","parameters":{"state":"ON"}}',
    ],
)
def test_schema_violations(raw):
    ok, _, reason, _ = act(raw)
    assert not ok and reason == "SCHEMA_VIOLATION"


@pytest.mark.parametrize(
    "raw",
    [
        # U58: outside the dictionary in force is NOT_IN_DICTIONARY, never
        # SCHEMA_VIOLATION, and the dictionary check runs first.
        '{"kind":"command","command":"CMD_NOPE","parameters":{}}',
        '{"kind":"command","command":"CMD_PLD_SET_STATE","parameters":{"state":"MAYBE"}}',
        '{"kind":"command","command":"CMD_PLD_SET_STATE","parameters":{"state":"ON","rate":1.0}}',
        '{"kind":"command","command":"CMD_PLD_SET_RATE","parameters":{"rate":99.0}}',
        '{"kind":"command","command":"CMD_PLD_SET_RATE","parameters":{"rate":0.01}}',
        '{"kind":"command","command":"CMD_SAFE_ENTER","parameters":{"x":1}}',
        '{"kind":"command","command":"CMD_MODE_SET","parameters":{"target":"SAFE"}}',
        '{"kind":"escalation","escalation_kind":"MALFUNCTION","refs":[],"proposed":{"command":"CMD_NOPE","parameters":{}},"urgency":"ROUTINE"}',
    ],
)
def test_not_in_dictionary(raw):
    ok, _, reason, _ = act(raw)
    assert not ok and reason == "NOT_IN_DICTIONARY"


@pytest.mark.parametrize(
    "field",
    ["request_id", "origin", "nonce", "signature", "run_id", "turn_id", "plan_id", "agent_input_hash", "utc", "met_s"],
)
def test_model_never_sets_loop_fields(field):
    payload = {"kind": "none", field: "forged"}
    ok, _, reason, _ = act(json.dumps(payload))
    assert not ok and reason == "SCHEMA_VIOLATION"


def test_report_body_valid_and_wrong_form():
    good = {
        "timeline": [{"met_s": 100, "event": "Pass started."}],
        "actions": [],
        "condition": {"summary": "Nominal.", "evidence": []},
        "deferred": [],
        "open_issues": [],
    }
    ok, _, reason, _ = validate_report_text(json.dumps(good), report_kind="PASS_START")
    assert ok
    # A command answer on a REPORT turn is the wrong form.
    ok, _, reason, _ = validate_report_text(
        '{"kind":"command","command":"CMD_SAFE_ENTER","parameters":{}}', report_kind="PASS_START"
    )
    assert not ok and reason == "WRONG_FORM_FOR_TURN"


def test_act_rejects_report_body():
    body = {
        "timeline": [],
        "actions": [],
        "condition": {"summary": "x", "evidence": []},
        "deferred": [],
        "open_issues": [],
    }
    ok, _, reason, _ = act(json.dumps(body))
    assert not ok and reason in ("SCHEMA_VIOLATION", "WRONG_FORM_FOR_TURN")


def test_checkin_requires_answer_others_forbid_it():
    base = {
        "timeline": [],
        "actions": [],
        "condition": {"summary": "Nominal.", "evidence": []},
        "deferred": [],
        "open_issues": [],
    }
    ok, _, reason, _ = validate_report_text(json.dumps(base), report_kind="CHECK_IN")
    assert not ok and reason == "SCHEMA_VIOLATION"
    with_answer = dict(base, answer="All nominal.")
    ok, _, _, _ = validate_report_text(json.dumps(with_answer), report_kind="CHECK_IN")
    assert ok
    ok, _, reason, _ = validate_report_text(json.dumps(with_answer), report_kind="PASS_START")
    assert not ok and reason == "SCHEMA_VIOLATION"
