"""No design choice in wrapper/ or connector/ is left UNSETTLED (00_HANDOFF.md §4, S4). Where the draft
decides something the contract does not, the code says so with a marker naming the open point, and this
test stays red until the Director has ruled on each."""

from tests.repo_checks import REPO_ROOT
from tests.test_s3_settled import markers


def test_no_unsettled_marker_remains_in_the_wrapper():
    assert markers(REPO_ROOT / "wrapper") == []


def test_no_unsettled_marker_remains_in_the_connector():
    assert markers(REPO_ROOT / "connector") == []
