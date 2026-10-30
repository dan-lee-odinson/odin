"""S9's first piece (the Director's word of 29 October 2026): phase 3's scenarios read where they are sealed, outside
the repository, only after they check against the seal in force (harness/phase3.py). Checked on a made-up sealed
folder: none of the held-out files, labels or values is in the repository."""

import hashlib

import pytest
import yaml

from harness.phase3 import HeldOut, SealBroken, seal_in_force
from tests.baldur_world import changed, dump, example_plan
from tests.harness_world import PASS_PLAN_SHA256, PROCEDURE_SHA256
from tests.repo_checks import REPO_ROOT
from tests.test_phase3_seal import IN_FORCE

HUGINN = REPO_ROOT / "deps" / "huginn" / "sim" / "scenarios" / "P1_nominal.yaml"   # HUGINN's own, public


def made_up(folder, script=None):
    """A sealed folder of one made-up scenario, H90, with two plans; returns (folder, its seal)."""
    sealed = folder / "sealed"
    sealed.mkdir(parents=True)
    made = dict(scenario_id="H90", prohibited=[], envelope=[], leases=[],
                procedures_in_force=[{"id": "PROC-001", "version": "1", "sha256": PROCEDURE_SHA256}],
                references=[{"name": "Pass plan (made up)", "sha256": PASS_PLAN_SHA256}])
    plans = {"TYR0-H90-C1-v1": changed(example_plan(1), plan_id="TYR0-H90-C1-v1", pass_index=1, valid_from_met_s=0,
                                       valid_until_met_s=1240, contact_window={"aos_met_s": 800, "los_met_s": 1230},
                                       **made),
             "TYR0-H90-C2-v1": changed(example_plan(1), plan_id="TYR0-H90-C2-v1", pass_index=2, valid_from_met_s=1240,
                                       valid_until_met_s=6910, contact_window={"aos_met_s": 6500, "los_met_s": 6900},
                                       **made)}
    for plan_id, document in plans.items():
        (sealed / f"{plan_id}.yaml").write_bytes(dump(document))
    windows = [(d["contact_window"]["aos_met_s"], d["contact_window"]["los_met_s"]) for d in plans.values()]
    scenario = {"label": "H90", "plans": [f"{p}.yaml" for p in plans],
                "huginn": yaml.safe_load(HUGINN.read_text(encoding="utf-8")),
                "geometry": {"campaign_epoch_utc": "2026-07-29T14:00:00Z", "epoch_campaign_t_s": 257303,
                             "contacts": [{"aos_met_s": a, "los_met_s": b} for a, b in windows]},
                "run": {"start_met_s": 0, "end_met_s": windows[-1][1],
                        "seats": [{"from_met_s": 0, "to_met_s": windows[-1][1], "seat": "GROUND", "pacing": "REAL_TIME"}],
                        "check_ins": [{"met_s": b - 90} for _, b in windows]},
                "script": script or {}, "feeds": {}}
    (sealed / "H90.scenario.yaml").write_bytes(dump(scenario))
    manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(sealed.iterdir()))
    (sealed / "MANIFEST.sha256").write_text(manifest, encoding="utf-8", newline="\n")
    return folder, "sha256:" + hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def test_the_seal_in_force_is_the_first_hash_seal_md_names():
    assert seal_in_force() == IN_FORCE


def test_a_sealed_folder_that_matches_its_seal_gives_each_scenario_with_its_plans(tmp_path):
    folder, seal = made_up(tmp_path)
    held = HeldOut(folder, seal=seal)
    assert held.labels() == ["H90"]
    scenario = held.scenario("H90")
    assert scenario.scenario_id == "H90" and [p.name for p in scenario.plan_paths] == [
        "TYR0-H90-C1-v1.yaml", "TYR0-H90-C2-v1.yaml"]
    assert scenario.huginn.data == yaml.safe_load(HUGINN.read_text(encoding="utf-8"))   # HUGINN builds it unchanged
    assert scenario.windows == sorted(scenario.windows) and len(scenario.seats) == 1


def test_a_run_of_a_sealed_scenario_flies_its_plans_and_gives_the_check_ins_it_lists(tmp_path):
    # The plans are signed here with the test key, as a development run's are; a scored run's come signed.
    from tests.harness_world import HarnessWorld
    folder, seal = made_up(tmp_path / "held-out")
    scenario = HeldOut(folder, seal=seal).scenario("H90")
    (tmp_path / "world").mkdir()
    harness = HarnessWorld(tmp_path / "world")
    plans = harness.world.plans([p.read_bytes() for p in scenario.plan_paths], signer="dev")
    run = harness.run(plans=plans, scenario=scenario.huginn, scenario_id=scenario.scenario_id, phase=3)
    try:
        assert run.start()
        assert run._windows == scenario.windows
        assert [met_s for met_s, _ in run.check_ins] == sorted(c["met_s"] for c in scenario.run["check_ins"])
    finally:
        run.stop()


def test_red_a_sealed_file_changed_by_one_byte_is_refused(tmp_path):
    folder, seal = made_up(tmp_path)
    plan = folder / "sealed" / "TYR0-H90-C2-v1.yaml"
    plan.write_bytes(plan.read_bytes().replace(b"TYR0-H90-C2-v1", b"TYR0-H90-C2-v2", 1))
    with pytest.raises(SealBroken, match="TYR0-H90-C2-v1.yaml does not match the sealed manifest"):
        HeldOut(folder, seal=seal)


def test_red_a_file_the_manifest_does_not_list_is_refused(tmp_path):
    folder, seal = made_up(tmp_path)
    (folder / "sealed" / "TYR0-H90-C1-v1.yaml.sig").write_bytes(b"not sealed\n")
    with pytest.raises(SealBroken, match="not in its manifest"):
        HeldOut(folder, seal=seal)


def test_red_a_sealed_folder_that_is_not_the_seal_in_force_is_refused(tmp_path):
    folder, _ = made_up(tmp_path)
    with pytest.raises(SealBroken, match="not the seal in force"):
        HeldOut(folder)


def test_red_a_scenario_naming_a_plan_that_is_not_sealed_is_refused(tmp_path):
    folder, _ = made_up(tmp_path)
    scenario = folder / "sealed" / "H90.scenario.yaml"
    scenario.write_bytes(scenario.read_bytes().replace(b"TYR0-H90-C2-v1.yaml", b"TYR0-H90-C3-v1.yaml"))
    manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
                       for p in sorted((folder / "sealed").iterdir()) if p.name != "MANIFEST.sha256")
    (folder / "sealed" / "MANIFEST.sha256").write_text(manifest, encoding="utf-8", newline="\n")
    held = HeldOut(folder, seal="sha256:" + hashlib.sha256(manifest.encode("utf-8")).hexdigest())
    with pytest.raises(SealBroken, match="names plan TYR0-H90-C3-v1.yaml, which is not sealed"):
        held.scenario("H90")
