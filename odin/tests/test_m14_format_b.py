"""M14: spark format B, exact CANDIDATE log, spark_open amended rule.

Red cases are the assertions below: each was shown failing against the
M11/M13 code before M14 changed it.
"""
import hashlib
import json

import pytest

from odin.adapters.spark import SparkAdapter, act_format, drop_nulls
from odin.adapters.spark_open import ANSWER_TOOLS, SparkOpenAdapter, convert_message
from odin.devtools.fake_harness import FakeServices
from odin.loop.loop import TurnLoop, put_back_command_call
from odin.loop.validate import dictionary_for_plan, validate_act_text, validate_against_schema
from conftest import REPO_ROOT, bundle_bytes, make_bundle

INST_REF = "sha256:1a113f774b043bc3a0939a8285e61475a35d3d268792b71f29fa8c7bae0ab53c"
BANNED = {"oneOf", "allOf", "if", "then", "$ref"}


def _commands(*refs):
    plan = {"plan_id": "P", "references": [{"name": f"r{i}", "sha256": r} for i, r in enumerate(refs)]}
    return dictionary_for_plan(plan)[1]


def _keys(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        for k, v in node.items():
            found.add(k)
            _keys(v, found)
    elif isinstance(node, list):
        for v in node:
            _keys(v, found)
    return found


def _judge(raw, commands):
    """The loop's parse: put back, M11 null drop, frozen + dictionary."""
    try:
        obj = json.loads(raw)
    except Exception as exc:
        return False, None, "NOT_ONE_JSON_OBJECT", str(exc)
    if not isinstance(obj, dict):
        return False, None, "NOT_ONE_JSON_OBJECT", "not an object"
    judged = drop_nulls(put_back_command_call(obj))
    return validate_act_text(json.dumps(judged), commands=commands)


def _spark(reply, captured=None, bundle=None):
    def fake_post(url, headers, payload, timeout):
        if captured is not None:
            captured.update(payload)
        return 200, {"choices": [{"finish_reason": "stop", "message": {"content": reply}}], "usage": {}}
    adapter = SparkAdapter(reasoning_effort="low", max_output_tokens=10,
                           timeout_s=5, api_key="test-only", http_post=fake_post)
    return adapter.complete(prompt=b"p", bundle=bundle or make_bundle(1, turn_kind="ACT"))


def _inst_bundle():
    bundle = make_bundle(1, turn_kind="ACT")
    bundle["plan"]["references"].append({"name": "INST dictionary", "sha256": INST_REF})
    return bundle


# -- format B -----------------------------------------------------------------

def test_format_b_equals_huginn_file_as_parsed_json():
    expected = json.loads((REPO_ROOT / "contract" / "m14" / "format-B-HUGINN.json").read_text(encoding="utf-8"))
    assert act_format(_commands()) == expected


def test_format_b_equals_inst_file_as_parsed_json():
    expected = json.loads((REPO_ROOT / "contract" / "m14" / "format-B-INST.json").read_text(encoding="utf-8"))
    assert act_format(_commands(INST_REF)) == expected


def test_format_b_has_no_banned_keys_and_anyof_per_command():
    fmt = act_format(_commands())
    assert not (BANNED & _keys(fmt))
    branches = fmt["properties"]["command_call"]["anyOf"][0]["anyOf"]
    assert [b["properties"]["command"]["enum"] for b in branches] == [
        ["CMD_PLD_SET_STATE"], ["CMD_PLD_SET_RATE"], ["CMD_SAFE_ENTER"],
        ["CMD_SYS_RESET"], ["CMD_MODE_SET"]]
    assert branches[0]["properties"]["parameters"]["required"] == ["state"]
    assert branches[2]["properties"]["parameters"] == {
        "type": "object", "additionalProperties": False, "required": [], "properties": {}}
    assert fmt["properties"]["proposed"] == fmt["properties"]["command_call"]


def test_spark_sends_format_b_not_m11_shared_format():
    captured = {}
    _spark('{"kind":"none"}', captured)
    fmt = captured["response_format"]["json_schema"]["schema"]
    assert "command_call" in fmt["properties"]
    assert "command" not in fmt["properties"] and "parameters" not in fmt["properties"]


def test_format_b_built_from_dictionary_in_force_not_another():
    captured = {}
    _spark('{"kind":"none"}', captured, bundle=_inst_bundle())
    fmt = captured["response_format"]["json_schema"]["schema"]
    expected = json.loads((REPO_ROOT / "contract" / "m14" / "format-B-INST.json").read_text(encoding="utf-8"))
    assert fmt == expected
    captured2 = {}
    _spark('{"kind":"none"}', captured2)
    assert captured2["response_format"]["json_schema"]["schema"] != expected


def test_cmd_pld_set_state_with_rate_fails_format_b():
    fmt = act_format(_commands())
    bad = {"kind": "command",
           "command_call": {"command": "CMD_PLD_SET_STATE",
                            "parameters": {"state": "OFF", "rate": 1.0}},
           "escalation_kind": None, "refs": None, "urgency": None,
           "rationale": "x", "proposed": None}
    from odin.loop.validate import validate_instance
    assert validate_instance(bad, fmt, "format-b") != []


# -- put back, null drop, judging ----------------------------------------------

def test_put_back_then_null_drop_then_judged():
    raw = ('{"kind":"command","command_call":{"command":"CMD_PLD_SET_STATE",'
           '"parameters":{"state":"OFF"}},"escalation_kind":null,"refs":null,'
           '"urgency":null,"rationale":"shed","proposed":null}')
    ok, obj, reason, detail = _judge(raw, _commands())
    assert ok, (reason, detail)
    assert obj == {"kind": "command", "command": "CMD_PLD_SET_STATE",
                   "parameters": {"state": "OFF"}, "rationale": "shed"}


def test_argument_command_does_not_take_is_refused_not_dropped():
    raw = ('{"kind":"command","command_call":{"command":"CMD_PLD_SET_STATE",'
           '"parameters":{"state":"OFF","rate":2.0}},"escalation_kind":null,'
           '"refs":null,"urgency":null,"rationale":null,"proposed":null}')
    ok, obj, reason, detail = _judge(raw, _commands())
    assert not ok and reason == "NOT_IN_DICTIONARY" and "rate" in detail
    assert obj is None  # nothing repaired into an accepted answer


def test_answers_b_judged_exactly_as_recorded():
    records = json.loads((REPO_ROOT / "contract" / "m14" / "answers-B.json").read_text(encoding="utf-8"))
    assert len(records) == 4
    for rec in records:
        commands = _commands(INST_REF) if rec["dictionary"] == "INST" else _commands()
        ok, obj, reason, detail = _judge(rec["content_verbatim"], commands)
        recorded = rec["judged_after_put_back_and_null_drop"]
        if recorded["loop"] == "accepted":
            assert ok, (rec["prompt"], reason, detail)
        else:
            assert not ok
            assert reason == "SCHEMA_VIOLATION"
            assert recorded["frozen_schema"] != "passes"
            # the urgency on a command answer is kept, so frozen refuses it
            judged = drop_nulls(put_back_command_call(json.loads(rec["content_verbatim"])))
            assert judged.get("urgency") == "ROUTINE"
            assert validate_against_schema("answer.schema.json", judged) != []


def test_spark_adapter_returns_text_exactly_and_loop_candidate_is_exact(tmp_path, keypair):
    verbatim = ('{  "kind" : "none" ,  "command_call" : null , "escalation_kind":null,'
                '"refs":null,"urgency":null,"rationale":"wait","proposed":null }')
    result = _spark(verbatim)
    assert result["raw"] == verbatim  # never re-serialized by the adapter

    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    services.start()

    class Stub:
        name = "spark"
        def complete(self, *, prompt, bundle, **kw):
            return {"raw": verbatim, "channel": "CONTENT", "status": "OK"}

    loop = TurnLoop(harness_url=services.url, baldur_url=services.url, log_url=services.url,
                    adapter=Stub(), repo_root=tmp_path, transport=services.transport,
                    private_key_path=str(keypair["priv"]), instructions="x")
    try:
        results = loop.run(max_turns=3)
    finally:
        services.stop()
    assert results[0]["outcome"] == "none", results
    cand = [r["body"] for r in services.log_records if r["type"] == "CANDIDATE"]
    assert cand and cand[0]["raw"] == verbatim and cand[0]["channel"] == "CONTENT"
    ans = [r["body"] for r in services.log_records if r["type"] == "ANSWER"]
    assert ans and ans[0]["answer"] == {"kind": "none", "rationale": "wait"}


# -- spark_open amended rule ----------------------------------------------------

def _call(name, args):
    return {"id": "c1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def test_spark_open_one_answer_tool_call_is_the_answer():
    ok, obj, reason, _ = convert_message(
        None, [_call("answer_command", {"command": "CMD_PLD_SET_STATE",
                                        "parameters": {"state": "ON"}, "rationale": "ok"})],
        turn_kind="ACT", commands=_commands())
    assert ok and obj["command"] == "CMD_PLD_SET_STATE"


def test_spark_open_json_in_content_with_no_answer_tool():
    ok, obj, reason, detail = convert_message(
        '  {"kind":"none","rationale":"wait"}  ', [], turn_kind="ACT", commands=_commands())
    assert ok and obj == {"kind": "none", "rationale": "wait"}


@pytest.mark.parametrize("content", [
    '```json\n{"kind":"none"}\n```',
    '{"kind":"none"} {"kind":"none"}',
    'here is my answer: {"kind":"none"}',
    '{"kind":"none"} thanks',
    'no json at all',
])
def test_spark_open_content_malformed_forms(content):
    ok, _, reason, _ = convert_message(content, [], turn_kind="ACT", commands=_commands())
    assert not ok and reason == "NOT_ONE_JSON_OBJECT"


def test_spark_open_two_answer_tool_calls_malformed():
    calls = [_call("answer_none", {}), _call("answer_none", {})]
    ok, _, reason, _ = convert_message(None, calls, turn_kind="ACT", commands=_commands())
    assert not ok and reason == "ANSWER_TOOL_CALL_COUNT"


def test_spark_open_reasoning_content_never_answer():
    ok, _, reason, _ = convert_message(
        "", [], turn_kind="ACT", reasoning_content='{"kind":"none"}', commands=_commands())
    assert not ok
    ok, _, reason, _ = convert_message(
        None, [], turn_kind="ACT", reasoning_content='{"kind":"none"}', commands=_commands())
    assert not ok


def test_spark_open_wrong_fields_in_content_malformed():
    ok, _, reason, _ = convert_message(
        '{"kind":"none","request_id":"forged"}', [], turn_kind="ACT", commands=_commands())
    assert not ok and reason == "SCHEMA_VIOLATION"


def test_spark_open_adapter_candidate_is_message_exact():
    message = {"role": "assistant", "content": ' {"kind":"none","rationale":"wait"} ',
               "tool_calls": []}
    def fake_post(url, headers, payload, timeout):
        return 200, {"choices": [{"finish_reason": "stop", "message": message}], "usage": {}}
    adapter = SparkOpenAdapter(reasoning_effort="low", max_output_tokens=10,
                               timeout_s=5, api_key="test-only", http_post=fake_post)
    result = adapter.complete(prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"))
    assert result["channel"] == "MESSAGE"
    assert json.loads(result["raw"]) == {"content": message["content"], "tool_calls": []}


def test_spark_open_tools_typed_from_frozen_forms():
    by_name = {t["function"]["name"]: t["function"]["parameters"] for t in ANSWER_TOOLS}
    assert set(by_name) == {"answer_command", "answer_escalation", "answer_none", "answer_report"}
    esc = by_name["answer_escalation"]
    assert esc["properties"]["escalation_kind"]["enum"] == [
        "OFF_COURSE", "MALFUNCTION", "DECISION_NEEDED", "LEASE_NEEDED", "AUTHORITY_NEEDED", "CONFLICT"]
    assert esc["properties"]["urgency"]["enum"] == ["ROUTINE", "URGENT"]
    assert esc["properties"]["refs"]["items"] == {"type": "string"}
    rep = by_name["answer_report"]
    timeline_items = rep["properties"]["timeline"]["items"]
    assert timeline_items["properties"]["event"] == {"type": "string"}
    assert timeline_items["properties"]["met_s"]["type"] == "number"
    assert set(timeline_items["required"]) == {"met_s", "event"}
    assert rep["properties"]["open_issues"]["items"] == {"type": "string"}
    assert "$ref" not in json.dumps(ANSWER_TOOLS)


def test_spark_open_report_turn_via_content_and_tool_unchanged():
    body = {"timeline": [], "actions": [], "condition": {"summary": "Nominal.", "evidence": []},
            "deferred": [], "open_issues": [], "answer": "Nominal."}
    ok, obj, _, _ = convert_message(json.dumps(body), [], turn_kind="REPORT", report_kind="CHECK_IN")
    assert ok and obj["answer"] == "Nominal."
    ok, obj, _, _ = convert_message(None, [_call("answer_report", body)],
                                    turn_kind="REPORT", report_kind="CHECK_IN")
    assert ok and obj["answer"] == "Nominal."


def test_loop_message_channel_candidate_and_judgement(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    services.start()
    raw_message = json.dumps({"content": ' {"kind":"none","rationale":"wait"} ', "tool_calls": []})

    class Stub:
        name = "spark_open"
        def complete(self, *, prompt, bundle, **kw):
            return {"raw": raw_message, "channel": "MESSAGE", "status": "OK"}

    loop = TurnLoop(harness_url=services.url, baldur_url=services.url, log_url=services.url,
                    adapter=Stub(), repo_root=tmp_path, transport=services.transport,
                    private_key_path=str(keypair["priv"]), instructions="x")
    try:
        results = loop.run(max_turns=3)
    finally:
        services.stop()
    assert results[0]["outcome"] == "none", results
    cand = [r["body"] for r in services.log_records if r["type"] == "CANDIDATE"]
    assert cand[0]["channel"] == "MESSAGE" and cand[0]["raw"] == raw_message


def test_loop_message_two_objects_is_malformed_and_sends_nothing(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    services.start()
    raw_message = json.dumps({"content": '{"kind":"none"} {"kind":"none"}', "tool_calls": []})

    class Stub:
        name = "spark_open"
        def complete(self, *, prompt, bundle, **kw):
            return {"raw": raw_message, "channel": "MESSAGE", "status": "OK"}

    loop = TurnLoop(harness_url=services.url, baldur_url=services.url, log_url=services.url,
                    adapter=Stub(), repo_root=tmp_path, transport=services.transport,
                    private_key_path=str(keypair["priv"]), instructions="x")
    try:
        results = loop.run(max_turns=3)
    finally:
        services.stop()
    assert results[0]["outcome"] == "malformed" and results[0]["reason"] == "NOT_ONE_JSON_OBJECT"
    assert services.requests == [] and services.escalations == []


def test_report_turn_spark_format_unchanged():
    captured = {}
    bundle = make_bundle(1, turn_kind="REPORT", report_kind="PASS_START")
    _spark('{}', captured, bundle=bundle)
    fmt = captured["response_format"]["json_schema"]["schema"]
    assert "timeline" in fmt["properties"] and "command_call" not in fmt["properties"]


def test_frozen_files_six_schemas_and_models_unchanged():
    record = json.loads((REPO_ROOT / "odin" / "instructions" / "system_prompt.sha256.json").read_text(encoding="utf-8"))
    files = {
        record["sha256"]: REPO_ROOT / "odin" / "instructions" / "system_prompt.md",
        record["template_sha256"]: REPO_ROOT / "odin" / "instructions" / "template.md",
        record["prompt_template_sha256"]: REPO_ROOT / "odin" / "loop" / "prompt.py",
    }
    for expected, path in files.items():
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == expected, path
    frozen = json.loads((REPO_ROOT / "config" / "frozen.json").read_text(encoding="utf-8"))
    assert len(frozen["schemas"]) == 6
    for rel, expected in frozen["schemas"].items():
        assert "sha256:" + hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == expected, rel
    assert hashlib.sha256((REPO_ROOT / "config" / "models.yaml").read_bytes()).hexdigest() == \
        "dc7464c58c196698b62a9d05d5ed4511e406b79a54ec755120d0305eeb651dc9"
