"""M12: a request stamped when it is signed.

The request's utc is wall-clock taken just before signing, never the
bundle's utc, so a slow turn (two model calls, 40 s on a fake clock)
still sends a request within a second of its sending. The signature
covers that utc. Plus M11's addition: an escalation's proposed that
holds only nulls becomes null.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from odin.adapters.spark import SparkAdapter, drop_nulls
from odin.loop import signing
from odin.loop.loop import TurnLoop, utc_now
from odin.loop.validate import dictionary_for_plan, validate_act_text
from conftest import REPO_ROOT, bundle_bytes, make_bundle

INST_REF = "sha256:1a113f774b043bc3a0939a8285e61475a35d3d268792b71f29fa8c7bae0ab53c"
UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}(Z|\+00:00)$")
COLLECT = ('{"kind":"command","command":"COLLECT","parameters":'
           '{"type":"NORMAL","duration":1.0,"opcode":3,"temp":20.0},"rationale":"collect"}')


def _parse(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def test_utc_now_is_contract_form_and_current():
    stamp = utc_now()
    assert UTC_RE.match(stamp)
    assert abs((_parse(stamp) - datetime.now(timezone.utc)).total_seconds()) < 5


def _run_slow_turn(tmp_path, keypair):
    from odin.devtools.fake_harness import FakeServices

    start = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
    clock = FakeClock(start)
    bundle = make_bundle(1, turn_kind="ACT")
    bundle["utc"] = "2026-10-29T12:00:00.000Z"
    bundle["plan"]["references"].append({"name": "INST dictionary", "sha256": INST_REF})

    class SlowAdapter:
        name = "stand_in"

        def complete(self, *, prompt, bundle, **kw):
            clock.advance(40)  # two model calls around a history call
            return {"raw": COLLECT, "channel": "CONTENT", "status": "OK"}

    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    sent_at = {}

    def transport(method, url, data=None):
        if method == "POST" and url.endswith("/request"):
            sent_at["at"] = clock.now
        return services.transport(method, url, data)

    loop = TurnLoop(harness_url=services.url, baldur_url=services.url,
                    log_url=services.url, adapter=SlowAdapter(),
                    repo_root=tmp_path, transport=transport,
                    private_key_path=str(keypair["priv"]), instructions="x",
                    clock=clock)
    results = loop.run(max_turns=5)
    return results, services, bundle, sent_at


def test_request_stamped_at_signing_not_bundle_utc(tmp_path, keypair):
    results, services, bundle, sent_at = _run_slow_turn(tmp_path, keypair)
    assert results[0]["outcome"] in ("request", "refused")
    assert len(services.requests) == 1
    request = services.requests[0]
    assert request["utc"] != bundle["utc"]
    assert UTC_RE.match(request["utc"])
    # Within a second of its sending, despite the 40 s turn.
    assert abs((_parse(request["utc"]) - sent_at["at"]).total_seconds()) <= 1
    assert _parse(request["utc"]) == _parse(bundle["utc"]) + timedelta(seconds=40)


def test_nothing_else_in_the_request_changes(tmp_path, keypair):
    results, services, bundle, _sent_at = _run_slow_turn(tmp_path, keypair)
    request = services.requests[0]
    assert request["met_s"] == bundle["met_s"]
    assert request["run_id"] == bundle["run_id"]
    assert request["turn_id"] == bundle["turn_id"]
    assert request["plan_id"] == bundle["plan"]["plan_id"]
    assert request["command"] == "COLLECT"
    assert request["parameters"] == {"type": "NORMAL", "duration": 1.0, "opcode": 3, "temp": 20.0}
    assert request["origin"] == "ODIN" and request["rationale"] == "collect"
    assert request["agent_input_hash"].startswith("sha256:")


def test_signature_covers_the_new_utc(tmp_path, keypair):
    _results, services, _bundle, _sent_at = _run_slow_turn(tmp_path, keypair)
    request = services.requests[0]
    assert signing.verify_request(request, str(keypair["pub"])) is True
    tampered = dict(request)
    tampered["utc"] = "2026-10-29T12:00:41.000Z" if request["utc"] != "2026-10-29T12:00:41.000Z" \
        else "2026-10-29T12:00:42.000Z"
    assert signing.verify_request(tampered, str(keypair["pub"])) is False


# -- proposed that holds only nulls becomes null --------------------------------

def _inst_commands():
    plan = {"plan_id": "P", "references": [{"name": "INST", "sha256": INST_REF}]}
    return dictionary_for_plan(plan)[1]


@pytest.mark.parametrize("proposed", [
    {"command": None, "parameters": {"type": None, "duration": None, "opcode": None, "temp": None}},
    {"command": None, "parameters": None},
    {},
])
def test_proposed_holding_only_nulls_becomes_null(proposed):
    answer = {"kind": "escalation", "command": None,
              "parameters": {"type": None, "duration": None, "opcode": None, "temp": None},
              "escalation_kind": "MALFUNCTION", "refs": [], "proposed": proposed,
              "urgency": "ROUTINE", "rationale": None}
    dropped = drop_nulls(answer)
    assert "proposed" in dropped and dropped["proposed"] is None
    ok, _obj, reason, detail = validate_act_text(json.dumps(dropped), commands=_inst_commands())
    assert ok, (reason, detail)


def test_proposed_holding_only_nulls_becomes_null_through_spark():
    raw = ('{"kind":"escalation","command":null,'
           '"parameters":{"type":null,"duration":null,"opcode":null,"temp":null},'
           '"escalation_kind":"MALFUNCTION","refs":[],'
           '"proposed":{"command":null,"parameters":{"type":null,"duration":null,"opcode":null,"temp":null}},'
           '"urgency":"ROUTINE","rationale":null}')
    bundle = make_bundle(1, turn_kind="ACT")
    bundle["plan"]["references"].append({"name": "INST dictionary", "sha256": INST_REF})

    def fake_post(url, headers, payload, timeout):
        return 200, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}], "usage": {}}

    adapter = SparkAdapter(reasoning_effort="low", max_output_tokens=10,
                           timeout_s=5, api_key="test-only", http_post=fake_post)
    result = adapter.complete(prompt=b"p", bundle=bundle)
    # M14: the adapter returns the text exactly; the loop's parse judges it.
    assert result["raw"] == raw
    from odin.loop.loop import judge_act_text
    ok, obj, reason, detail = judge_act_text(result["raw"], commands=_inst_commands())
    assert ok, (reason, detail)
    assert "proposed" in obj and obj["proposed"] is None


def test_real_proposed_is_not_nulled():
    answer = {"kind": "escalation", "command": None, "parameters": None,
              "escalation_kind": "MALFUNCTION", "refs": [],
              "proposed": {"command": "COLLECT",
                           "parameters": {"type": "NORMAL", "duration": 1.0, "opcode": 3, "temp": 20.0}},
              "urgency": "ROUTINE", "rationale": None}
    dropped = drop_nulls(answer)
    assert dropped["proposed"]["command"] == "COLLECT"


def test_frozen_files_six_schemas_and_models_unchanged():
    record = json.loads((REPO_ROOT / "odin" / "instructions" / "system_prompt.sha256.json").read_text(encoding="utf-8"))
    files = {
        record["sha256"]: REPO_ROOT / "odin" / "instructions" / "system_prompt.md",
        record["template_sha256"]: REPO_ROOT / "odin" / "instructions" / "template.md",
        record["prompt_template_sha256"]: REPO_ROOT / "odin" / "loop" / "prompt.py",
    }
    for expected, path in files.items():
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == expected, path
    frozen = json.loads((REPO_ROOT / "config" / "frozen.json").read_text(encoding="utf-8"))
    for rel, expected in frozen["schemas"].items():
        assert "sha256:" + hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == expected, rel
    # M17: each model's block checked against its frozen.json entry,
    # so a model can be added with its entry without breaking this.
    from freeze_guard import assert_model_blocks_match_frozen
    assert_model_blocks_match_frozen(REPO_ROOT / "config" / "models.yaml",
                                     REPO_ROOT / "config" / "frozen.json")
