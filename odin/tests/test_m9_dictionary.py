"""M9: the dictionary in force (U58). The answer check reads the dictionary
the plan in force lists, through config/dictionaries.yaml, never a fixed path."""
import hashlib
import json
import shutil

import pytest
import yaml

from odin.loop.validate import (
    DictionaryError,
    dictionary_for_plan,
    dictionary_in_force_entry,
    load_dictionary_commands,
    validate_act_text,
)
from conftest import REPO_ROOT, bundle_bytes, make_bundle

REGISTRY = REPO_ROOT / "config" / "dictionaries.yaml"
HUGINN_REF = "sha256:985105875e6e41c4896cd635efbd15fe037349da228027261cc7ce059c930648"
INST_REF = "sha256:1a113f774b043bc3a0939a8285e61475a35d3d268792b71f29fa8c7bae0ab53c"

COLLECT = ('{"kind":"command","command":"COLLECT","parameters":'
           '{"type":"NORMAL","duration":1.0,"opcode":3,"temp":20.0}}')
HUGINN_CMD = '{"kind":"command","command":"CMD_PLD_SET_STATE","parameters":{"state":"ON"}}'


def _plan(*refs):
    return {"plan_id": "P", "references": [{"name": f"ref{i}", "sha256": r}
                                           for i, r in enumerate(refs)]}


def _commands(plan):
    _entry, commands = dictionary_for_plan(plan)
    return commands


# -- choosing the dictionary in force ----------------------------------------

def test_no_registered_reference_uses_huginn():
    entry, commands = dictionary_for_plan(_plan())
    assert entry["name"] == "HUGINN"
    assert "CMD_PLD_SET_STATE" in commands and "COLLECT" not in commands
    entry2 = dictionary_in_force_entry(_plan("sha256:" + "0" * 64))
    assert entry2["name"] == "HUGINN"


def test_inst_plan_uses_inst():
    entry, commands = dictionary_for_plan(_plan(INST_REF))
    assert entry["name"] == "INST"
    assert "COLLECT" in commands and "CMD_PLD_SET_STATE" not in commands


def test_two_registered_dictionaries_raise():
    with pytest.raises(DictionaryError):
        dictionary_for_plan(_plan(HUGINN_REF, INST_REF))


def test_registry_file_hashes_verify():
    entries = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["dictionaries"]
    assert {e["name"] for e in entries} == {"HUGINN", "INST"}
    for entry in entries:
        commands = load_dictionary_commands(entry)
        assert commands  # the entry's file matched its recorded sha256


def test_changed_byte_in_dictionary_file_rejected(tmp_path):
    cfg = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config" / "dictionaries", cfg / "dictionaries")
    registry = cfg / "dictionaries.yaml"
    shutil.copy2(REGISTRY, registry)
    target = cfg / "dictionaries" / "INST.yaml"
    data = bytearray(target.read_bytes())
    data[-10] ^= 1
    target.write_bytes(bytes(data))
    entry = {"name": "INST", "file": "config/dictionaries/INST.yaml",
             "sha256": "sha256:e0afc1cd3eb87cbd4bb3be768b8d5bd5928723618555c5a396544d8fd5a0b477"}
    with pytest.raises(DictionaryError):
        load_dictionary_commands(entry, registry_path=registry)


# -- checking answers against the dictionary in force -------------------------

def test_inst_command_rejected_under_huginn_plan():
    ok, _, reason, detail = validate_act_text(COLLECT, commands=_commands(_plan()))
    assert not ok and reason == "NOT_IN_DICTIONARY" and "COLLECT" in detail


def test_inst_command_accepted_under_inst_plan_huginn_rejected():
    commands = _commands(_plan(INST_REF))
    ok, obj, reason, _ = validate_act_text(COLLECT, commands=commands)
    assert ok and obj["command"] == "COLLECT"
    ok, _, reason, detail = validate_act_text(HUGINN_CMD, commands=commands)
    assert not ok and reason == "NOT_IN_DICTIONARY" and "CMD_PLD_SET_STATE" in detail


def test_out_of_dictionary_is_not_schema_violation():
    ok, _, reason, _ = validate_act_text(
        '{"kind":"command","command":"CMD_NOPE","parameters":{}}',
        commands=_commands(_plan()))
    assert not ok and reason == "NOT_IN_DICTIONARY"


def test_dictionary_check_runs_before_generic_schema():
    # Out-of-dictionary command AND an extra top-level field: dictionary first.
    ok, _, reason, _ = validate_act_text(
        '{"kind":"command","command":"COLLECT","parameters":'
        '{"type":"NORMAL","duration":1.0,"opcode":3,"temp":20.0},"extra":1}',
        commands=_commands(_plan()))
    assert not ok and reason == "NOT_IN_DICTIONARY"


@pytest.mark.parametrize("params, named", [
    ('{"type":"SPECIAL","duration":1.0,"opcode":3,"temp":20.0}', "type"),
    ('{"type":"NORMAL","duration":99.0,"opcode":3,"temp":20.0}', "duration"),
    ('{"type":"NORMAL","duration":1.0,"opcode":true,"temp":20.0}', "opcode"),
    ('{"type":"NORMAL","duration":1.0,"opcode":300,"temp":20.0}', "opcode"),
    ('{"type":"NORMAL","duration":1.0,"opcode":3}', "temp"),
    ('{"type":"NORMAL","duration":1.0,"opcode":3,"temp":20.0,"bogus":1}', "bogus"),
])
def test_inst_argument_outside_dictionary(params, named):
    commands = _commands(_plan(INST_REF))
    ok, _, reason, detail = validate_act_text(
        '{"kind":"command","command":"COLLECT","parameters":' + params + '}',
        commands=commands)
    assert not ok and reason == "NOT_IN_DICTIONARY" and named in detail


def test_escalation_proposed_checked_the_same_way():
    commands = _commands(_plan(INST_REF))
    raw = ('{"kind":"escalation","escalation_kind":"MALFUNCTION","refs":[],'
           '"proposed":{"command":"CMD_PLD_SET_STATE","parameters":{"state":"ON"}},'
           '"urgency":"ROUTINE"}')
    ok, _, reason, detail = validate_act_text(raw, commands=commands)
    assert not ok and reason == "NOT_IN_DICTIONARY"
    good = ('{"kind":"escalation","escalation_kind":"MALFUNCTION","refs":[],'
            '"proposed":{"command":"COLLECT","parameters":'
            '{"type":"NORMAL","duration":1.0,"opcode":3,"temp":20.0}},"urgency":"ROUTINE"}')
    ok, _, _, _ = validate_act_text(good, commands=commands)
    assert ok


def test_default_dictionary_comes_through_the_registry():
    # No commands passed (stand-alone callers): the HUGINN entry, via registry.
    ok, _, _, _ = validate_act_text(HUGINN_CMD)
    assert ok
    ok, _, reason, _ = validate_act_text(COLLECT)
    assert not ok and reason == "NOT_IN_DICTIONARY"


def test_no_fixed_huginn_path_in_the_checker():
    for folder in ("loop", "adapters"):
        for path in (REPO_ROOT / "odin" / folder).glob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "tlm_cmd.yaml" not in text, path
            assert "deps/huginn" not in text.replace("\\", "/"), path


def test_frozen_files_unchanged():
    record = json.loads((REPO_ROOT / "odin" / "instructions"
                         / "system_prompt.sha256.json").read_text(encoding="utf-8"))
    files = {
        record["sha256"]: REPO_ROOT / "odin" / "instructions" / "system_prompt.md",
        record["template_sha256"]: REPO_ROOT / "odin" / "instructions" / "template.md",
        record["prompt_template_sha256"]: REPO_ROOT / "odin" / "loop" / "prompt.py",
    }
    for expected, path in files.items():
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == expected, path


# -- loop behaviour -------------------------------------------------------------

def _run_one(tmp_path, keypair, bundle, raw):
    from odin.adapters.stand_in import StandInAdapter
    from odin.devtools.fake_harness import FakeServices
    from odin.loop.loop import TurnLoop

    services = FakeServices(bundles=[bundle_bytes(bundle)],
                            public_key_path=keypair["pub"])
    loop = TurnLoop(
        harness_url=services.url, baldur_url=services.url, log_url=services.url,
        adapter=StandInAdapter(script=lambda t, b: raw),
        repo_root=tmp_path, transport=services.transport,
        private_key_path=str(keypair["priv"]), instructions="x")
    return loop.run(max_turns=5), services


def test_loop_inst_command_under_huginn_plan_sends_nothing(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")  # dev plan: no registered dictionary
    results, services = _run_one(tmp_path, keypair, bundle, COLLECT)
    assert results[0]["outcome"] == "malformed"
    assert results[0]["reason"] == "NOT_IN_DICTIONARY"
    assert services.requests == []
    malformed = [r for r in services.log_records if r["type"] == "MALFORMED"]
    assert malformed and malformed[0]["body"]["reason"] == "NOT_IN_DICTIONARY"


def test_loop_inst_plan_collect_is_sent(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")
    bundle["plan"]["references"].append({"name": "INST dictionary", "sha256": INST_REF})
    results, services = _run_one(tmp_path, keypair, bundle, COLLECT)
    assert results[0]["outcome"] in ("request", "refused")
    assert len(services.requests) == 1
    assert services.requests[0]["command"] == "COLLECT"


def test_loop_two_dictionaries_sends_nothing_and_is_an_error(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")
    bundle["plan"]["references"] += [
        {"name": "HUGINN dictionary", "sha256": HUGINN_REF},
        {"name": "INST dictionary", "sha256": INST_REF},
    ]
    results, services = _run_one(tmp_path, keypair, bundle, HUGINN_CMD)
    assert results[0]["outcome"] == "error"
    assert services.requests == []
    assert not [r for r in services.log_records if r["type"] == "MALFORMED"]
