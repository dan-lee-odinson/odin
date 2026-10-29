"""The Director's pre-existing inputs, the phase-2 TYR-0 plans and the arming acts, as placed by his rulings
of 27 October 2026, section 5: every input labeled with its date, source and hash and free of private
identity details; each procedure stating the version of its folder, and v0.2 carrying the D-017 red-line
PASS-3 flew on; the console card of 27 October nowhere in the repository; each plan well formed, its
contact window one of those the U35 tests use, every procedure it names placed, and every other hash it
lists either a file here or an all-zero placeholder still to fill; contact A's telemetry frozen; and the
six acts as section 3 lists them. The plans and acts are unsigned until the Director signs them after
phase 1. By his ruling of 28 October, HUGINN's dictionary v0.5 is here byte for byte, and every plan lists
it, then BALDUR-0's generated class table, as its last two references."""

import hashlib
import re
import subprocess

import pytest
import yaml

from contract.validate import check
from gateway.plans import _consistency, _protective_restrictions
from gateway.signed import load_yaml
from tests.huginn_scenarios import FLOWN
from tests.repo_checks import REPO_ROOT, iter_files
from tools.class_table import FROZEN as CLASS_TABLE
from tools.contact_a_telemetry import FROZEN, generate
from tools.identity_scan import scan

INPUTS = REPO_ROOT / "inputs-pre-existing"
PLANS = sorted((REPO_ROOT / "plans").glob("TYR0-P2-*.yaml"))   # phase 2's; phase 1's is tests/test_s7_dictionary.py's
ACTS = sorted((REPO_ROOT / "acts").glob("*.yaml"))
ZEROS = "sha256:" + "0" * 64
CARD_OF_27_OCTOBER = "sha256:bb6dd70e260792651a6c2e9c5c240e2bad7d53d6ba949064c45c6d0dd039fd8e"
DICTIONARY = "sha256:985105875e6e41c4896cd635efbd15fe037349da228027261cc7ce059c930648"   # v0.5 at b4dbe61
LABEL_ROW = re.compile(r"^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| `(sha256:[0-9a-f]{64})` \|$", re.MULTILINE)
VERSION_LINE = re.compile(r"^Procedures version: (\S+) ", re.MULTILINE)
# D-017 rulings 2 and 3, the red-line of PROC-002-S02 made before PASS-3: a load alarm goes to S03.
D017_RED_LINE = "If the point you confirmed at S01 is EPS_LOAD_I, record branch load alarm and go to S03."


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def plan(path):
    document, problems = load_yaml(path.read_bytes())
    assert problems == [], path.name
    return document


def labels():
    found = {}
    for sources in (INPUTS / "SOURCES.md", INPUTS / "comparison-only" / "SOURCES.md"):
        base = sources.parent.relative_to(INPUTS).as_posix()
        for path, _, _, sha in LABEL_ROW.findall(sources.read_text(encoding="utf-8")):
            found[f"{base}/{path}".lstrip("./")] = sha
    return found


def files_holding(root, sha):
    return [path for path in iter_files(root) if digest(path.read_bytes()) == sha]


# -- the inputs --------------------------------------------------------------------------------------------

def test_every_input_is_labeled_with_its_hash_and_every_label_is_a_file():
    on_disk = {p.relative_to(INPUTS).as_posix() for p in INPUTS.rglob("*") if p.is_file() and p.name != "SOURCES.md"}
    labeled = labels()
    assert set(labeled) == on_disk
    assert {name: digest((INPUTS / name).read_bytes()) for name in labeled} == labeled


def test_no_input_holds_a_private_identity_detail():
    assert [f for p in INPUTS.rglob("*") if p.is_file() for f in scan(p.name, p.read_bytes())] == []


@pytest.mark.parametrize("version", ["0.1", "0.2", "0.3"])
def test_each_procedure_states_the_version_of_its_folder(version):
    folder = INPUTS / "procedures" / f"v{version}"
    assert sorted(p.name for p in folder.iterdir()) == ["PROC-001.md", "PROC-002.md", "PROC-003.md"]
    assert {p.name: VERSION_LINE.findall(p.read_text(encoding="utf-8")) for p in folder.iterdir()} == {
        name: [version] for name in ("PROC-001.md", "PROC-002.md", "PROC-003.md")}


def test_proc_002_s02_carries_the_d017_red_line_from_v0_2_on():
    def s02(version):
        text = (INPUTS / "procedures" / f"v{version}" / "PROC-002.md").read_text(encoding="utf-8")
        return text.split("### PROC-002-S02 ", 1)[1].split("### PROC-002-S03 ", 1)[0]
    assert [D017_RED_LINE in s02(version) for version in ("0.1", "0.2", "0.3")] == [False, True, True]


def test_the_console_card_of_27_october_is_nowhere_in_the_repository():
    assert files_holding(REPO_ROOT, CARD_OF_27_OCTOBER) == []


def test_red_a_file_holding_those_bytes_would_be_found(tmp_path):
    (tmp_path / "card.html").write_bytes(b"made up for the test\n")
    assert files_holding(tmp_path, digest(b"made up for the test\n")) == [tmp_path / "card.html"]


# -- the plans ---------------------------------------------------------------------------------------------

def test_the_five_phase_2_plans_are_here():
    assert [p.stem for p in PLANS] == ["TYR0-P2-PASS1-v1", "TYR0-P2-PASS2A-v1", "TYR0-P2-PASS2B-v1",
                                       "TYR0-P2-PASS3-v1", "TYR0-P2-PASS4-v1"]


@pytest.mark.parametrize("path", PLANS, ids=lambda p: p.stem)
def test_each_plan_is_well_formed_and_leaves_the_protective_commands_alone(path):
    document = plan(path)
    assert check("tyr0_plan", document) == [] and _consistency(document) == []
    assert _protective_restrictions(document) == [] and document["plan_id"] == path.stem


@pytest.mark.parametrize("path", PLANS, ids=lambda p: p.stem)
def test_each_plans_contact_window_is_one_the_u35_tests_use(path):
    document = plan(path)
    window = (document["contact_window"]["aos_met_s"], document["contact_window"]["los_met_s"])
    assert window in FLOWN[document["scenario_id"]]
    assert document["valid_until_met_s"] == window[1]   # in force from the run's start to its LOS


def test_every_window_the_u35_tests_use_has_its_plan():
    windows = {(d["scenario_id"], d["contact_window"]["aos_met_s"], d["contact_window"]["los_met_s"])
               for d in map(plan, PLANS)}
    assert windows == {(scenario, aos, los) for scenario, spans in FLOWN.items() for aos, los in spans}


def test_red_a_window_off_by_one_second_is_not_one_the_u35_tests_use():
    assert (801, 1230) not in FLOWN["P3_stuck_load"]


@pytest.mark.parametrize("path", PLANS, ids=lambda p: p.stem)
def test_every_hash_a_plan_lists_is_a_file_here_or_a_placeholder(path):
    document = plan(path)
    here = {digest(p.read_bytes()) for folder in (INPUTS, REPO_ROOT / "plans", REPO_ROOT / "odin" / "study")
            for p in folder.rglob("*") if p.is_file()}
    listed = [ref["sha256"] for ref in document["procedures_in_force"] + document["references"]]
    assert [sha for sha in listed if sha != ZEROS and sha not in here] == []
    for ref in document["procedures_in_force"]:
        if ref["sha256"] != ZEROS:
            assert digest((INPUTS / "procedures" / f"v{ref['version']}" / f"{ref['id']}.md").read_bytes()) == ref["sha256"]


@pytest.mark.parametrize("path", PLANS, ids=lambda p: p.stem)
def test_every_procedure_a_plan_names_is_placed(path):
    assert [ref["id"] for ref in plan(path)["procedures_in_force"] if ref["sha256"] == ZEROS] == []


def test_contact_a_is_frozen_and_listed_by_pass_2b():
    frozen = FROZEN.read_bytes()
    assert generate() == frozen
    rows = frozen.decode().splitlines()
    assert (len(rows), rows[1].split(",")[11], rows[-1].split(",")[11]) == (331, "2190", "2519")
    [reference] = [r for r in plan(REPO_ROOT / "plans" / "TYR0-P2-PASS2B-v1.yaml")["references"]
                   if r["name"].startswith("Contact A telemetry")]
    assert reference["sha256"] == digest(frozen)


def test_the_dictionary_is_huginns_v0_5_at_b4dbe61_byte_for_byte():
    copy = (INPUTS / "dictionary" / "tlm_cmd_dictionary_v0.5.md").read_bytes()
    pinned = subprocess.run(["git", "-C", str(REPO_ROOT / "deps" / "huginn"), "show", "b4dbe61:docs/tlm_cmd_dictionary.md"],
                            capture_output=True, check=True).stdout
    assert copy == pinned and digest(copy) == DICTIONARY


@pytest.mark.parametrize("path", PLANS, ids=lambda p: p.stem)
def test_each_plan_ends_its_references_with_the_dictionary_and_baldur0s_class_table(path):
    assert [(r["name"], r["sha256"]) for r in plan(path)["references"][-2:]] == [
        ("HUGINN command and telemetry dictionary v0.5 (HUGINN b4dbe61)", DICTIONARY),
        ("BALDUR-0's command classes, generated from its class configuration", digest(CLASS_TABLE.read_bytes()))]


# -- the arming acts ---------------------------------------------------------------------------------------

def test_the_arming_acts_cover_the_runs_section_3_lists_and_phase_1s_second_run():
    # ARM-PH1-R2 for phase 1's second run (the Director's ruling of 29 October 2026, after R1's build defect).
    acts = {p.stem: yaml.safe_load(p.read_bytes()) for p in ACTS}
    assert sorted(acts) == ["ARM-PH1", "ARM-PH1-R2", "ARM-PH2-PASS1", "ARM-PH2-PASS2A", "ARM-PH2-PASS2B",
                            "ARM-PH2-PASS3", "ARM-PH2-PASS4"]
    for act_id, act in acts.items():
        assert check("arming_act", act) == [] and act["act_id"] == act_id
        assert (act["rung"], act["expires_utc"], len(act["plan_chain_hashes"])) == (
            "AI_AUTONOMOUS", "2026-11-05T02:00:00.000Z", 1)
    assert acts["ARM-PH1"]["runs"] == ["PH1-SHAKEDOWN-SPARK-R1"]
    assert acts["ARM-PH1-R2"]["runs"] == ["PH1-SHAKEDOWN-SPARK-R2"]
    assert acts["ARM-PH2-PASS3"]["runs"] == [f"PH2-PASS3-{m}-R{n}" for m in ("SPARK", "OPEN") for n in range(1, 6)]
