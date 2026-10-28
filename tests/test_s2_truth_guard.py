"""The truth file is kept apart (CONTRACT.md §12): runs/<run_id>/truth.jsonl holds fault onsets and the
simulator's true state, for evaluation only, and ODIN never reads it. Only the log, the wrapper, the
harness, eval and VERDA's viewer, which plays a finished run back (the Director's ruling on U63, 28 October
2026), may name it in code; not ODIN, BALDUR-0 or the connector.
"""

import pytest

from tests.repo_checks import REPO_ROOT, check_truth_kept_apart


def test_only_the_writers_and_eval_name_the_truth_file():
    assert check_truth_kept_apart(REPO_ROOT) == []


# Red cases: each planted in a scratch tree.

READS = 'open("runs/dev-run-0001/truth.jsonl")\n'

PLANTED = {
    "ODIN's loop": ("odin/loop/turn.py", READS),
    "ODIN's instructions": ("odin/instructions/template.json", '{"see": "runs/x/truth.jsonl"}\n'),
    "BALDUR-0": ("gateway/decide.py", READS),
    "the COSMOS connector": ("connector/read.py", READS),
    "a configuration file": ("config/run.yaml", "truth: runs/dev-run-0001/truth.jsonl\n"),
}


@pytest.mark.parametrize("where", PLANTED)
def test_red_naming_the_truth_file_is_caught(tmp_path, where):
    rel, text = PLANTED[where]
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text(text, encoding="utf-8")
    assert check_truth_kept_apart(tmp_path) != []


# VERDA's viewer, deposited into viewer/ (U63): its page, its script and its converter.
VIEWER = {"viewer/index.html": '<script>fetch("../runs/dev-run-0001/truth.jsonl")</script>\n',
          "viewer/app.js": 'fetch("runs/dev-run-0001/truth.jsonl")\n',
          "viewer/convert.py": READS}


def test_the_viewer_may_name_the_truth_file(tmp_path):
    for rel, text in VIEWER.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert check_truth_kept_apart(tmp_path) == []


def test_red_odin_naming_the_truth_file_is_still_caught_beside_a_viewer_that_may(tmp_path):
    for rel, text in {**VIEWER, "odin/adapters/replay.py": READS}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert [problem.split(":")[0] for problem in check_truth_kept_apart(tmp_path)] == ["odin/adapters/replay.py"]


@pytest.mark.parametrize("rel", ["log/event_log.py", "wrapper/faults.py", "harness/run.py", "eval/score.py",
                                 "README.md"])
def test_the_writers_eval_and_prose_may_name_it(tmp_path, rel):
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_text(READS, encoding="utf-8")
    assert check_truth_kept_apart(tmp_path) == []
