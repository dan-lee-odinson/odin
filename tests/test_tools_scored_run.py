"""tools/scored_run.py refuses to start a scored run while a series stop stands (the Director's rulings of 29
October 2026, and his word of 30 October 2026: "The launcher refuses to start while a stop stands"): a second
set-aside for the same cause stops the series until he lifts it. Phase 3's runs fly what the held-out folder holds,
read at run time (S9): checked here on a made-up one, since none of the held-out files, labels or values is in the
repository."""

import json

import pytest
import yaml

import eval.set_aside as aside
from tests.test_s9_more_feeds import OTHERS, REPLAY, WEATHER
from tests.test_s9_phase3_setup import made_up
from tests.test_s9_revocation import SCRIPT
from tools import scored_run

RUN = "PH1-SHAKEDOWN-SPARK-R4"
FOUND = [{"cause": "MODEL_CALL_ERROR", "key": "MODEL_CALL ERROR", "detail": "made up", "record_id": 7}]


class Started(Exception):
    """go reached the point of making the run."""


@pytest.fixture
def marks(tmp_path, monkeypatch):
    path = tmp_path / "set_aside.yaml"
    monkeypatch.setattr(aside, "SET_ASIDE", path)
    monkeypatch.setattr(scored_run, "fly", lambda *a, **k: pytest.fail("a run flew"))

    def make_run(run_id, held_out=None):
        raise Started(run_id)
    monkeypatch.setattr(scored_run, "make_run", make_run)
    return path


def test_red_the_launcher_refuses_to_start_while_a_stop_stands(marks, capsys):
    aside.mark("PH2-A", 2, FOUND, marks)
    aside.mark("PH2-B", 2, FOUND, marks)
    assert scored_run.go(RUN) == 1
    assert "refused: the series is stopped until the Director lifts it: phase 2, MODEL_CALL ERROR, 2 runs" in (
        capsys.readouterr().out)


def test_the_launcher_starts_once_the_stop_is_lifted(marks):
    aside.mark("PH2-A", 2, FOUND, marks)
    aside.mark("PH2-B", 2, FOUND, marks)
    marks.write_bytes(marks.read_bytes() + b"  lifted: the Director's word, made up\n")
    with pytest.raises(Started):
        scored_run.go(RUN)


# -- phase 2 (the Director's word of 30 October 2026) ---------------------------------------------------------

def test_red_phase_2s_runs_are_exactly_those_each_signed_act_names_on_its_arm():
    named = {}
    for pass_name in scored_run.PASSES_PH2:
        act = yaml.safe_load(scored_run.act_ph2(pass_name).read_bytes())
        named.update({run_id: (pass_name, "spark" if "-SPARK-" in run_id else "spark_open") for run_id in act["runs"]})
    assert scored_run.RUNS_PH2 == named and len(named) == 50


def test_a_phase_2_run_is_scored_in_the_ground_seat_in_real_time_on_its_pass():
    run = scored_run.make_run("PH2-PASS2B-OPEN-R3")
    assert (run.phase, run.mode, run.seat, run.pacing, run.rate) == (2, "SCORED", "GROUND", "REAL_TIME", 1.0)
    assert run.plan_paths == [scored_run.ROOT / "plans" / "TYR0-P2-PASS2B-v1.yaml"]
    assert run.act_path == scored_run.ROOT / "acts" / "ARM-PH2-PASS2B.yaml"
    assert run.scenario_id == "P2_array_string_loss" and run.scenario is not None
    assert (run.config["model_config"], run.config["answer_method"]) == ("spark_open", "ANSWER_TOOLS")


@pytest.mark.parametrize("run_id, key, stop", [
    ("PH2-PASS1-SPARK-R1", "META_API_KEY", ("META_CREDIT", 125.0, "Meta")),
    ("PH2-PASS4-OPEN-R5", "BASETEN_API_KEY", ("BASETEN_CREDIT", 90.0, "Baseten")),
    (RUN, "META_API_KEY", ("META_CREDIT", 125.0, "Meta"))])
def test_each_run_takes_its_models_key_and_stop(run_id, key, stop):
    assert scored_run.needed(run_id) == (key, "ODIN_KEY_PATH")
    assert scored_run.STOPS[scored_run.model_of(run_id)] == stop


def test_a_phase_2_run_has_its_pass_contact_and_900_s_more():
    assert scored_run.timeout_of("PH2-PASS2A-SPARK-R1") == 2520 - 2190 + 900
    assert scored_run.timeout_of(RUN) == scored_run.TIMEOUT_S


def test_red_the_launcher_refuses_a_phase_2_run_while_a_stop_stands(marks):
    aside.mark("PH2-A", 2, FOUND, marks)
    aside.mark("PH2-B", 2, FOUND, marks)
    assert scored_run.go("PH2-PASS3-SPARK-R1") == 1


# -- phase 3 (S9; CONTRACT.md §10.3), on a made-up held-out folder ------------------------------------------------

FEEDS = {"other_stations": dict(OTHERS, schedule=[{"station": "STAND-IN-1", "beacon_met_s": 850, "report_met_s": 900}]),
         "space_weather": WEATHER}
ONBOARD = [{"from_met_s": 0, "to_met_s": 1240, "seat": "GROUND", "pacing": "REAL_TIME"},
           {"from_met_s": 1240, "to_met_s": 6500, "seat": "ONBOARD", "pacing": "CHARGED"},
           {"from_met_s": 6500, "to_met_s": 6900, "seat": "GROUND", "pacing": "REAL_TIME"}]
REVOKED = {"revocation": {"at": "made up"}, "restore": {"after_revocation_s": SCRIPT["restore_after_s"]},
           "second_presentation": {"after_restore_s": SCRIPT["second_presentation_after_s"]},
           "safety_test": {"after_restore_s": SCRIPT["safety_test_after_s"], "request": SCRIPT["safety_test_request"]}}


def held_out(tmp_path, runs=("PH3-H90-SPARK-R1",), script=None, seats=None):
    """A made-up held-out folder: the sealed H90, its plans as signed (the sealed bytes; a signature is BALDUR-0's to
    check when the run starts), and an arming act naming runs."""
    folder, seal = made_up(tmp_path, script=script, feeds=FEEDS, seats=seats,
                           extra={"space_weather_replay.json": json.dumps(REPLAY).encode()})
    (folder / "plans-to-sign").mkdir()
    for plan in sorted((folder / "sealed").glob("TYR0-*.yaml")):
        (folder / "plans-to-sign" / plan.name).write_bytes(plan.read_bytes())
    (folder / "acts").mkdir()
    (folder / "acts" / "ARM-PH3-H90.yaml").write_text(yaml.safe_dump({"runs": list(runs)}), encoding="utf-8")
    return folder, seal


def test_a_phase_3_run_flies_its_sealed_scenario_as_signed_on_its_arm(tmp_path):
    folder, seal = held_out(tmp_path, runs=("PH3-H90-SPARK-R1", "PH3-H90-OPEN-R2"))
    run = scored_run.make_run("PH3-H90-SPARK-R1", folder, seal=seal)
    assert (run.phase, run.mode, run.scenario_id, run.rate) == (3, "SCORED", "H90", 1.0)
    assert run.plan_paths == [folder / "plans-to-sign" / "TYR0-H90-C1-v1.yaml",
                              folder / "plans-to-sign" / "TYR0-H90-C2-v1.yaml"]
    assert run.act_path == folder / "acts" / "ARM-PH3-H90.yaml"
    assert (run.config["model_config"], run.config["answer_method"]) == ("spark", "STRUCTURED_OUTPUT")
    assert run.config["seed"] == 20260729   # HUGINN's public P1_nominal's own seed: the scenario's, not a constant
    assert (run.seats, run.onboard, run.revocation) == ([(0, 6900, "GROUND", "REAL_TIME")], None, None)
    assert scored_run.make_run("PH3-H90-OPEN-R2", folder, seal=seal).config["model_config"] == "spark_open"
    assert scored_run.Phase3("PH3-H90-SPARK-R1", folder, seal=seal).timeout_s() == 6900 - 0 + 900
    assert [scored_run.phase3_of(r) for r in ("PH3-H90-OPEN-R5", "PH3-H90-OPEN-R6", "PH2-PASS1-SPARK-R1")] == [
        ("H90", "OPEN", 5), None, None]


def test_red_a_signed_plan_that_is_not_the_sealed_bytes_refuses_the_run(tmp_path):
    folder, seal = held_out(tmp_path)
    signed = folder / "plans-to-sign" / "TYR0-H90-C2-v1.yaml"
    signed.write_bytes(signed.read_bytes() + b"# one byte more\n")
    with pytest.raises(ValueError, match="not the sealed plan's bytes"):
        scored_run.make_run("PH3-H90-SPARK-R1", folder, seal=seal)


def test_red_a_run_its_arming_act_does_not_name_is_refused(tmp_path):
    folder, seal = held_out(tmp_path, runs=("PH3-H90-SPARK-R1",))
    with pytest.raises(ValueError, match="does not name PH3-H90-SPARK-R2"):
        scored_run.make_run("PH3-H90-SPARK-R2", folder, seal=seal)


def test_red_an_onboard_seat_brings_glimmer_on_modal_beside_the_arms_model(tmp_path):
    folder, seal = held_out(tmp_path, seats=ONBOARD)
    run = scored_run.make_run("PH3-H90-SPARK-R1", folder, seal=seal)
    assert run.onboard == "glimmer_modal" and run.config["model_config"] == "spark"
    assert [seat for _, _, seat, _ in run.seats] == ["GROUND", "ONBOARD", "GROUND"]
    assert scored_run.needed("PH3-H90-SPARK-R1", run.onboard) == (
        "META_API_KEY", "ODIN_KEY_PATH", "ODIN_MODAL_PROXY_KEY", "ODIN_MODAL_PROXY_SECRET")
    assert scored_run.STOPS["glimmer_modal"] == ("MODAL_CREDIT", 125.0, "Modal")


def test_red_a_scripted_revocation_takes_the_restore_act_signed_for_its_own_run(tmp_path):
    folder, seal = held_out(tmp_path, runs=("PH3-H90-OPEN-R4",), script=REVOKED)
    run = scored_run.make_run("PH3-H90-OPEN-R4", folder, seal=seal)
    assert run.revocation == dict(SCRIPT, restore_act=folder / "acts" / "RST-PH3-H90-OPEN-R4.yaml")


def test_red_the_launcher_refuses_a_phase_3_run_while_a_stop_stands(marks):
    aside.mark("PH3-A", 3, FOUND, marks)
    aside.mark("PH3-B", 3, FOUND, marks)
    assert scored_run.go("PH3-H90-SPARK-R1", "no held-out folder is read while a stop stands") == 1
