"""No design choice in harness/ is left UNSETTLED (00_HANDOFF.md §4, S6). Where the draft decides
something the contract does not, the code says so with a marker naming the open point, and this test
stays red until the Director has ruled on each. BALDUR-0's markers are test_s3_settled's."""

from tests.repo_checks import REPO_ROOT
from tests.test_s3_settled import markers


def test_no_unsettled_marker_remains_in_the_harness():
    assert markers(REPO_ROOT / "harness") == []
