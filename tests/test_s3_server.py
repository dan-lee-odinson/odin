"""BALDUR-0's endpoints (CONTRACT.md §8.2): POST /request and POST /escalation on the baldur0 port of
config/ports.yaml. Each test runs a server on a free local port, bound to a started run's Gateway.
The last tests send requests with ODIN's own loop code, signing and transport both, from odin/."""

import json
import threading
import time

import pytest

from contract.validate import check
from gateway.server import baldur0_address, make_server
from tests.baldur_world import RUN, World
from tests.repo_checks import REPO_ROOT
from tests.test_s2_event_log import example
from tests.test_s2_server import post


@pytest.fixture
def served(tmp_path):
    world = World(tmp_path)
    assert world.start()
    replies = []
    server = make_server(world.gateway, ("127.0.0.1", 0), after_request=replies.append)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield world, f"http://127.0.0.1:{server.server_address[1]}", replies
    server.shutdown()
    server.server_close()


def after_reply(replies, timeout=5.0):
    """What after_request was given. It runs once the reply has been sent, so a client can hold the reply
    before it has run."""
    deadline = time.monotonic() + timeout
    while not replies and time.monotonic() < deadline:
        time.sleep(0.01)
    return replies


def test_after_request_runs_only_once_the_reply_is_sent(tmp_path):
    world = World(tmp_path)
    assert world.start()
    release, replies = threading.Event(), []
    server = make_server(world.gateway, ("127.0.0.1", 0),
                         after_request=lambda record: release.wait(5) and replies.append(record))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, record = post(f"http://127.0.0.1:{server.server_address[1]}/request",
                              world.request("CMD_SAFE_ENTER", {}))
        assert status == 200 and replies == []   # the client has the reply; the hook has not run
        release.set()
        assert after_reply(replies) == [record]
    finally:
        server.shutdown()
        server.server_close()


def test_baldur0_listens_where_config_ports_yaml_says():
    assert baldur0_address() == ("127.0.0.1", 8711)
    assert (REPO_ROOT / "config" / "ports.yaml").read_text(encoding="utf-8").count("baldur0: 8711") == 1


def test_an_allowed_request_is_answered_with_its_decision_record(served):
    world, base, replies = served
    status, record = post(base + "/request", world.request("CMD_SAFE_ENTER", {}))
    assert status == 200 and record["decision"] == "ALLOW"
    assert check("decision_record", record) == []
    assert world.bodies("DECISION") == [record]
    assert after_reply(replies) == [record]


def test_a_refused_request_is_answered_with_its_decision_record_too(served):
    world, base, replies = served
    status, record = post(base + "/request", world.request("CMD_PLD_SET_RATE", {"rate": 1.0}))
    assert status == 200 and record["decision"] == "REFUSE"
    assert after_reply(replies) == [record]


BAD_BODIES = {
    "a request with no signature": lambda w: {k: v for k, v in w.request("CMD_SAFE_ENTER", {}).items()
                                              if k != "signature"},
    "a request whose command the dictionary does not have": lambda w: w.request("CMD_SELF_DESTRUCT", {}),
    "a request whose parameters do not fit its command": lambda w: w.request("CMD_PLD_SET_STATE", {"state": "DIM"}),
    "a body that is not JSON": lambda w: b"command: CMD_SAFE_ENTER",
    "a body holding NaN": lambda w: json.dumps(w.request("CMD_SAFE_ENTER", {})).replace('"met_s": 100.0',
                                                                                        '"met_s": NaN').encode(),
}


@pytest.mark.parametrize("title", BAD_BODIES)
def test_red_a_body_that_is_not_a_request_gets_400_and_writes_nothing(served, title):
    world, base, replies = served
    before = world.records()
    status, reply = post(base + "/request", BAD_BODIES[title](world))
    assert status == 400 and reply["problems"]
    assert world.records() == before and replies == []


def test_red_an_unknown_endpoint_gets_404(served):
    world, base, _ = served
    status, reply = post(base + "/log/agent", world.request("CMD_SAFE_ENTER", {}))
    assert status == 404 and reply["problems"]
    assert world.bodies("REQUEST") == []


def test_every_refusal_is_answered_though_its_body_is_large(served):
    # A reply sent before the body is read reached the client as a reset connection about one time
    # in three for a body this size on Windows, so twenty in a row would almost never all arrive.
    world, base, _ = served
    for _ in range(20):
        assert post(base + "/log/agent", b"x" * 100_000)[0] == 404
        assert post(base + "/request", b"x" * 100_000)[0] == 400


@pytest.mark.parametrize("contact, delivery", [("IN_CONTACT", "NOW"), ("OUT_OF_CONTACT", "QUEUED_UNTIL_AOS")])
def test_an_escalation_is_logged_and_its_delivery_said(served, contact, delivery):
    world, base, replies = served
    world.contact = contact
    escalation = example("escalation/good-escalation.json")
    status, reply = post(base + "/escalation", escalation)
    [logged] = world.records("ESCALATION")
    assert (status, reply) == (200, {"record_id": logged["record_id"], "delivery": delivery})
    assert check("escalation_reply", reply) == []
    assert logged["body"] == escalation
    assert replies == [] and world.gateway.pending() == []


def test_red_an_escalation_that_is_not_one_gets_400(served):
    world, base, _ = served
    status, reply = post(base + "/escalation", {**example("escalation/good-escalation.json"), "urgency": "NOW!"})
    assert status == 400 and reply["problems"]
    assert world.records("ESCALATION") == []


# -- ODIN's own code against BALDUR-0 ----------------------------------------------------------

@pytest.fixture
def odin_signs_with(monkeypatch):
    """ODIN's signer, reading its private key from ODIN_KEY_PATH, given the test's in-memory key instead."""
    from odin.loop import signing

    def use(key):
        monkeypatch.setattr(signing, "load_private_key", lambda private_key_path=None: key)
        return signing.build_signed_request
    return use


def _odin_request(world, build, command, parameters):
    return build(command=command, parameters=parameters, rationale="test", run_id=RUN, turn_id=3,
                 plan_id="TYR0-DEV-PASS1-v1", met_s=world.met, utc=world.utc(),
                 agent_input_hash="sha256:" + "cd" * 32)


def test_a_request_signed_and_sent_by_odins_loop_code_is_allowed(served, odin_signs_with):
    from odin.loop.loop import _http_json
    world, base, _ = served
    request = _odin_request(world, odin_signs_with(world.odin), "CMD_MODE_SET", {"target": "LOW_POWER"})
    status, data = _http_json("POST", base + "/request", request)
    record = json.loads(data)
    assert status == 200 and record["decision"] == "ALLOW" and record["lease_id"] == "L1"
    assert world.bodies("REQUEST") == [request]


def test_a_refusal_reaches_odins_transport_as_a_reply_not_an_error(served, odin_signs_with):
    from odin.loop.loop import _http_json
    world, base, _ = served
    request = _odin_request(world, odin_signs_with(world.odin), "CMD_PLD_SET_RATE", {"rate": 1.0})
    status, data = _http_json("POST", base + "/request", request)
    assert status == 200 and json.loads(data)["decision"] == "REFUSE"


def test_red_a_request_odins_code_signs_with_another_key_is_refused(served, odin_signs_with):
    from odin.loop.loop import _http_json
    world, base, _ = served
    request = _odin_request(world, odin_signs_with(world.dev), "CMD_SAFE_ENTER", {})
    _, data = _http_json("POST", base + "/request", request)
    assert [c["reason"] for c in json.loads(data)["checks"] if c["result"] == "FAIL"] == ["BAD_SIGNATURE"]
