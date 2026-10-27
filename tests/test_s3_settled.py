"""No design choice in gateway/ is left UNSETTLED (00_HANDOFF.md §4, S3). Where BALDUR-0's draft
decides something the contract does not, the code says so with a marker naming the open point, and
this test stays red until the Director has ruled on each."""

from tests.repo_checks import REPO_ROOT
from tests.schema_checks import MARKER


def markers(folder):
    return [f"{path.name}:{number}: {line.strip()}" for path in sorted(folder.glob("*.py"))
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if MARKER.search(line)]


def test_no_unsettled_marker_remains_in_gateway():
    assert markers(REPO_ROOT / "gateway") == []


def test_a_settled_folder_passes(tmp_path):
    (tmp_path / "rules.py").write_text('"""Settled."""\nX = 1\n', encoding="utf-8")
    assert markers(tmp_path) == []


def test_red_a_marker_in_a_gateway_file_is_caught(tmp_path):
    (tmp_path / "rules.py").write_text("X = 1\n# Unsettled (U99): which X.\n", encoding="utf-8")
    assert markers(tmp_path) == ["rules.py:2: # Unsettled (U99): which X."]
