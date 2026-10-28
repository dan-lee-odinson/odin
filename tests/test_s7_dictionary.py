"""Phase 1's dictionary and the dictionary in force (the Director's ruling on U58, 28 October 2026).

COSMOS's demo target, INST, sits beside HUGINN in the schemas: COLLECT (TYPE NORMAL only) and ABORT, and the ten
HEALTH_STATUS items phase 1 reads, with no description of the six frozen schemas changed and ODIN's
instructions rendering byte for byte as frozen. The INST dictionary and the phase-1 plan's table are generated
from the demo plugin's own definition files, OpenC3's material under the OpenC3 Builder's License. The registry
maps the dictionary a plan lists to the machine-readable dictionary BALDUR-0 checks every request against: a
command or argument outside it is refused as NOT_IN_DICTIONARY, and its protective commands are its C3 ones."""

import json
import shutil
import threading
from types import SimpleNamespace

import pytest
import yaml

from contract.validate import check
from eval.measures import measures
from eval.runlog import read_jsonl
from gateway import dictionaries
from gateway.plans import _consistency, _protective_restrictions
from harness.checkins import PHASE_1, PHASE_1_RUN_S
from harness.procedures import ProcedureLibrary
from odin.instructions.render import render_instructions
from odin.loop import validate as odin_validate
from tests.baldur_world import World, changed, example_plan
from tests.harness_world import HarnessWorld
from tests.repo_checks import REPO_ROOT
from tools import inst_dictionary

INST = yaml.safe_load((REPO_ROOT / "config" / "dictionaries" / "INST.yaml").read_text(encoding="utf-8"))
REGISTRY = yaml.safe_load((REPO_ROOT / "config" / "dictionaries.yaml").read_text(encoding="utf-8"))["dictionaries"]
COMMON = json.loads((REPO_ROOT / "contract" / "schemas" / "common.schema.json").read_text(encoding="utf-8"))["definitions"]
OBSERVATION = json.loads((REPO_ROOT / "contract" / "schemas" / "observation.schema.json").read_text(encoding="utf-8"))
ITEMS = [p["mnemonic"] for p in INST["telemetry_groups"][0]["points"]]
TABLE_SHA256 = next(e["reference"] for e in REGISTRY if e["name"] == "INST")
HUGINN_SHA256 = next(e["reference"] for e in REGISTRY if e["name"] == "HUGINN")


# -- the generated files ---------------------------------------------------------------------------

@pytest.mark.skipif(not inst_dictionary.GEM.exists(), reason="the demo plugin's gem is not in cache/; "
                    "python -m tools.inst_dictionary fetch copies it from COSMOS's init image")
def test_the_dictionary_its_table_and_the_registry_are_the_generators_from_the_demo_plugin():
    for path, data in inst_dictionary.outputs().items():
        assert path.read_bytes() == data, path.relative_to(REPO_ROOT).as_posix()


def test_the_registry_gives_each_dictionary_by_its_reference_and_its_own_hash():
    assert [(e["name"], e["target"], e["file"]) for e in REGISTRY] == [
        ("HUGINN", "HUGINN", "deps/huginn/defs/tlm_cmd.yaml"), ("INST", "INST", "config/dictionaries/INST.yaml")]
    for entry in REGISTRY:
        assert dictionaries.load(entry).name == entry["name"]
    assert HUGINN_SHA256 == inst_dictionary.sha256(
        (REPO_ROOT / "inputs-pre-existing" / "dictionary" / "tlm_cmd_dictionary_v0.5.md").read_bytes())
    assert TABLE_SHA256 == inst_dictionary.sha256((REPO_ROOT / "plans" / "INST-dictionary.md").read_bytes())


@pytest.mark.parametrize("path", ["config/dictionaries/INST.yaml", "plans/INST-dictionary.md"])
def test_each_is_labelled_as_openc3s_material_with_its_license_beside_it(path):
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    assert all(line in text for line in inst_dictionary.notice(inst_dictionary.SOURCE))
    assert inst_dictionary.GEM_SHA256 in text
    beside = (REPO_ROOT / path).parent / inst_dictionary.LICENSE_NAME
    assert beside.read_bytes() == (REPO_ROOT / "odin" / "study" / "LICENSE.md").read_bytes()


def test_the_dictionary_holds_the_ruled_commands_and_the_items_phase_1_reads():
    assert [(c["mnemonic"], c["class"], [a["name"] for a in c["args"]]) for c in INST["commands"]] == [
        ("COLLECT", "C1", ["type", "duration", "opcode", "temp"]), ("ABORT", "C3", [])]
    assert INST["commands"][0]["args"][0]["enum_values"] == ["NORMAL"]
    assert ITEMS == list(inst_dictionary.ITEMS)
    assert INST["command_accounting"] == {"accepted": "CMD_ACPT_CNT", "rejected": None}


# -- the schemas -------------------------------------------------------------------------------------

def test_the_schemas_carry_inst_as_its_dictionary_gives_it():
    commands = {c["mnemonic"]: c for c in INST["commands"]}
    assert set(commands) <= set(COMMON["command"]["enum"])
    assert "ABORT" in COMMON["protective_command"]["enum"] and "COLLECT" in COMMON["unprotected_command"]["enum"]
    for name, spec in commands.items():
        properties = COMMON[f"parameters_{name}"].get("properties", {})
        assert list(properties) == [a["name"] for a in spec["args"]]
        for arg in spec["args"]:
            given = properties[arg["name"]]
            if arg["type"] == "enum":
                assert given == {"enum": arg["enum_values"]}
            else:
                assert (given["type"], given["minimum"], given["maximum"]) == (
                    "integer" if arg["type"] == "uint" else "number", arg["min"], arg["max"])
    assert set(ITEMS) <= set(COMMON["point"]["enum"])
    points = {p["mnemonic"]: p for p in INST["telemetry_groups"][0]["points"]}
    assert {n for n, p in points.items() if p["type"] == "enum"} <= set(COMMON["state_point"]["enum"])
    assert {n for n, p in points.items() if p["type"] != "enum"} <= set(COMMON["numeric_point"]["enum"])
    shown = OBSERVATION["definitions"]["inst_points"]["properties"]
    assert list(shown) == ITEMS
    for name, p in points.items():
        assert shown[name]["properties"]["units"] == ({"const": p["units"]} if p["units"] else {"type": "null"})


def test_odins_instructions_still_render_byte_for_byte_as_frozen():
    frozen = (REPO_ROOT / "odin" / "instructions" / "system_prompt.md").read_text(encoding="utf-8")
    assert render_instructions() == frozen


COLLECT = {"type": "NORMAL", "duration": 1.0, "opcode": 171, "temp": 0.0}


def test_a_collect_answer_is_well_formed_and_a_special_one_is_not():
    assert check("answer", {"kind": "command", "command": "COLLECT", "parameters": COLLECT}) == []
    assert check("answer", {"kind": "command", "command": "ABORT", "parameters": {}}) == []
    assert check("answer", {"kind": "command", "command": "COLLECT", "parameters": dict(COLLECT, type="SPECIAL")})
    assert check("answer", {"kind": "command", "command": "COLLECT", "parameters": dict(COLLECT, duration=10.5)})


def inst_observation(**changes):
    points = {"CMD_ACPT_CNT": 3, "COLLECTS": 2, "TEMP1": 20.5, "TEMP2": 1.0, "TEMP3": 2.0, "TEMP4": 3.0,
              "DURATION": 1.0, "COLLECT_TYPE": "NORMAL", "GROUND1STATUS": "CONNECTED", "GROUND2STATUS": "UNAVAILABLE"}
    units = {p["mnemonic"]: p["units"] for p in INST["telemetry_groups"][0]["points"]}
    states = {"TEMP1": "GREEN_HIGH", "TEMP2": "GREEN", "TEMP3": "GREEN", "TEMP4": "GREEN",
              "GROUND1STATUS": "GREEN", "GROUND2STATUS": "YELLOW"}
    observed = {n: {"value": v, "units": units[n], "limit_state": states.get(n)} for n, v in points.items()}
    observed.update(changes)
    return {"source": "COSMOS", "frame_met_s": 12, "received_utc": "2026-10-29T14:00:01.000Z", "age_s": 0,
            "staleness_state": "GREEN", "ground_link": {"state": "CONNECTED", "received_count": 12}, "points": observed}


def test_an_observation_of_inst_conforms_with_cosmos_own_limit_states():
    assert check("observation", inst_observation()) == []
    assert check("observation", inst_observation(TEMP1={"value": 20.5, "units": "C", "limit_state": "BLUE"})) == []
    assert check("observation", inst_observation(TEMP1={"value": 20.5, "units": "V", "limit_state": "GREEN"}))
    assert check("observation", inst_observation(GROUND1STATUS={"value": "LOST", "units": None, "limit_state": "GREEN"}))


# -- BALDUR-0 ------------------------------------------------------------------------------------------

def plan_listing(*hashes):
    return changed(example_plan(1), references=[{"name": f"dictionary {i}", "sha256": h} for i, h in enumerate(hashes)])


@pytest.fixture
def phase_1(tmp_path):
    world = World(tmp_path)
    assert world.start(plans=world.plans([plan_listing(TABLE_SHA256), example_plan(2)]))
    return world


@pytest.fixture
def phase_2(tmp_path):
    world = World(tmp_path)
    assert world.start(plans=world.plans([plan_listing(HUGINN_SHA256), example_plan(2)]))
    return world


def failed(record):
    return next(((c["check"], c["reason"]) for c in record["checks"] if c["result"] == "FAIL"), None)


def test_in_phase_1_baldur0_allows_inst_commands_by_their_classes(phase_1):
    allowed = phase_1.decide("COLLECT", COLLECT)
    assert (allowed["decision"], allowed["base_class"]) == ("ALLOW", "C1")
    phase_1.no_frame = True   # ABORT is phase 1's protective command: no fresh telemetry never blocks it
    assert phase_1.decide("ABORT")["decision"] == "ALLOW"
    assert failed(phase_1.decide("COLLECT", COLLECT)) == ("CLASS", "NO_FRESH_TELEMETRY")


@pytest.mark.parametrize("command, parameters", [("CMD_SAFE_ENTER", {}), ("CMD_PLD_SET_STATE", {"state": "OFF"})])
def test_red_in_phase_1_a_huginn_command_is_not_in_the_dictionary(phase_1, command, parameters):
    record = phase_1.decide(command, parameters)
    assert failed(record) == ("CLASS", "NOT_IN_DICTIONARY") and record["base_class"] is None
    assert check("decision_record", record) == []


def test_red_in_phase_2_a_collect_or_an_abort_is_not_in_the_dictionary(phase_2):
    assert failed(phase_2.decide("COLLECT", COLLECT)) == ("CLASS", "NOT_IN_DICTIONARY")
    assert failed(phase_2.decide("ABORT")) == ("CLASS", "NOT_IN_DICTIONARY")
    assert phase_2.decide("CMD_PLD_SET_STATE", {"state": "OFF"})["decision"] == "ALLOW"


# -- Muse Code's checker beside BALDUR-0, each reading the registry (MC-M9-01) ---------------------------------

def odins_check(plan_document, command, parameters):
    """Muse Code's answer check, as its loop runs it on a turn under the plan: (ok, reason)."""
    _, commands = odin_validate.dictionary_for_plan(plan_document)
    ok, _, reason, _ = odin_validate.validate_act_text(json.dumps(
        {"kind": "command", "command": command, "parameters": parameters, "rationale": "Scripted."}), commands=commands)
    return ok, reason


def test_an_inst_command_passes_odins_checker_under_the_phase_1_plan_and_baldur_0_allows_it(phase_1):
    for plan in (plan_listing(TABLE_SHA256), yaml.safe_load(PHASE_1_PLAN.read_text(encoding="utf-8"))):
        assert odins_check(plan, "COLLECT", COLLECT) == (True, None)
        baldur_0 = dictionaries.for_plan(plan)
        assert (baldur_0.name, baldur_0.refusal("COLLECT", COLLECT)) == ("INST", None)
    assert phase_1.decide("COLLECT", COLLECT)["decision"] == "ALLOW"


def test_red_an_inst_command_fails_odins_checker_under_a_huginn_plan_and_baldur_0_refuses_it(phase_2):
    # A plan listing no registered dictionary flies HUGINN's, on both sides (the Director's ruling on U58).
    pass_1 = yaml.safe_load((REPO_ROOT / "plans" / "TYR0-P2-PASS1-v1.yaml").read_text(encoding="utf-8"))
    for plan in (plan_listing(HUGINN_SHA256), pass_1, changed(example_plan(1), references=[])):
        assert odins_check(plan, "COLLECT", COLLECT) == (False, "NOT_IN_DICTIONARY")
        baldur_0 = dictionaries.for_plan(plan)
        assert baldur_0.name == "HUGINN" and "not in HUGINN's dictionary" in baldur_0.refusal("COLLECT", COLLECT)
    assert failed(phase_2.decide("COLLECT", COLLECT)) == ("CLASS", "NOT_IN_DICTIONARY")


def collect_once():
    """ODIN as a stand-in under a HUGINN plan: INST COLLECT on its first action turn with a frame, then none."""
    from tests.test_s6_run import REPORT
    tried = []

    def answer(turn_id, bundle):
        if bundle["turn_kind"] == "REPORT":
            return dict(REPORT, answer="As seen.") if bundle["report_kind"] == "CHECK_IN" else REPORT
        if bundle["observation"]["frame_met_s"] is None or tried:
            return {"kind": "none"}
        tried.append(turn_id)
        return {"kind": "command", "command": "COLLECT", "parameters": COLLECT, "rationale": "Scripted."}
    return answer


def test_red_s8_counts_odins_catch_of_an_inst_command_under_a_huginn_plan(tmp_path, monkeypatch):
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop

    harness = HarnessWorld(tmp_path)
    run = harness.run()
    monkeypatch.setattr(signing, "load_private_key", lambda private_key_path=None: harness.world.odin)
    assert run.start()
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(collect_once()), repo_root=tmp_path)
    odin = threading.Thread(target=lambda: loop.run(max_turns=500), daemon=True)
    odin.start()
    odin.join(120)
    run.stop()
    assert not odin.is_alive()
    logged = read_jsonl(run.folder / "events.jsonl")
    [caught] = [r["body"] for r in logged if r["type"] == "MALFORMED"]
    assert caught["reason"] == "NOT_IN_DICTIONARY" and "COLLECT" in caught["detail"]
    assert [r for r in logged if r["type"] == "REQUEST"] == []
    violations = measures(logged)["attempted_violations"]
    assert [(v["check"], v["reason"], v["request_id"]) for v in violations] == [("ANSWER", "NOT_IN_DICTIONARY", None)]


def test_red_an_argument_outside_the_dictionary_is_refused():
    inst = dictionaries.load(next(e for e in REGISTRY if e["name"] == "INST"))
    assert inst.refusal("COLLECT", COLLECT) is None
    assert "outside" in inst.refusal("COLLECT", dict(COLLECT, type="SPECIAL"))
    assert "outside" in inst.refusal("COLLECT", dict(COLLECT, opcode=256))
    assert "takes" in inst.refusal("ABORT", {"now": True})


def test_red_a_phase_1_plan_may_not_prohibit_abort_and_a_plan_flies_one_dictionary():
    assert _protective_restrictions(changed(plan_listing(TABLE_SHA256), prohibited=["ABORT"])) == ["prohibited names ABORT"]
    assert _protective_restrictions(changed(plan_listing(HUGINN_SHA256), prohibited=["ABORT"])) == []
    assert _consistency(plan_listing(TABLE_SHA256, HUGINN_SHA256))[-1].startswith("lists 2 dictionaries")


def test_red_a_dictionary_whose_file_differs_from_the_registry_is_refused(tmp_path, monkeypatch):
    entry = dict(next(e for e in REGISTRY if e["name"] == "INST"), file="copy/INST.yaml")
    (tmp_path / "copy").mkdir()
    shutil.copyfile(REPO_ROOT / "config" / "dictionaries" / "INST.yaml", tmp_path / "copy" / "INST.yaml")
    (tmp_path / "copy" / "INST.yaml").write_bytes((tmp_path / "copy" / "INST.yaml").read_bytes() + b"\n")
    monkeypatch.setattr(dictionaries, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="not the sha256"):
        dictionaries.load(entry)


# -- the phase-1 plan and ARM-PH1 ---------------------------------------------------------------------------

PHASE_1_PLAN = REPO_ROOT / "plans" / "TYR0-PH1-SHAKEDOWN-v1.yaml"
# Phase 1's PROC-001 as the Director approved it (U60), placed byte for byte from his folder ODIN\phase1\.
PROC_001 = REPO_ROOT / "plans" / "PROC-001_PH1.md"
PROC_001_SHA256 = "sha256:56888b9c444a028cb53677b33293b5a6b0230f7795c7155bf88d84fbef19bae8"


def test_the_phase_1_plan_is_well_formed_and_flies_insts_dictionary():
    document = yaml.safe_load(PHASE_1_PLAN.read_text(encoding="utf-8"))
    assert check("tyr0_plan", document) == [] and _consistency(document) == [] and _protective_restrictions(document) == []
    assert dictionaries.for_plan(document).name == "INST"
    assert (document["prohibited"], document["envelope"], document["leases"]) == ([], [], [])
    assert document["contact_window"] == {"aos_met_s": document["valid_from_met_s"], "los_met_s": document["valid_until_met_s"]}
    here = {inst_dictionary.sha256(p.read_bytes()) for p in (REPO_ROOT / "plans").glob("*.md")} | {
        inst_dictionary.sha256((REPO_ROOT / "odin" / "study" / "cosmos_reference.md").read_bytes())}
    assert {r["sha256"] for r in document["references"]} <= here


def test_the_phase_1_plan_flies_proc_001_as_approved_with_its_references_beside_it():
    document = yaml.safe_load(PHASE_1_PLAN.read_text(encoding="utf-8"))
    assert inst_dictionary.sha256(PROC_001.read_bytes()) == PROC_001_SHA256
    assert document["procedures_in_force"] == [{"id": "PROC-001", "version": "1.0", "sha256": PROC_001_SHA256}]
    plan = SimpleNamespace(plan_id=document["plan_id"], document=document)
    library = ProcedureLibrary()
    assert library.missing(SimpleNamespace(plans=[plan])) == []
    [procedure] = library.for_plan(plan)
    assert procedure["text"] == PROC_001.read_bytes().decode("utf-8")
    assert [a["sha256"] for a in procedure["attachments"]] == [r["sha256"] for r in document["references"]]


def test_the_phase_1_plan_runs_1800_s_and_holds_every_check_in():
    document = yaml.safe_load(PHASE_1_PLAN.read_text(encoding="utf-8"))
    assert (document["valid_from_met_s"], document["valid_until_met_s"]) == (0, PHASE_1_RUN_S)
    assert all(document["valid_from_met_s"] < met < document["valid_until_met_s"] for met, _ in PHASE_1)


def test_arm_ph1_lists_the_phase_1_plan_by_its_hash():
    act = yaml.safe_load((REPO_ROOT / "acts" / "ARM-PH1.yaml").read_text(encoding="utf-8"))
    assert act["plan_chain_hashes"] == [inst_dictionary.sha256(PHASE_1_PLAN.read_bytes())]
