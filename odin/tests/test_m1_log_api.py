"""M1/S2: fake log in line with U21 (seven types) and U24 (200/400 replies)."""
import json

from odin.devtools.fake_harness import FakeServices

SHA = "sha256:" + "a" * 64
BODIES = {
    "AGENT_INPUT": {"run_id": "dev-run-m1", "turn_id": 1, "bundle_sha256": SHA, "prompt_sha256": SHA},
    "MODEL_CALL": {
        "run_id": "dev-run-m1", "turn_id": 1, "call_index": 1, "config": "stand_in",
        "provider": None, "model_id": None, "reasoning_effort": None, "max_output_tokens": None,
        "status": "OK", "input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 5,
        "reasoning_tokens": None, "reserved_cost_usd": 0.0, "actual_cost_usd": 0.0,
        "pays_from": None, "latency_s": 0.0, "provider_usage": None,
    },
    "CANDIDATE": {"run_id": "dev-run-m1", "turn_id": 1, "channel": "CONTENT", "raw": '{"kind":"none"}'},
    "ANSWER": {"run_id": "dev-run-m1", "turn_id": 1, "answer": {"kind": "none"}},
    "MALFORMED": {"run_id": "dev-run-m1", "turn_id": 1, "reason": "NOT_ONE_JSON_OBJECT", "detail": "x"},
    "SPEND": {"turn_id": 1, "call_index": 1, "meta_credit_usd": 0.0, "baseten_credit_usd": 0.0,
              "modal_credit_usd": 0.0, "out_of_pocket_usd": 0.0},
    "SPEND_STOP": {"turn_id": 1, "call_index": 1, "config": "spark", "stop": "META",
                   "spent_usd": 120.0, "reserved_usd": 10.0, "limit_usd": 125.0},
}


def _post(services, path, payload):
    status, raw = services.transport("POST", path, json.dumps(payload).encode())
    return status, json.loads(raw)


def test_all_seven_record_types_accepted():
    services = FakeServices()
    for record_type, body in BODIES.items():
        status, reply = _post(services, "/log/agent", {"type": record_type, "body": body})
        assert status == 200, (record_type, reply)
        assert isinstance(reply["record_id"], int) and reply["record_id"] >= 1
    assert [r["type"] for r in services.log_records] == list(BODIES)


def test_bad_record_refused_400_and_not_written():
    services = FakeServices()
    status, reply = _post(services, "/log/agent", {"type": "SPEND", "body": {"turn_id": 1}})
    assert status == 400 and len(reply["problems"]) >= 1
    assert all(isinstance(p, str) and p for p in reply["problems"])
    assert services.log_records == []
    status, reply = _post(services, "/log/agent", {"type": "NOPE", "body": {}})
    assert status == 400 and services.log_records == []


def test_spend_stop_config_stop_mismatch_refused():
    services = FakeServices()
    body = dict(BODIES["SPEND_STOP"], stop="BASETEN")  # spark must stop on META
    status, _ = _post(services, "/log/agent", {"type": "SPEND_STOP", "body": body})
    assert status == 400 and services.log_records == []


def test_report_replies():
    services = FakeServices()
    report = {
        "report_kind": "PASS_START", "run_id": "dev-run-m1", "turn_id": 1, "met_s": 100,
        "utc": "2026-10-28T14:10:04.210Z", "plan_id": "TYR0-DEV-PASS1-v1",
        "timeline": [], "actions": [], "condition": {"summary": "Nominal.", "evidence": []},
        "deferred": [], "open_issues": [],
    }
    status, reply = _post(services, "/report", report)
    assert status == 200 and reply["record_id"] >= 1
    status, reply = _post(services, "/report", {"report_kind": "PASS_START"})
    assert status == 400 and len(reply["problems"]) >= 1
    assert len(services.reports) == 1
