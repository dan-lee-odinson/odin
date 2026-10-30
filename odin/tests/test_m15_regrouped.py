"""M15: spark's regrouped answer format (format R).

Red cases: format B sent instead of R; escalation fields left nested;
an escalation holding values on a command dropped instead of refused;
any of answers-R's ten or escalations-R's five judged otherwise than
recorded. Each was shown failing against the M14 code first.
"""
import hashlib
import json

import pytest

from odin.adapters.spark import SparkAdapter, act_format, drop_nulls
from odin.adapters.spark_open import convert_message
from odin.devtools.fake_harness import FakeServices
from odin.loop.loop import TurnLoop, judge_act_text, put_back_command_call, put_back_escalation
from odin.loop.validate import dictionary_for_plan, validate_against_schema
from conftest import REPO_ROOT, bundle_bytes, make_bundle

INST_REF = "sha256:1a113f774b043bc3a0939a8285e61475a35d3d268792b71f29fa8c7bae0ab53c"
BANNED = {"oneOf", "allOf", "if", "then", "$ref"}
ESCALATION_FIELDS = ("escalation_kind", "refs", "urgency", "proposed")


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


def _load(*parts):
    return json.loads((REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8"))


# -- the regrouped format -----------------------------------------------------

def test_regrouped_format_equals_huginn_file_as_parsed_json():
    assert act_format(_commands()) == _load("contract", "m15", "format-R-HUGINN.json")


def test_regrouped_format_equals_inst_file_as_parsed_json():
    assert act_format(_commands(INST_REF)) == _load("contract", "m15", "format-R-INST.json")


def test_regrouped_root_order_escalation_shape_and_no_banned_keys():
    fmt = act_format(_commands())
    assert list(fmt["properties"]) == ["kind", "command_call", "escalation", "rationale"]
    assert fmt["required"] == ["kind", "command_call", "escalation", "rationale"]
    assert not (BANNED & _keys(fmt))
    esc = fmt["properties"]["escalation"]
    assert esc["anyOf"][1] == {"type": "null"}
    obj = esc["anyOf"][0]
    assert obj["type"] == "object" and obj["additionalProperties"] is False
    assert obj["required"] == ["escalation_kind", "refs", "urgency", "proposed"]
    assert list(obj["properties"]) == ["escalation_kind", "refs", "urgency", "proposed"]
    assert obj["properties"]["proposed"] == fmt["properties"]["command_call"]
    branches = fmt["properties"]["command_call"]["anyOf"][0]["anyOf"]
    assert [b["properties"]["command"]["enum"] for b in branches] == [
        ["CMD_PLD_SET_STATE"], ["CMD_PLD_SET_RATE"], ["CMD_SAFE_ENTER"],
        ["CMD_SYS_RESET"], ["CMD_MODE_SET"]]


def test_spark_sends_regrouped_format_not_format_b():
    captured = {}
    _spark('{"kind":"none"}', captured)
    fmt = captured["response_format"]["json_schema"]["schema"]
    assert fmt == _load("contract", "m15", "format-R-HUGINN.json")
    assert fmt != _load("contract", "m14", "format-B-HUGINN.json")
    assert "escalation" in fmt["properties"]
    for field in ESCALATION_FIELDS:
        assert field not in fmt["properties"]


def test_spark_sent_format_exact_for_dictionary_in_force():
    # Point 5: the HUGINN bundle's sent format is checked exactly, not
    # only as "not INST's"; the INST bundle's is checked exactly too.
    captured = {}
    _spark('{"kind":"none"}', captured, bundle=_inst_bundle())
    assert captured["response_format"]["json_schema"]["schema"] == \
        _load("contract", "m15", "format-R-INST.json")
    captured_h = {}
    _spark('{"kind":"none"}', captured_h)
    sent_h = captured_h["response_format"]["json_schema"]["schema"]
    assert sent_h == _load("contract", "m15", "format-R-HUGINN.json")
    assert sent_h != _load("contract", "m15", "format-R-INST.json")


# -- put back, then judge exactly as M14 ---------------------------------------

def test_null_escalation_puts_back_nulls():
    put = put_back_escalation({"kind": "command", "command_call": None,
                               "escalation": None, "rationale": "x"})
    assert "escalation" not in put
    assert {f: put[f] for f in ESCALATION_FIELDS} == {f: None for f in ESCALATION_FIELDS}


def test_escalation_holding_values_is_put_back_and_kept():
    esc = {"escalation_kind": "LEASE_NEEDED", "refs": ["PROC-002-S04"],
           "urgency": "URGENT",
           "proposed": {"command": "CMD_PLD_SET_STATE", "parameters": {"state": "OFF"}}}
    put = put_back_escalation({"kind": "escalation", "command_call": None,
                               "escalation": esc, "rationale": "made up"})
    assert "escalation" not in put
    assert {f: put[f] for f in ESCALATION_FIELDS} == esc


def test_escalation_fields_left_nested_would_not_judge_as_root():
    # Through the loop's parse the fields must be at the root: the judged
    # escalation carries them, with no nested "escalation" left.
    raw = json.dumps({"kind": "escalation", "command_call": None, "rationale": "made up",
                      "escalation": {"escalation_kind": "MALFUNCTION", "refs": [],
                                     "urgency": "ROUTINE", "proposed": None}})
    ok, obj, reason, detail = judge_act_text(raw, commands=_commands())
    assert ok, (reason, detail)
    assert "escalation" not in obj
    assert obj["escalation_kind"] == "MALFUNCTION" and obj["proposed"] is None


def test_command_escalation_holding_values_refused_not_dropped():
    raw = json.dumps({"kind": "command",
                      "command_call": {"command": "CMD_PLD_SET_STATE",
                                       "parameters": {"state": "OFF"}},
                      "rationale": "made up",
                      "escalation": {"escalation_kind": None, "refs": ["PROC-002-S04"],
                                     "urgency": "ROUTINE", "proposed": None}})
    # The values survive the put-back and the null drop...
    judged = drop_nulls(put_back_command_call(put_back_escalation(json.loads(raw))))
    assert judged.get("refs") == ["PROC-002-S04"] and judged.get("urgency") == "ROUTINE"
    assert validate_against_schema("answer.schema.json", judged) != []
    # ...so the frozen schema refuses the answer: nothing is sent.
    ok, obj, reason, detail = judge_act_text(raw, commands=_commands())
    assert not ok and obj is None and reason == "SCHEMA_VIOLATION"


def test_answers_r_judged_exactly_as_recorded():
    records = _load("contract", "m15", "answers-R.json")
    assert len(records) == 10
    for rec in records:
        commands = _commands(INST_REF) if rec["dictionary"] == "INST" else _commands()
        ok, obj, reason, detail = judge_act_text(rec["content_verbatim"], commands=commands)
        recorded = rec["judged_after_put_backs_and_null_drop"]
        assert ok == recorded["accepted"], (rec["prompt"], rec["call"], reason, detail)
        assert obj == recorded["judged"], (rec["prompt"], rec["call"])
        assert reason == recorded["reason"] and detail == recorded["detail"]


def test_escalations_r_judged_exactly_as_recorded():
    records = _load("contract", "m15", "escalations-R.json")
    assert len(records) == 5
    for rec in records:
        commands = _commands(INST_REF) if rec["dictionary"] == "INST" else _commands()
        ok, obj, reason, detail = judge_act_text(json.dumps(rec["answer"]), commands=commands)
        recorded = rec["judged_after_put_backs_and_null_drop"]
        assert ok == recorded["accepted"], (rec["case"], reason, detail)
        assert obj == recorded["judged"], rec["case"]
        assert reason == recorded["reason"] and detail == recorded["detail"], rec["case"]


def test_m14_judging_still_applies_after_put_backs():
    # An argument the command does not take is refused, not dropped.
    raw = ('{"kind":"command","command_call":{"command":"CMD_PLD_SET_STATE",'
           '"parameters":{"state":"OFF","rate":2.0}},"escalation":null,"rationale":null}')
    ok, obj, reason, detail = judge_act_text(raw, commands=_commands())
    assert not ok and reason == "NOT_IN_DICTIONARY" and "rate" in detail


# -- CANDIDATE exact, loop end to end ------------------------------------------

def test_spark_adapter_returns_text_exactly_and_loop_candidate_is_exact(tmp_path, keypair):
    verbatim = ('{  "kind" : "none" ,  "command_call" : null , '
                '"escalation" : null , "rationale" : "wait" }')
    assert _spark(verbatim)["raw"] == verbatim

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


def test_loop_sends_command_and_escalation_from_regrouped_answers(tmp_path, keypair):
    answers = [
        '{"kind":"command","command_call":{"command":"CMD_PLD_SET_STATE",'
        '"parameters":{"state":"OFF"}},"escalation":null,"rationale":"shed"}',
        '{"kind":"escalation","command_call":null,"rationale":"made up",'
        '"escalation":{"escalation_kind":"LEASE_NEEDED","refs":["PROC-002-S04"],'
        '"urgency":"URGENT","proposed":{"command":"CMD_PLD_SET_STATE",'
        '"parameters":{"state":"OFF"}}}}',
        '{"kind":"command","command_call":{"command":"CMD_PLD_SET_STATE",'
        '"parameters":{"state":"OFF"}},"rationale":"made up",'
        '"escalation":{"escalation_kind":null,"refs":["PROC-002-S04"],'
        '"urgency":"ROUTINE","proposed":null}}',
    ]
    bundles = [bundle_bytes(make_bundle(i + 1, turn_kind="ACT")) for i in range(len(answers))]
    services = FakeServices(bundles=bundles, public_key_path=keypair["pub"])
    services.start()
    queue = list(answers)

    class Stub:
        name = "spark"
        def complete(self, *, prompt, bundle, **kw):
            return {"raw": queue.pop(0), "channel": "CONTENT", "status": "OK"}

    loop = TurnLoop(harness_url=services.url, baldur_url=services.url, log_url=services.url,
                    adapter=Stub(), repo_root=tmp_path, transport=services.transport,
                    private_key_path=str(keypair["priv"]), instructions="x")
    try:
        results = loop.run(max_turns=5)
    finally:
        services.stop()
    assert [r["outcome"] for r in results] == ["request", "escalation", "malformed"], results
    assert results[2]["reason"] == "SCHEMA_VIOLATION"
    assert len(services.requests) == 1
    assert services.requests[0]["command"] == "CMD_PLD_SET_STATE"
    assert len(services.escalations) == 1
    esc = services.escalations[0]
    assert esc["escalation_kind"] == "LEASE_NEEDED" and esc["urgency"] == "URGENT"
    assert esc["proposed"] == {"command": "CMD_PLD_SET_STATE", "parameters": {"state": "OFF"}}
    assert "escalation" not in esc


# -- unchanged neighbours -------------------------------------------------------

def test_spark_open_unchanged():
    def call(name, args):
        return {"id": "c1", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}}
    ok, obj, reason, _ = convert_message(
        None, [call("answer_command", {"command": "CMD_PLD_SET_STATE",
                                       "parameters": {"state": "ON"}, "rationale": "ok"})],
        turn_kind="ACT", commands=_commands())
    assert ok and obj["command"] == "CMD_PLD_SET_STATE"
    ok, obj, reason, _ = convert_message(
        '  {"kind":"none","rationale":"wait"}  ', [], turn_kind="ACT", commands=_commands())
    assert ok and obj == {"kind": "none", "rationale": "wait"}
    ok, _, reason, _ = convert_message(
        '{"kind":"none"} {"kind":"none"}', [], turn_kind="ACT", commands=_commands())
    assert not ok and reason == "NOT_ONE_JSON_OBJECT"


def test_report_turn_spark_format_unchanged():
    captured = {}
    bundle = make_bundle(1, turn_kind="REPORT", report_kind="PASS_START")
    _spark('{}', captured, bundle=bundle)
    fmt = captured["response_format"]["json_schema"]["schema"]
    assert "timeline" in fmt["properties"] and "command_call" not in fmt["properties"]
    assert "escalation" not in fmt["properties"]


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
