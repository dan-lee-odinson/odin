"""M3: U30 — BALDUR-0 replies and ODIN's transport handling."""
import json

from odin.adapters.stand_in import StandInAdapter
from odin.devtools.fake_harness import FakeServices
from odin.loop import signing
from odin.loop.loop import TurnLoop
from conftest import bundle_bytes, make_bundle

CMD = '{"kind":"command","command":"CMD_PLD_SET_STATE","parameters":{"state":"ON"}}'


def _world(tmp_path, baldur_suffix=""):
    priv = tmp_path / "k1"
    pub = tmp_path / "k1.pub"
    signing.generate_keypair_files(priv, pub)
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=pub)
    loop = TurnLoop(
        harness_url=services.url, baldur_url=services.url + baldur_suffix,
        log_url=services.url, adapter=StandInAdapter(script=lambda t, b: CMD),
        repo_root=tmp_path, transport=services.transport, private_key_path=str(priv),
        instructions="x", frozen_reference="y",
    )
    return services, loop


def test_refuse_200_is_normal_outcome_no_retry(tmp_path):
    services, loop = _world(tmp_path)
    # Wrong public key at the fake BALDUR-0: signature fails, REFUSE at ORIGIN.
    other_priv = tmp_path / "k2"
    other_pub = tmp_path / "k2.pub"
    signing.generate_keypair_files(other_priv, other_pub)
    services.public_key_path = str(other_pub)
    results = loop.run(max_turns=5)
    assert results[0]["outcome"] == "refused"
    assert results[0]["decision"]["decision"] == "REFUSE"
    assert services.request_attempts == 1
    assert services.escalations == [] and services.reports == []


def test_allow_200_still_sends_one_request(tmp_path):
    services, loop = _world(tmp_path)
    results = loop.run(max_turns=5)
    assert results[0]["outcome"] == "request"
    assert services.request_attempts == 1
    assert services.decisions[-1]["decision"] == "ALLOW"


def test_invalid_request_body_400_nothing_logged(tmp_path):
    services, _ = _world(tmp_path)
    status, raw = services.transport("POST", "/request", b'{"command": "CMD_PLD_SET_STATE"}')
    assert status == 400
    assert json.loads(raw)["problems"]
    assert services.requests == [] and services.decisions == []


def test_400_ends_turn_without_retry_or_crash(tmp_path):
    services, loop = _world(tmp_path)
    services.force_status = {"/request": 400}
    results = loop.run(max_turns=5)
    assert results[0]["outcome"] == "error"
    assert services.request_attempts == 1


def test_404_ends_turn_without_retry_or_crash(tmp_path):
    services, loop = _world(tmp_path, baldur_suffix="/missing")
    results = loop.run(max_turns=5)
    assert results[0]["outcome"] == "error"
    assert services.request_attempts == 1


def test_unknown_path_404(tmp_path):
    services, _ = _world(tmp_path)
    status, _ = services.transport("GET", "/nope", None)
    assert status == 404
