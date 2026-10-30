"""tools/scored_run.py refuses to start a scored run while a series stop stands (the Director's rulings of 29
October 2026, and his word of 30 October 2026: "The launcher refuses to start while a stop stands"): a second
set-aside for the same cause stops the series until he lifts it."""

import pytest

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
