"""M2: spend meter (CONTRACT §11.2–§11.3; AGENTS §4.3; U21 SPEND/SPEND_STOP)."""
import json
from pathlib import Path

import pytest

from odin.devtools.fake_harness import FakeServices
from odin.spend.meter import SpendMeter

REPO_ROOT = Path(__file__).resolve().parents[2]
PRICES = REPO_ROOT / "config" / "prices.yaml"


def make_meter(tmp_path, submit=None):
    return SpendMeter(ledger_path=tmp_path / "spend.jsonl", prices_path=PRICES, submit=submit)


def log_submitter(services):
    def submit(record_type, body):
        status, raw = services.transport(
            "POST", "/log/agent", json.dumps({"type": record_type, "body": body}).encode()
        )
        assert status == 200, (record_type, raw)
    return submit


def spend_to(meter, config, actual_usd, turn_id=1):
    """Drive spent to an exact amount via a settled zero-token call."""
    reservation = meter.reserve(
        config=config, input_tokens=0, max_output_tokens=1,
        turn_id=turn_id, call_index=1, reserved_usd=actual_usd,
    )
    assert reservation is not None
    reservation.settle(actual_usd=actual_usd)
    return reservation


# -- stops (§11.3) ---------------------------------------------------------

def test_meta_stop_refuses_at_125(tmp_path):
    meter = make_meter(tmp_path)
    spend_to(meter, "spark", 124.0)
    refused = meter.reserve(config="spark", input_tokens=0, max_output_tokens=1,
                            turn_id=2, call_index=1, reserved_usd=2.0)
    assert refused is None  # 124 + 2 would pass $125


def test_baseten_stop_refuses_at_90(tmp_path):
    meter = make_meter(tmp_path)
    spend_to(meter, "spark_open", 89.0)
    refused = meter.reserve(config="spark_open", input_tokens=0, max_output_tokens=1,
                            turn_id=2, call_index=1, reserved_usd=2.0)
    assert refused is None  # 89 + 2 would pass $90


def test_modal_stop_refuses_at_12(tmp_path):
    meter = make_meter(tmp_path)
    spend_to(meter, "glimmer_local", 11.0)
    refused = meter.reserve(config="glimmer_local", input_tokens=0, max_output_tokens=1,
                            turn_id=2, call_index=1, reserved_usd=2.0)
    assert refused is None  # 11 + 2 would pass $12.00


def test_call_reaching_exactly_the_stop_is_allowed(tmp_path):
    # "Would pass a stop" (§11.3) means exceed it; landing exactly on it is allowed.
    meter = make_meter(tmp_path)
    spend_to(meter, "spark", 120.0)
    allowed = meter.reserve(config="spark", input_tokens=0, max_output_tokens=1,
                            turn_id=2, call_index=1, reserved_usd=5.0)
    assert allowed is not None  # 120 + 5 == 125, not past it
    refused = meter.reserve(config="spark", input_tokens=0, max_output_tokens=1,
                            turn_id=3, call_index=1, reserved_usd=0.01)
    assert refused is None  # one cent more would pass it


# -- reservation replaced by actual (§11.3) ---------------------------------

def test_actual_cost_replaces_reservation(tmp_path):
    meter = make_meter(tmp_path)
    # Worst case: 1M input ($1.25) + 1M max output ($4.25) = $5.50 reserved.
    reservation = meter.reserve(config="spark", input_tokens=1_000_000,
                                max_output_tokens=1_000_000, turn_id=1, call_index=1)
    assert reservation is not None
    assert reservation.reserved_usd == pytest.approx(5.50)
    actual = reservation.settle(input_tokens=1000, cached_input_tokens=0, output_tokens=100)
    assert actual == pytest.approx((1000 * 1.25 + 100 * 4.25) / 1_000_000)
    assert meter.totals()["META_CREDIT"] == pytest.approx(actual)
    # The freed reservation no longer counts: a $124 call now fits under $125.
    follow_up = meter.reserve(config="spark", input_tokens=0, max_output_tokens=1,
                              turn_id=2, call_index=1, reserved_usd=124.0)
    assert follow_up is not None


def test_cached_input_priced_separately(tmp_path):
    meter = make_meter(tmp_path)
    reservation = meter.reserve(config="spark", input_tokens=1_000_000,
                                max_output_tokens=0, turn_id=1, call_index=1)
    actual = reservation.settle(input_tokens=1_000_000, cached_input_tokens=500_000,
                                output_tokens=0)
    expected = (500_000 * 1.25 + 500_000 * 0.15) / 1_000_000
    assert actual == pytest.approx(expected)


# -- four amounts kept apart (§11.2) -----------------------------------------

def test_four_amounts_kept_apart(tmp_path):
    meter = make_meter(tmp_path)
    spend_to(meter, "spark", 1.0, turn_id=1)
    spend_to(meter, "spark_open", 2.0, turn_id=2)
    spend_to(meter, "glimmer_local", 3.0, turn_id=3)
    reservation = meter.reserve(config="spark", input_tokens=0, max_output_tokens=1,
                                turn_id=4, call_index=1, reserved_usd=4.0,
                                pays_from="OUT_OF_POCKET")
    reservation.settle(actual_usd=4.0)
    assert meter.totals() == {
        "META_CREDIT": pytest.approx(1.0), "BASETEN_CREDIT": pytest.approx(2.0),
        "MODAL_CREDIT": pytest.approx(3.0), "OUT_OF_POCKET": pytest.approx(4.0),
    }


# -- ledger survives a restart (§4.3) -----------------------------------------

def test_ledger_survives_restart_and_is_appended(tmp_path):
    ledger = tmp_path / "spend.jsonl"
    meter = SpendMeter(ledger_path=ledger, prices_path=PRICES)
    spend_to(meter, "spark", 1.5)
    first_lines = ledger.read_text(encoding="utf-8").splitlines()
    assert first_lines

    restarted = SpendMeter(ledger_path=ledger, prices_path=PRICES)
    assert restarted.totals()["META_CREDIT"] == pytest.approx(1.5)
    spend_to(restarted, "spark", 0.5, turn_id=2)
    after = ledger.read_text(encoding="utf-8").splitlines()
    assert after[: len(first_lines)] == first_lines  # appended, never overwritten
    assert restarted.totals()["META_CREDIT"] == pytest.approx(2.0)


# -- SPEND / SPEND_STOP through the log (U21) ---------------------------------

def test_spend_records_match_model_call_actuals(tmp_path):
    services = FakeServices()
    meter = make_meter(tmp_path, submit=log_submitter(services))
    model_calls = []

    def run_call(config, turn_id, settle_kwargs, pays_from_bucket):
        reservation = meter.reserve(config=config, input_tokens=1000,
                                    max_output_tokens=1000, turn_id=turn_id, call_index=1)
        assert reservation is not None
        actual = reservation.settle(**settle_kwargs)
        model_calls.append({"pays_from": pays_from_bucket, "actual_cost_usd": actual})

    run_call("spark", 1, {"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 100}, "META_CREDIT")
    run_call("spark_open", 2, {"input_tokens": 2000, "cached_input_tokens": 0, "output_tokens": 200}, "BASETEN_CREDIT")

    spends = [r["body"] for r in services.log_records if r["type"] == "SPEND"]
    assert len(spends) == 2
    totals = meter.totals()
    assert spends[-1]["meta_credit_usd"] == pytest.approx(totals["META_CREDIT"])
    assert spends[-1]["baseten_credit_usd"] == pytest.approx(totals["BASETEN_CREDIT"])
    for bucket, key in (("META_CREDIT", "meta_credit_usd"), ("BASETEN_CREDIT", "baseten_credit_usd")):
        expected = sum(c["actual_cost_usd"] for c in model_calls if c["pays_from"] == bucket)
        assert spends[-1][key] == pytest.approx(expected)


def test_spend_stop_submitted_on_refusal(tmp_path):
    services = FakeServices()
    meter = make_meter(tmp_path, submit=log_submitter(services))
    spend_to(meter, "spark", 124.0)
    refused = meter.reserve(config="spark", input_tokens=0, max_output_tokens=1,
                            turn_id=9, call_index=1, reserved_usd=2.0)
    assert refused is None
    stops = [r["body"] for r in services.log_records if r["type"] == "SPEND_STOP"]
    assert len(stops) == 1
    assert stops[0]["stop"] == "META" and stops[0]["config"] == "spark"
    assert stops[0]["limit_usd"] == pytest.approx(125.0)
    assert stops[0]["turn_id"] == 9
