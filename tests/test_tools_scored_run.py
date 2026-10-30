"""tools/scored_run.py refuses to start a scored run while a series stop stands (the Director's rulings of 29
October 2026, and his word of 30 October 2026: "The launcher refuses to start while a stop stands"): a second
set-aside for the same cause stops the series until he lifts it."""

import pytest
import yaml

import eval.set_aside as aside
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

    def make_run(run_id):
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
