"""GET /turn/next is a long poll that ODIN's loop gives up after 120 s and asks again (the Director's ruling on
U39). The abandoned request's handler is still waiting in the harness when the next one arrives, so a turn
that came due then could be taken by it and written to a closed connection, and be lost (the Director's
check of 28 October 2026). A poll whose client has gone, or that a newer poll has superseded, takes no turn."""

import json
import socket
import time
import urllib.error
import urllib.request

import pytest

from tests.harness_world import HarnessWorld, records

CHECK_IN = {"text": "ODIN, status?", "audio_sha256": None, "source": "TEXT", "utc": "2026-10-28T14:16:50.000Z"}


def poll(run, timeout):
    with urllib.request.urlopen(run.url("harness") + "/turn/next", timeout=timeout) as reply:
        return json.loads(reply.read())


def check_in(run):
    request = urllib.request.Request(run.url("harness") + "/checkin", data=json.dumps(CHECK_IN).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as reply:
        return json.loads(reply.read())


@pytest.fixture
def quiet(tmp_path):
    """A run in real time whose opening turns ODIN has taken, so nothing is due for a while."""
    run = HarnessWorld(tmp_path).run(pacing="REAL_TIME", rate=1.0)
    assert run.start()
    taken = []
    while len(taken) < 2 or run.queue.waiting():
        taken.append(poll(run, 5))
    yield run, taken
    run.stop()


def test_red_a_turn_due_after_odin_gave_up_a_poll_goes_to_its_next_poll(quiet):
    run, taken = quiet
    with pytest.raises((TimeoutError, socket.timeout, urllib.error.URLError)):
        poll(run, 0.5)   # ODIN gives up the wait and hangs up
    time.sleep(0.3)
    check_in(run)        # a turn comes due before ODIN asks again
    time.sleep(0.5)
    turn = poll(run, 5)
    assert (turn["turn_kind"], turn["report_kind"], turn["check_in_text"]) == ("REPORT", "CHECK_IN", CHECK_IN["text"])
    assert turn["turn_id"] == len(taken) + 1
    assert [r["body"]["turn_id"] for r in records(run, "TRIGGER")] == list(range(1, len(taken) + 2))


def test_a_poll_superseded_by_a_newer_one_takes_no_turn(quiet):
    run, taken = quiet
    # Two polls waiting at once, as when ODIN's loop asks again while the harness still holds its last
    # request: the turn goes to the newer, and the older takes none.
    first = run.next_turn
    import threading
    results = {}
    older = threading.Thread(target=lambda: results.setdefault("older", first()), daemon=True)
    older.start()
    time.sleep(0.3)
    newer = threading.Thread(target=lambda: results.setdefault("newer", first()), daemon=True)
    newer.start()
    time.sleep(0.3)
    check_in(run)
    newer.join(5)
    older.join(5)
    assert results["older"] is None
    assert json.loads(results["newer"])["check_in_text"] == CHECK_IN["text"]
