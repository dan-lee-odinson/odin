"""M11 as amended by M14: spark's ACT answer format B.

History: M11 sent one plain object with a shared argument union. M14
replaced it with format B (one closed branch per command, tied to its
own arguments), moved the put-back and M11's null drop into the loop's
parse, and made the adapter return the model's text exactly. The full
format-B equality checks live in test_m14_format_b.py; this file keeps
the M11-era cases judged through the loop's parse.
"""
import hashlib
import json

from odin.adapters.spark import SparkAdapter, act_format, drop_nulls
from odin.loop.loop import judge_act_text
from odin.loop.validate import dictionary_for_plan
from conftest import REPO_ROOT, make_bundle

INST_REF = "sha256:1a113f774b043bc3a0939a8285e61475a35d3d268792b71f29fa8c7bae0ab53c"
HUGINN_REF = "sha256:985105875e6e41c4896cd635efbd15fe037349da228027261cc7ce059c930648"

BANNED = {"oneOf", "allOf", "$ref", "if", "then"}


def _commands(*refs):
    plan = {"plan_id": "P", "references": [{"name": f"r{i}", "sha256": r} for i, r in enumerate(refs)]}
    return dictionary_for_plan(plan)[1]


def _inst_bundle():
    bundle = make_bundle(1, turn_kind="ACT")
    bundle["plan"]["references"].append({"name": "INST dictionary", "sha256": INST_REF})
    return bundle


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


def _branches(fmt):
    return fmt["properties"]["command_call"]["anyOf"][0]["anyOf"]


def _branch(fmt, name):
    return next(b for b in _branches(fmt) if b["properties"]["command"]["enum"] == [name])


def _adapter(reply, captured):
    def fake_post(url, headers, payload, timeout):
        captured.update(payload)
        return 200, {"choices": [{"finish_reason": "stop", "message": {"content": reply}}], "usage": {}}
    return SparkAdapter(reasoning_effort="low", max_output_tokens=10,
                        timeout_s=5, api_key="test-only", http_post=fake_post)


def _sent_schema(reply='{"kind":"none"}', bundle=None):
    captured = {}
    _adapter(reply, captured).complete(prompt=b"p", bundle=bundle or make_bundle(1, turn_kind="ACT"))
    return captured["response_format"]


def _judged(reply, bundle=None):
    result = _adapter(reply, {}).complete(prompt=b"p", bundle=bundle or _inst_bundle())
    assert result["raw"] == reply  # M14: adapter returns text exactly
    bundle = bundle or _inst_bundle()
    refs = [r["sha256"] for r in bundle["plan"]["references"]]
    commands = _commands(INST_REF) if INST_REF in refs else _commands()
    return judge_act_text(result["raw"], commands=commands)


# -- the format -----------------------------------------------------------------

def test_act_format_is_one_plain_object_with_no_banned_keys():
    fmt = act_format(_commands(INST_REF))
    assert fmt["type"] == "object"
    assert not (BANNED & _keys(fmt))


def test_no_strict_flag_and_no_banned_keys_in_what_spark_sends():
    rf = _sent_schema(bundle=_inst_bundle())
    assert "strict" not in rf and "strict" not in rf["json_schema"]
    fmt = rf["json_schema"]["schema"]
    assert fmt["type"] == "object"
    assert not (BANNED & _keys(fmt))


def test_kind_required_enum_and_every_other_field_required_but_nullable():
    fmt = act_format(_commands(INST_REF))
    assert set(fmt["required"]) == {"kind", "command_call", "escalation", "rationale"}
    assert fmt["properties"]["kind"] == {"type": "string", "enum": ["command", "escalation", "none"]}
    for name, prop in fmt["properties"].items():
        if name == "kind":
            continue
        assert any(b.get("type") == "null" for b in prop["anyOf"]), name


def test_inst_command_branches():
    fmt = act_format(_commands(INST_REF))
    assert [b["properties"]["command"]["enum"] for b in _branches(fmt)] == [["COLLECT"], ["ABORT"]]
    params = _branch(fmt, "COLLECT")["properties"]["parameters"]
    assert params["type"] == "object" and params["additionalProperties"] is False
    assert params["required"] == ["type", "duration", "opcode", "temp"]
    assert params["properties"]["type"] == {"type": "string", "enum": ["NORMAL"]}
    assert params["properties"]["duration"] == {"type": "number", "minimum": 0.0, "maximum": 10.0}
    assert params["properties"]["opcode"] == {"type": "integer", "minimum": 0, "maximum": 255}
    assert params["properties"]["temp"] == {"type": "number", "minimum": 0.0, "maximum": 25.0}
    assert _branch(fmt, "ABORT")["properties"]["parameters"] == {
        "type": "object", "additionalProperties": False, "required": [], "properties": {}}


def test_huginn_command_branches_and_no_arg_command():
    fmt = act_format(_commands())
    assert [b["properties"]["command"]["enum"] for b in _branches(fmt)] == [
        ["CMD_PLD_SET_STATE"], ["CMD_PLD_SET_RATE"], ["CMD_SAFE_ENTER"],
        ["CMD_SYS_RESET"], ["CMD_MODE_SET"]]
    assert _branch(fmt, "CMD_PLD_SET_STATE")["properties"]["parameters"]["properties"] == {
        "state": {"type": "string", "enum": ["OFF", "ON"]}}
    assert _branch(fmt, "CMD_PLD_SET_RATE")["properties"]["parameters"]["properties"] == {
        "rate": {"type": "number", "minimum": 0.1, "maximum": 10}}
    assert _branch(fmt, "CMD_MODE_SET")["properties"]["parameters"]["properties"] == {
        "target": {"type": "string", "enum": ["NOMINAL", "LOW_POWER"]}}
    assert _branch(fmt, "CMD_SAFE_ENTER")["properties"]["parameters"]["required"] == []


def test_command_enum_follows_the_dictionary_in_force_not_another():
    inst = [b["properties"]["command"]["enum"][0] for b in _branches(act_format(_commands(INST_REF)))]
    huginn = [b["properties"]["command"]["enum"][0] for b in _branches(act_format(_commands()))]
    assert inst == ["COLLECT", "ABORT"] and "COLLECT" not in huginn
    sent_inst = _sent_schema(bundle=_inst_bundle())["json_schema"]["schema"]
    assert [b["properties"]["command"]["enum"] for b in _branches(sent_inst)] == [["COLLECT"], ["ABORT"]]


def test_proposed_is_the_same_anyof_and_escalation_fields_from_frozen():
    fmt = act_format(_commands(INST_REF))
    esc = fmt["properties"]["escalation"]["anyOf"][0]["properties"]
    assert esc["proposed"] == fmt["properties"]["command_call"]
    assert esc["escalation_kind"]["anyOf"][0] == {
        "type": "string", "enum": ["OFF_COURSE", "MALFUNCTION", "DECISION_NEEDED",
                                   "LEASE_NEEDED", "AUTHORITY_NEEDED", "CONFLICT"]}
    assert esc["urgency"]["anyOf"][0] == {"type": "string", "enum": ["ROUTINE", "URGENT"]}
    assert esc["refs"]["anyOf"][0] == {"type": "array", "items": {"type": "string"}}
    assert fmt["properties"]["rationale"]["anyOf"][0] == {"type": "string"}


def test_shared_argument_name_typed_per_command_in_format_b():
    commands = {
        "AAA": {"mnemonic": "AAA", "args": [{"name": "x", "type": "float", "min": 0.0, "max": 1.0}]},
        "BBB": {"mnemonic": "BBB", "args": [{"name": "x", "type": "float", "min": 0.0, "max": 2.0}]},
    }
    fmt = act_format(commands)
    assert _branch(fmt, "AAA")["properties"]["parameters"]["properties"]["x"]["maximum"] == 1.0
    assert _branch(fmt, "BBB")["properties"]["parameters"]["properties"]["x"]["maximum"] == 2.0


# -- dropping nulls in the loop's parse, then the frozen checks -------------------

def test_director_fixtures_pass_after_put_back_and_drop():
    cases = [
        '{"command_call":{"command":"COLLECT","parameters":{"duration":5.0,"opcode":1,"temp":10.0,"type":"NORMAL"}},'
        '"escalation_kind":null,"kind":"command","proposed":null,'
        '"rationale":"S02 first NORMAL collect.","refs":null,"urgency":null}',
        '{"command_call": {"command": "COLLECT", "parameters": {"duration": 5.0, "opcode": 0, "temp": 20.0, "type": "NORMAL"}}, '
        '"escalation_kind": null, "kind": "command", "proposed": null, '
        '"rationale": "S02 sends one NORMAL collect.", "refs": null, "urgency": null}',
    ]
    for raw in cases:
        ok, obj, reason, detail = _judged(raw)
        assert ok, (reason, detail)
        assert obj["command"] == "COLLECT"
        assert set(obj) == {"kind", "command", "parameters", "rationale"}


def test_full_collect_abort_and_none_pass():
    cases = [
        ('{"kind":"command","command_call":{"command":"COLLECT","parameters":{"type":"NORMAL","duration":5.0,"opcode":1,"temp":10.0}},'
         '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}'),
        ('{"kind":"command","command_call":{"command":"ABORT","parameters":{}},'
         '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}'),
        ('{"kind":"none","command_call":null,'
         '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":"wait"}'),
    ]
    for raw in cases:
        ok, obj, reason, detail = _judged(raw)
        assert ok, (raw, reason, detail)
    _, abort, _, _ = _judged(cases[1])
    assert abort == {"kind": "command", "command": "ABORT", "parameters": {}}
    _, none, _, _ = _judged(cases[2])
    assert none == {"kind": "none", "rationale": "wait"}


def test_huginn_command_with_no_arguments_passes():
    raw = ('{"kind":"command","command_call":{"command":"CMD_SAFE_ENTER","parameters":{}},'
           '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}')
    ok, obj, reason, detail = _judged(raw, bundle=make_bundle(1, turn_kind="ACT"))
    assert ok, (reason, detail)
    assert obj == {"kind": "command", "command": "CMD_SAFE_ENTER", "parameters": {}}


def test_collect_with_a_null_argument_fails_the_dictionary_check():
    raw = ('{"kind":"command","command_call":{"command":"COLLECT",'
           '"parameters":{"type":"NORMAL","duration":null,"opcode":1,"temp":10.0}},'
           '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}')
    ok, _, reason, detail = _judged(raw)
    assert not ok and reason == "NOT_IN_DICTIONARY" and "duration" in detail


def test_non_null_field_of_another_form_is_kept_and_refused():
    raw = ('{"kind":"none","command_call":{"command":"COLLECT",'
           '"parameters":{"type":"NORMAL","duration":5.0,"opcode":1,"temp":10.0}},'
           '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}')
    ok, _, reason, _ = _judged(raw)
    assert not ok and reason == "SCHEMA_VIOLATION"


def test_escalations_null_proposed_is_not_dropped():
    raw = ('{"kind":"escalation","command_call":null,'
           '"escalation_kind":"MALFUNCTION","refs":[],"proposed":null,"urgency":"ROUTINE","rationale":null}')
    ok, obj, reason, detail = _judged(raw)
    assert ok, (reason, detail)
    assert "proposed" in obj and obj["proposed"] is None


def test_escalation_proposed_parameters_pass():
    raw = ('{"kind":"escalation","command_call":null,'
           '"escalation_kind":"MALFUNCTION","refs":[],'
           '"proposed":{"command":"COLLECT","parameters":{"type":"NORMAL","duration":1.0,"opcode":3,"temp":20.0}},'
           '"urgency":"ROUTINE","rationale":null}')
    ok, obj, reason, detail = _judged(raw)
    assert ok, (reason, detail)
    assert obj["proposed"]["parameters"] == {"type": "NORMAL", "duration": 1.0, "opcode": 3, "temp": 20.0}


def test_drop_nulls_keeps_a_required_null_so_the_frozen_schema_refuses():
    obj = drop_nulls({"kind": "command", "command": None, "parameters": {},
                      "escalation_kind": None, "refs": None, "proposed": None,
                      "urgency": None, "rationale": None})
    assert "command" in obj and obj["command"] is None


# -- unchanged neighbours ---------------------------------------------------------

def test_report_turn_format_is_unchanged():
    bundle = make_bundle(1, turn_kind="REPORT", report_kind="PASS_START")
    rf = _sent_schema(bundle=bundle)
    fmt = rf["json_schema"]["schema"]
    assert "timeline" in fmt["properties"]
    assert not ({"oneOf", "$ref"} & _keys(fmt))


def test_spark_open_answer_tool_names_unchanged():
    from odin.adapters.spark_open import ANSWER_TOOLS
    names = [t["function"]["name"] for t in ANSWER_TOOLS]
    assert names == ["answer_command", "answer_escalation", "answer_none", "answer_report"]


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
    for rel, expected in frozen["schemas"].items():
        assert "sha256:" + hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == expected, rel
    assert hashlib.sha256((REPO_ROOT / "config" / "models.yaml").read_bytes()).hexdigest() == \
        "dc7464c58c196698b62a9d05d5ed4511e406b79a54ec755120d0305eeb651dc9"
