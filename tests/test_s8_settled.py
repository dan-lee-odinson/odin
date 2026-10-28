"""No design choice in eval/ is left UNSETTLED (00_HANDOFF.md §4, S8). Where the draft decides something the
Director's scoring ruling does not, the code says so with a marker naming the open point, and this test stays
red until he has ruled on each."""

from tests.repo_checks import REPO_ROOT
from tests.test_s3_settled import markers


def test_no_unsettled_marker_remains_in_eval():
    assert markers(REPO_ROOT / "eval") == []
