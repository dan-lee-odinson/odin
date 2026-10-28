"""M1: turn loop end to end on the stand-in (§4.1, §6–§8)."""
import hashlib
import json
from pathlib import Path

import pytest

from odin.adapters.stand_in import StandInAdapter
from odin.devtools.fake_harness import FakeServices
from odin.loop import signing
from odin.loop.loop import TurnLoop
from conftest import RUN_ID, bundle_bytes, make_bundle

REPORT_BODY = {
    "timeline": [{"met_s": 100, "event": "Pass started."}],
    "actions": [],
    "condition": {"summary": "Spacecraft nominal.", "evidence": []},
    "deferred": [],
    "open_issues": [],
}
CHECKIN_BODY = dict(REPORT_BODY, answer="Spacecraft is nominal.")


def script_for(turn_id: int, bundle: dict) -> str:
    if bundle["turn_kind"] == "REPORT":
        body = CHECKIN_BODY if bundle["report_kind"] == "CHECK_IN" else REPORT_BODY
        return json.dumps(body)
    cycle = turn_id % 4
    if cycle == 1:
        return '{"kind":"command","command":"CMD_PLD_SET_STATE","parameters":{"state":"ON"},"rationale":"Payload on."}'
    if cycle == 2:
        return '{"kind":"none","rationale":"Nothing due."}'
    if cycle == 3:
        return json.dumps(
            {
                "kind": "escalation",
                "escalation_kind": "MALFUNCTION",
                "refs": ["EPS_BATT_SOC"],
                "proposed": None,
                "urgency": "ROUTINE",
                "rationale": "Watching battery.",
            }
        )
    return '{"kind":"command","command":"CMD_SAFE_ENTER","parameters":{},"rationale":"Protective check."}'


def build_world(tmp_path, n_turns=20):
    bundles = []
    for i in range(1, n_turns + 1):
        if i == 5:
            b = make_bundle(i, turn_kind="REPORT", report_kind="PASS_START")
        elif i == 10:
            b = make_bundle(i, turn_kind="REPORT", report_kind="CHECK_IN")
        else:
            b = make_bundle(i, turn_kind="ACT")
        bundles.append(b)
    priv_path = tmp_path / "odin_test_key"
    pub_path = tmp_path / "odin.pub"
    signing.generate_keypair_files(priv_path, pub_path)
    services = FakeServices(bundles=[bundle_bytes(b) for b in bundles], public_key_path=pub_path)
    services.start()
    adapter = StandInAdapter(script=script_for)
    loop = TurnLoop(
        harness_url=services.url,
        baldur_url=services.url,
        log_url=services.url,
        adapter=adapter,
        repo_root=tmp_path,
        transport=services.transport,
        private_key_path=str(priv_path),
        instructions="Test instructions. Fly by the plan.",
        frozen_reference="Frozen COSMOS reference (test).",
    )
    return services, loop


def test_twenty_turn_stand_in_run(tmp_path, keypair):
    services, loop = build_world(tmp_path, 20)
    try:
        results = loop.run(max_turns=50)
    finally:
        services.stop()
    assert len(results) == 20
    kinds = [r["outcome"] for r in results]
    assert kinds.count("request") >= 5
    assert kinds.count("none") >= 3
    assert kinds.count("escalation") >= 3
    assert kinds.count("report") == 2
    assert len(services.requests) == kinds.count("request")
    assert len(services.reports) == 2
    assert len(services.escalations) == kinds.count("escalation")
    # Every turn logged AGENT_INPUT before its CANDIDATE.
    types = [r["type"] for r in services.log_records]
    assert types.count("AGENT_INPUT") == 20
    for idx, t in enumerate(types):
        if t == "CANDIDATE":
            assert "AGENT_INPUT" in types[:idx]


def test_saved_inputs_hash_to_logged_hashes(tmp_path, keypair):
    services, loop = build_world(tmp_path, 3)
    try:
        loop.run(max_turns=10)
    finally:
        services.stop()
    inputs_dir = tmp_path / "runs" / RUN_ID / "inputs"
    assert inputs_dir.is_dir()
    agent_inputs = [r["body"] for r in services.log_records if r["type"] == "AGENT_INPUT"]
    assert len(agent_inputs) == 3
    for body in agent_inputs:
        for key in ("bundle_sha256", "prompt_sha256"):
            digest = body[key].split(":", 1)[1]
            saved = (inputs_dir / digest).read_bytes()
            assert "sha256:" + hashlib.sha256(saved).hexdigest() == body[key]


def test_malformed_turn_sends_nothing(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    services.start()
    adapter = StandInAdapter(script=lambda tid, b: "definitely not json")
    loop = TurnLoop(
        harness_url=services.url, baldur_url=services.url, log_url=services.url,
        adapter=adapter, repo_root=tmp_path, transport=services.transport, instructions="x", frozen_reference="y",
    )
    try:
        results = loop.run(max_turns=5)
    finally:
        services.stop()
    assert results[0]["outcome"] == "malformed"
    assert services.requests == [] and services.escalations == [] and services.reports == []
    malformed = [r for r in services.log_records if r["type"] == "MALFORMED"]
    assert len(malformed) == 1 and malformed[0]["body"]["reason"] == "NOT_ONE_JSON_OBJECT"


def test_model_cannot_forge_loop_fields_end_to_end(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    services.start()
    forged = json.dumps({"kind": "none", "request_id": "forged", "origin": "ODIN", "nonce": "0" * 32})
    adapter = StandInAdapter(script=lambda tid, b: forged)
    loop = TurnLoop(
        harness_url=services.url, baldur_url=services.url, log_url=services.url,
        adapter=adapter, repo_root=tmp_path, transport=services.transport, instructions="x", frozen_reference="y",
    )
    try:
        results = loop.run(max_turns=5)
    finally:
        services.stop()
    assert results[0]["outcome"] == "malformed"
    assert services.requests == []


def test_prompt_stable_prefix_first(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    services.start()
    adapter = StandInAdapter(script=lambda tid, b: '{"kind":"none"}')
    loop = TurnLoop(
        harness_url=services.url, baldur_url=services.url, log_url=services.url,
        adapter=adapter, repo_root=tmp_path, transport=services.transport,
        instructions="INSTRUCTIONS-MARKER",
    )
    try:
        loop.run(max_turns=5)
    finally:
        services.stop()
    body = [r["body"] for r in services.log_records if r["type"] == "AGENT_INPUT"][0]
    prompt = (tmp_path / "runs" / RUN_ID / "inputs" / body["prompt_sha256"].split(":")[1]).read_text("utf-8")
    # U43 order: instructions, then plan/procedures, then the changing turn.
    assert prompt.index("INSTRUCTIONS-MARKER") < prompt.index("TYR0-DEV-PASS1-v1")
    assert prompt.index("TYR0-DEV-PASS1-v1") < prompt.index("EPS_BATT_V")
