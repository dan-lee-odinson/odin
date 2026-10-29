"""M11: spark's ACT answer format that Meta can enforce.

One plain object at the root, no oneOf/allOf/if/then/$ref, every field
required but nullable, the command enum and parameter union derived at
call time from the dictionary in force (through the registry, as the
checker reads it). After the call the adapter drops nulls by the
Director's rule, then the frozen schema and dictionary check judge it.
"""
import hashlib
import json
from pathlib import Path

import pytest

from odin.adapters.spark import SparkAdapter, act_format, drop_nulls
from odin.loop.validate import dictionary_for_plan, validate_act_text
from conftest import REPO_ROOT, make_bundle

INST_REF = "sha256:1a113f774b043bc3a0939a8285e61475a35d3d268792b71f29fa8c7bae0ab53c"
HUGINN_REF = "sha256:985105875e6e41c4896cd635efbd15fe037349da228027261cc7ce059c930648"

FIXTURE_1 = ('{"command":"COLLECT","escalation_kind":null,"kind":"command",'
             '"parameters":{"duration":5.0,"opcode":1,"temp":10.0,"type":"NORMAL"},'
             '"proposed":null,"rationale":"S02 first NORMAL collect; confirm via COLLECTS rise from 3 and CMD_ACPT_CNT rise from 6.",'
             '"refs":null,"urgency":null}')
FIXTURE_2 = ('{"command": "COLLECT", "escalation_kind": null, "kind": "command", '
             '"parameters": {"duration": 5.0, "opcode": 0, "temp": 20.0, "type": "NORMAL"}, '
             '"proposed": null, "rationale": "S02 sends one NORMAL collect; confirm COLLECTS rise on later telemetry.", '
             '"refs": null, "urgency": null}')

BANNED = {"oneOf", "allOf", "$ref", "if", "then"}


def _commands(*refs):
    plan = {"plan_id": "P", "references": [{"name": f"r{i}", "sha256": r} for i, r in enumerate(refs)]}
    _entry, commands = dictionary_for_plan(plan)
    return commands


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
    assert set(fmt["required"]) == {"kind", "command", "parameters", "escalation_kind",
                                    "refs", "proposed", "urgency", "rationale"}
    assert fmt["properties"]["kind"] == {"type": "string", "enum": ["command", "escalation", "none"]}
    for name, prop in fmt["properties"].items():
        if name == "kind":
            continue
        assert any(b.get("type") == "null" for b in prop["anyOf"]), name


def test_inst_command_enum_and_parameters_union():
    fmt = act_format(_commands(INST_REF))
    cmd = fmt["properties"]["command"]["anyOf"][0]
    assert cmd["enum"] == ["COLLECT", "ABORT"]
    params = fmt["properties"]["parameters"]["anyOf"][0]
    assert params["type"] == "object" and params["additionalProperties"] is False
    assert set(params["required"]) == {"type", "duration", "opcode", "temp"}
    assert set(params["properties"]) == {"type", "duration", "opcode", "temp"}
    assert params["properties"]["type"]["anyOf"][0] == {"type": "string", "enum": ["NORMAL"]}
    assert params["properties"]["duration"]["anyOf"][0] == {"type": "number", "minimum": 0.0, "maximum": 10.0}
    assert params["properties"]["opcode"]["anyOf"][0] == {"type": "integer", "minimum": 0, "maximum": 255}
    assert params["properties"]["temp"]["anyOf"][0] == {"type": "number", "minimum": 0.0, "maximum": 25.0}
    for prop in params["properties"].values():
        assert any(b.get("type") == "null" for b in prop["anyOf"])


def test_huginn_command_enum_and_parameters_union_and_no_arg_command():
    fmt = act_format(_commands())
    cmd = fmt["properties"]["command"]["anyOf"][0]
    assert cmd["enum"] == ["CMD_PLD_SET_STATE", "CMD_PLD_SET_RATE", "CMD_SAFE_ENTER",
                           "CMD_SYS_RESET", "CMD_MODE_SET"]
    params = fmt["properties"]["parameters"]["anyOf"][0]
    assert set(params["properties"]) == {"state", "rate", "target"}
    assert params["properties"]["state"]["anyOf"][0] == {"type": "string", "enum": ["OFF", "ON"]}
    assert params["properties"]["rate"]["anyOf"][0] == {"type": "number", "minimum": 0.1, "maximum": 10}
    assert params["properties"]["target"]["anyOf"][0] == {"type": "string", "enum": ["NOMINAL", "LOW_POWER"]}


def test_command_enum_follows_the_dictionary_in_force_not_another():
    inst = act_format(_commands(INST_REF))["properties"]["command"]["anyOf"][0]["enum"]
    huginn = act_format(_commands())["properties"]["command"]["anyOf"][0]["enum"]
    assert "COLLECT" in inst and "COLLECT" not in huginn
    assert "CMD_SAFE_ENTER" in huginn and "CMD_SAFE_ENTER" not in inst
    # And what spark actually sends follows the bundle's plan.
    sent_inst = _sent_schema(bundle=_inst_bundle())["json_schema"]["schema"]
    assert sent_inst["properties"]["command"]["anyOf"][0]["enum"] == ["COLLECT", "ABORT"]
    sent_hug = _sent_schema(bundle=make_bundle(1, turn_kind="ACT"))["json_schema"]["schema"]
    assert "COLLECT" not in sent_hug["properties"]["command"]["anyOf"][0]["enum"]


def test_proposed_typed_the_same_way_and_escalation_fields_from_frozen():
    fmt = act_format(_commands(INST_REF))
    proposed = fmt["properties"]["proposed"]["anyOf"][0]
    assert proposed["type"] == "object" and proposed["additionalProperties"] is False
    assert set(proposed["required"]) == {"command", "parameters"}
    assert proposed["properties"]["command"] == fmt["properties"]["command"]["anyOf"][0]
    assert proposed["properties"]["parameters"] == fmt["properties"]["parameters"]["anyOf"][0]
    assert fmt["properties"]["escalation_kind"]["anyOf"][0] == {
        "type": "string", "enum": ["OFF_COURSE", "MALFUNCTION", "DECISION_NEEDED",
                                   "LEASE_NEEDED", "AUTHORITY_NEEDED", "CONFLICT"]}
    assert fmt["properties"]["urgency"]["anyOf"][0] == {"type": "string", "enum": ["ROUTINE", "URGENT"]}
    assert fmt["properties"]["refs"]["anyOf"][0] == {"type": "array", "items": {"type": "string"}}
    assert fmt["properties"]["rationale"]["anyOf"][0] == {"type": "string"}


def test_shared_argument_with_different_ranges_stops():
    commands = {
        "AAA": {"mnemonic": "AAA", "args": [{"name": "x", "type": "float", "min": 0.0, "max": 1.0}]},
        "BBB": {"mnemonic": "BBB", "args": [{"name": "x", "type": "float", "min": 0.0, "max": 2.0}]},
    }
    with pytest.raises(ValueError):
        act_format(commands)


# -- dropping nulls, then the frozen checks ---------------------------------------

@pytest.mark.parametrize("fixture", [FIXTURE_1, FIXTURE_2])
def test_director_fixtures_pass_after_the_adapter(fixture):
    captured = {}
    result = _adapter(fixture, captured).complete(prompt=b"p", bundle=_inst_bundle())
    obj = json.loads(result["raw"])
    assert obj["kind"] == "command" and obj["command"] == "COLLECT"
    assert set(obj) == {"kind", "command", "parameters", "rationale"}
    ok, validated, reason, _ = validate_act_text(result["raw"], commands=_commands(INST_REF))
    assert ok, reason


def test_full_collect_abort_and_none_with_only_null_parameters_pass():
    commands = _commands(INST_REF)
    cases = [
        ('{"kind":"command","command":"COLLECT","parameters":{"type":"NORMAL","duration":5.0,"opcode":1,"temp":10.0},'
         '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}'),
        ('{"kind":"command","command":"ABORT","parameters":{"type":null,"duration":null,"opcode":null,"temp":null},'
         '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}'),
        ('{"kind":"none","command":null,"parameters":{"type":null,"duration":null,"opcode":null,"temp":null},'
         '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":"wait"}'),
    ]
    for raw in cases:
        result = _adapter(raw, {}).complete(prompt=b"p", bundle=_inst_bundle())
        ok, obj, reason, detail = validate_act_text(result["raw"], commands=commands)
        assert ok, (result["raw"], reason, detail)
    abort = json.loads(_adapter(cases[1], {}).complete(prompt=b"p", bundle=_inst_bundle())["raw"])
    assert abort == {"kind": "command", "command": "ABORT", "parameters": {}}
    none = json.loads(_adapter(cases[2], {}).complete(prompt=b"p", bundle=_inst_bundle())["raw"])
    assert none == {"kind": "none", "rationale": "wait"}


def test_huginn_command_with_no_arguments_passes():
    raw = ('{"kind":"command","command":"CMD_SAFE_ENTER",'
           '"parameters":{"state":null,"rate":null,"target":null},'
           '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}')
    result = _adapter(raw, {}).complete(prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"))
    assert json.loads(result["raw"]) == {"kind": "command", "command": "CMD_SAFE_ENTER", "parameters": {}}
    ok, _, reason, detail = validate_act_text(result["raw"], commands=_commands())
    assert ok, (reason, detail)


def test_collect_with_a_null_argument_fails_the_dictionary_check():
    raw = ('{"kind":"command","command":"COLLECT",'
           '"parameters":{"type":"NORMAL","duration":null,"opcode":1,"temp":10.0},'
           '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}')
    result = _adapter(raw, {}).complete(prompt=b"p", bundle=_inst_bundle())
    assert "duration" not in json.loads(result["raw"])["parameters"]
    ok, _, reason, detail = validate_act_text(result["raw"], commands=_commands(INST_REF))
    assert not ok and reason == "NOT_IN_DICTIONARY" and "duration" in detail


def test_non_null_field_of_another_form_is_kept_and_refused():
    raw = ('{"kind":"none","command":"COLLECT","parameters":null,'
           '"escalation_kind":null,"refs":null,"proposed":null,"urgency":null,"rationale":null}')
    result = _adapter(raw, {}).complete(prompt=b"p", bundle=_inst_bundle())
    assert json.loads(result["raw"]).get("command") == "COLLECT"
    ok, _, reason, _ = validate_act_text(result["raw"], commands=_commands(INST_REF))
    assert not ok and reason == "SCHEMA_VIOLATION"


def test_escalations_null_proposed_is_not_dropped():
    raw = ('{"kind":"escalation","command":null,"parameters":{"type":null,"duration":null,"opcode":null,"temp":null},'
           '"escalation_kind":"MALFUNCTION","refs":[],"proposed":null,"urgency":"ROUTINE","rationale":null}')
    result = _adapter(raw, {}).complete(prompt=b"p", bundle=_inst_bundle())
    obj = json.loads(result["raw"])
    assert "proposed" in obj and obj["proposed"] is None
    ok, _, reason, detail = validate_act_text(result["raw"], commands=_commands(INST_REF))
    assert ok, (reason, detail)


def test_escalation_proposed_parameters_have_nulls_dropped():
    raw = ('{"kind":"escalation","command":null,"parameters":null,'
           '"escalation_kind":"MALFUNCTION","refs":[],'
           '"proposed":{"command":"COLLECT","parameters":{"type":"NORMAL","duration":1.0,"opcode":3,"temp":20.0}},'
           '"urgency":"ROUTINE","rationale":null}')
    result = _adapter(raw, {}).complete(prompt=b"p", bundle=_inst_bundle())
    ok, obj, reason, detail = validate_act_text(result["raw"], commands=_commands(INST_REF))
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


def test_spark_open_is_unchanged():
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
