"""M1: spark_open answer-tool conversion on recorded responses, no network (§11.1)."""
import json

import pytest

from odin.adapters.spark_open import convert_tool_calls

RECORDED_ONE = [
    {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "answer_command",
            "arguments": json.dumps(
                {"command": "CMD_PLD_SET_STATE", "parameters": {"state": "ON"}, "rationale": "SoC allows it."}
            ),
        },
    }
]


def test_one_answer_call_becomes_object():
    ok, obj, reason, _ = convert_tool_calls(RECORDED_ONE, turn_kind="ACT")
    assert ok and reason is None
    assert obj == {
        "kind": "command",
        "command": "CMD_PLD_SET_STATE",
        "parameters": {"state": "ON"},
        "rationale": "SoC allows it.",
    }


def test_readonly_calls_then_one_answer_is_fine():
    calls = [
        {"id": "c0", "type": "function", "function": {"name": "docs_lookup", "arguments": '{"q":"payload"}'}},
        RECORDED_ONE[0],
    ]
    ok, obj, _, _ = convert_tool_calls(calls, turn_kind="ACT")
    assert ok and obj["kind"] == "command"


def test_no_answer_call_is_malformed():
    ok, _, reason, _ = convert_tool_calls([], turn_kind="ACT")
    assert not ok and reason == "ANSWER_TOOL_CALL_COUNT"
    only_readonly = [
        {"id": "c0", "type": "function", "function": {"name": "history", "arguments": '{"points":"EPS_BATT_SOC"}'}}
    ]
    ok, _, reason, _ = convert_tool_calls(only_readonly, turn_kind="ACT")
    assert not ok and reason == "ANSWER_TOOL_CALL_COUNT"


def test_two_answer_calls_is_malformed():
    ok, _, reason, _ = convert_tool_calls(RECORDED_ONE + RECORDED_ONE, turn_kind="ACT")
    assert not ok and reason == "ANSWER_TOOL_CALL_COUNT"


@pytest.mark.parametrize(
    "bad_args, expected",
    [
        # U58: outside the dictionary is NOT_IN_DICTIONARY, through spark_open too.
        ({"command": "CMD_NOPE", "parameters": {}}, "NOT_IN_DICTIONARY"),
        ({"command": "CMD_PLD_SET_STATE", "parameters": {"state": "MAYBE"}}, "NOT_IN_DICTIONARY"),
        ({"command": "CMD_PLD_SET_STATE"}, "SCHEMA_VIOLATION"),
        ({"parameters": {"state": "ON"}}, "SCHEMA_VIOLATION"),
        ({"command": "CMD_PLD_SET_STATE", "parameters": {"state": "ON"}, "request_id": "forged"},
         "SCHEMA_VIOLATION"),
    ],
)
def test_wrong_fields_are_malformed(bad_args, expected):
    calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "answer_command", "arguments": json.dumps(bad_args)},
        }
    ]
    ok, _, reason, _ = convert_tool_calls(calls, turn_kind="ACT")
    assert not ok and reason == expected


def test_reasoning_content_is_never_the_answer():
    ok, _, reason, _ = convert_tool_calls([], turn_kind="ACT", reasoning_content='{"kind":"none"}')
    assert not ok and reason == "ANSWER_TOOL_CALL_COUNT"


def test_report_tool_on_report_turn():
    body = {
        "timeline": [],
        "actions": [],
        "condition": {"summary": "Nominal.", "evidence": []},
        "deferred": [],
        "open_issues": [],
        "answer": "All nominal.",
    }
    calls = [
        {"id": "c1", "type": "function", "function": {"name": "answer_report", "arguments": json.dumps(body)}}
    ]
    ok, obj, _, _ = convert_tool_calls(calls, turn_kind="REPORT", report_kind="CHECK_IN")
    assert ok and obj["answer"] == "All nominal."
    ok, _, reason, _ = convert_tool_calls(calls, turn_kind="ACT")
    assert not ok and reason == "WRONG_FORM_FOR_TURN"
