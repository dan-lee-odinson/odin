"""The procedures and attachments a turn bundle carries (CONTRACT.md §6.2, §16.1 U5; the Director's ruling
on U43, 27 October 2026): every reference a plan lists, resolved by hash, rides beside PROC-001 with the
plan's hash, placeholders left out, and nothing from comparison-only/ is ever found. Checked against the
five phase-2 plans and the Director's inputs as placed."""

import hashlib
from types import SimpleNamespace

import pytest

from gateway.signed import load_yaml
from harness.procedures import PLACEHOLDER, MissingProcedure, ProcedureLibrary
from tests.repo_checks import REPO_ROOT

PLANS = sorted((REPO_ROOT / "plans").glob("TYR0-P2-*.yaml"))   # phase 2's; phase 1's waits on its procedure (U43)
CONTACT_A = "plans/TYR0-P2-PASS2B-v1.contact-a-telemetry.csv"
REFERENCE = "odin/study/cosmos_reference.md"   # ODIN's frozen COSMOS reference, from Muse Code's M4 deposit
NOTES = "plans/ODIN-PH1-console-notes.md"   # ODIN's phase-1 notes, R4's MET 1620 answer


def plan(path):
    document, problems = load_yaml(path.read_bytes())
    assert problems == []
    return SimpleNamespace(plan_id=document["plan_id"], document=document)


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="module")
def library():
    return ProcedureLibrary()


@pytest.mark.parametrize("path", PLANS, ids=lambda p: p.stem)
def test_every_reference_a_plan_lists_rides_beside_proc_001_with_the_plans_hash(library, path):
    one = plan(path)
    procedures = library.for_plan(one)
    listed = [(r["name"], r["sha256"]) for r in one.document["references"] if r["sha256"] != PLACEHOLDER]
    assert [p["id"] for p in procedures] == ["PROC-001", "PROC-002", "PROC-003"]
    assert [(a["name"], a["sha256"]) for a in procedures[0]["attachments"]] == listed
    assert all(digest(a["text"].encode("utf-8")) == a["sha256"] for a in procedures[0]["attachments"])
    assert [p["attachments"] for p in procedures[1:]] == [[], []]
    assert all(digest(p["text"].encode("utf-8")) == p["sha256"] for p in procedures)
    assert library.missing(SimpleNamespace(plans=[one])) == []


def test_every_pass_carries_the_frozen_cosmos_reference_and_its_own_inputs(library):
    by_stem = {p.stem: library.for_plan(plan(p))[0]["attachments"] for p in PLANS}
    reference = (REPO_ROOT / REFERENCE).read_bytes()
    assert digest(reference) == "sha256:c3f964cd81bd07a834c37c0e2c8ac503dbac2394e5e70c517dc8c4c8812e234f"
    assert all(attached[0]["text"].encode("utf-8") == reference for attached in by_stem.values())
    # The phase-1 notes, R4's MET 1620 answer, frozen on 29 October 2026, ride second on every pass.
    notes = (REPO_ROOT / NOTES).read_bytes()
    assert all(attached[1]["text"].encode("utf-8") == notes for attached in by_stem.values())
    assert [a["text"].encode("utf-8") for a in by_stem["TYR0-P2-PASS2B-v1"][2:3]] == [(REPO_ROOT / CONTACT_A).read_bytes()]
    # Every pass: the reference and the notes, then its own inputs, then the dictionary and BALDUR-0's class table.
    assert [len(by_stem[p.stem]) for p in PLANS] == [4, 4, 5, 6, 6]
    assert all([a["name"] for a in attached[-2:]] == ["HUGINN command and telemetry dictionary v0.5 (HUGINN b4dbe61)",
                                                       "BALDUR-0's command classes, generated from its class configuration"]
               for attached in by_stem.values())


def test_red_a_placeholder_is_not_attached(library):
    # The plans hold none since the phase-1 notes were filled in (29 October 2026), so one is set here.
    one = plan(REPO_ROOT / "plans" / "TYR0-P2-PASS4-v1.yaml")
    one.document["references"][1]["sha256"] = PLACEHOLDER
    assert sum(r["sha256"] == PLACEHOLDER for r in one.document["references"]) == 1
    assert PLACEHOLDER not in [a["sha256"] for a in library.for_plan(one)[0]["attachments"]]
    assert len(library.for_plan(one)[0]["attachments"]) == len(one.document["references"]) - 1


def test_red_a_file_in_comparison_only_is_never_found(library):
    record = REPO_ROOT / "inputs-pre-existing" / "comparison-only" / "pass-records" / "2026-10-11-P3" / "report.yaml"
    one = plan(REPO_ROOT / "plans" / "TYR0-P2-PASS3-v1.yaml")
    one.document["references"].append({"name": "PASS-3's flown record", "sha256": digest(record.read_bytes())})
    assert library.missing(SimpleNamespace(plans=[one])) == [
        f"TYR0-P2-PASS3-v1: reference \"PASS-3's flown record\" {digest(record.read_bytes())}"]
    with pytest.raises(MissingProcedure):
        library.for_plan(one)


def test_red_references_with_no_proc_001_in_force_to_ride_beside(library):
    one = plan(REPO_ROOT / "plans" / "TYR0-P2-PASS3-v1.yaml")
    one.document["procedures_in_force"] = one.document["procedures_in_force"][1:]
    assert library.missing(SimpleNamespace(plans=[one])) == [
        "TYR0-P2-PASS3-v1: references to attach but no PROC-001 in force to attach them beside"]
