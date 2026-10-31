"""The record's gaps closed (the Director's ruling of 29 October 2026, "Close them"): a refusal of what ODIN's own loop
sent to the log or to BALDUR-0, and a failure a request handler did not foresee, each end the run with ERROR and say
so as RUN_END's detail, where before they left nothing in the record. A tool call the harness refuses for the
model's own arguments is the model's, and the run goes on."""

import json
import time
import urllib.error
import urllib.request

import pytest

from tests.harness_world import HarnessWorld, records


def poll(run, timeout=5):
    with urllib.request.urlopen(run.url("harness") + "/turn/next", timeout=timeout) as reply:
        return json.loads(reply.read())


def post(url, body):
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as reply:
            return reply.status
    except urllib.error.HTTPError as error:
        return error.code


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as reply:
            return reply.status
    except urllib.error.HTTPError as error:
        return error.code


@pytest.fixture
def flying(tmp_path):
    """A run in real time whose opening turns ODIN has taken."""
    run = HarnessWorld(tmp_path).run(pacing="REAL_TIME", rate=1.0)
    assert run.start()
    while len(records(run, "TRIGGER")) < 2 or run.queue.waiting():
        poll(run)
    yield run
    run.stop()


def ended_with(run):
    """ODIN's next poll is told the run is complete; RUN_END's reason and detail."""
    assert poll(run) == {"run_complete": True}
    [end] = records(run, "RUN_END")
    return end["body"]["reason"], end["body"]["detail"]


def test_red_the_log_refusing_odins_record_ends_the_run_with_error(flying):
    assert post(flying.url("log") + "/log/agent", {"type": "MODEL_CALL", "body": {}}) == 400
    reason, detail = ended_with(flying)
    assert reason == "ERROR" and detail.startswith("the log refused ODIN's POST /log/agent (400): ")


def test_red_baldur0_refusing_odins_request_before_deciding_ends_the_run_with_error(flying):
    assert post(flying.url("baldur0") + "/request", {"not": "a request"}) == 400
    reason, detail = ended_with(flying)
    assert reason == "ERROR" and detail.startswith("BALDUR-0 refused ODIN's POST /request (400): ")


def test_red_a_handler_failure_nobody_foresaw_ends_the_run_with_error(flying, monkeypatch):
    def broken(q):
        raise RuntimeError("made up")
    monkeypatch.setattr(flying, "docs_lookup", broken)
    assert get(flying.url("harness") + "/docs/lookup?q=load") == 500
    reason, detail = ended_with(flying)
    assert (reason, detail) == ("ERROR", "the harness failed on GET /docs/lookup: RuntimeError('made up')")


def test_a_tool_call_refused_for_the_models_own_arguments_does_not_end_the_run(flying):
    assert get(flying.url("harness") + "/history?points=NOT_A_POINT&window_s=0") == 400
    # The handler's reply comes before anything it does after it, so the run is watched a while, not read once: read
    # once, a full dry run of 31 October 2026 missed the made-up failure after the reply.
    watched_until = time.monotonic() + 0.5
    while time.monotonic() < watched_until:
        assert flying.failed is None
        time.sleep(0.02)
    assert records(flying, "RUN_END") == []
