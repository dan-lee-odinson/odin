"""The event log's endpoints (CONTRACT.md §8.3; the Director's ruling on U24, 26 October 2026): POST
/log/agent and POST /report reply 200 {"record_id": n} on success and 400 {"problems": [...]} on
refusal, when nothing is written. Each test runs a server on a free local port."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from contract.validate import check
from log.server import log_address, make_server
from tests.test_s2_event_log import example, new_log
from tests.repo_checks import REPO_ROOT


@pytest.fixture
def served(tmp_path):
    log = new_log(tmp_path)
    server = make_server(log, ("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield log, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def post(url, body):
    data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_the_log_listens_where_config_ports_yaml_says():
    assert log_address() == ("127.0.0.1", 8712)
    assert (REPO_ROOT / "config" / "ports.yaml").read_text(encoding="utf-8").count("log: 8712") == 1


def test_a_submission_is_written_and_answered_with_its_record_id(served):
    log, base = served
    status, reply = post(base + "/log/agent", {"type": "AGENT_INPUT", "body": example("agent_input/good-input.json")})
    assert (status, reply) == (200, {"record_id": 1})
    assert check("log_reply", reply) == []
    status, reply = post(base + "/log/agent", {"type": "SPEND", "body": example("spend/good-after-call.json")})
    assert (status, reply) == (200, {"record_id": 2})


def test_a_report_is_written_and_answered_with_its_record_id(served):
    log, base = served
    status, reply = post(base + "/report", example("report/good-check-in.json"))
    assert (status, reply) == (200, {"record_id": 1})
    assert json.loads(log.path.read_bytes().splitlines()[0])["type"] == "REPORT"


REFUSED = {
    "a decision on /log/agent": ("/log/agent", {"type": "DECISION", "body": example("decision_record/good-allow.json")}),
    "a body that does not fit its type": ("/log/agent", {"type": "SPEND", "body": {"turn_id": 3}}),
    "a report without its answer": ("/report", {k: v for k, v in example("report/good-check-in.json").items()
                                                if k != "answer"}),
    "a report sent to /log/agent": ("/log/agent", example("report/good-check-in.json")),
    "a body that is not JSON": ("/log/agent", b"{not json"),
    "a list instead of an object": ("/log/agent", [1, 2]),
}


@pytest.mark.parametrize("case", REFUSED)
def test_red_a_refused_submission_gets_400_and_writes_nothing(served, case):
    log, base = served
    path, body = REFUSED[case]
    status, reply = post(base + path, body)
    assert status == 400
    assert check("log_refusal", reply) == []
    assert log.path.read_bytes() == b""


def test_red_an_unknown_endpoint_writes_nothing(served):
    log, base = served
    status, reply = post(base + "/log/system", {"type": "DECISION", "body": {}})
    assert status == 404 and reply["problems"]
    assert log.path.read_bytes() == b""


def test_every_refusal_is_answered_though_its_body_is_large(served):
    # A reply sent before the body is read can reach the client as a reset connection instead. On
    # Windows, with a body this size, the server that did so lost 42 of 50 replies.
    log, base = served
    body = b"x" * 4_000_000
    for _ in range(50):
        assert post(base + "/log/system", body)[0] == 404
    assert log.path.read_bytes() == b""
