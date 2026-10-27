"""Spend meter (CONTRACT §11.2–§11.3; AGENTS §4.3; rulings U21).

Prices are read from config/prices.yaml at run time; no second copy is
kept. Before each call the meter reserves the worst-case cost (known
input tokens at the full input price plus the call's maximum output at
the output price). If spent plus reserved would pass a stop, the call is
refused and SPEND_STOP is submitted. After the call, actual cost replaces
the reservation and SPEND (the four running totals) is submitted. Both go
through POST /log/agent via the caller's `submit` callable.

The ledger is an append-only JSONL file: a restart replays it, so the
totals survive. It is never overwritten.
"""
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRICES = REPO_ROOT / "config" / "prices.yaml"

# The stops (§11.3) and which credit each configuration draws on (§11.2,
# spend_stop.schema.json). Glimmer's Modal GPU fallback is the modal case.
STOPS = {"META": 125.0, "BASETEN": 90.0, "MODAL": 12.0}
CONFIG_STOP = {"spark": "META", "spark_open": "BASETEN", "glimmer_local": "MODAL"}
CONFIG_BUCKET = {
    "spark": "META_CREDIT",
    "spark_open": "BASETEN_CREDIT",
    "glimmer_local": "MODAL_CREDIT",
    "stand_in": None,
}
BUCKETS = ["META_CREDIT", "BASETEN_CREDIT", "MODAL_CREDIT", "OUT_OF_POCKET"]
SPEND_KEYS = {
    "META_CREDIT": "meta_credit_usd",
    "BASETEN_CREDIT": "baseten_credit_usd",
    "MODAL_CREDIT": "modal_credit_usd",
    "OUT_OF_POCKET": "out_of_pocket_usd",
}


class Reservation:
    def __init__(self, meter, *, config, bucket, reserved_usd, turn_id, call_index):
        self._meter = meter
        self.config = config
        self.bucket = bucket
        self.reserved_usd = reserved_usd
        self.turn_id = turn_id
        self.call_index = call_index
        self.actual_usd = None

    def settle(self, *, input_tokens=None, cached_input_tokens=0, output_tokens=None,
               actual_usd=None) -> float:
        """Replace the reservation with the actual cost; submit SPEND (U21)."""
        if self.actual_usd is not None:
            raise RuntimeError("reservation already settled")
        if actual_usd is None:
            actual_usd = self._meter.token_cost(
                self.config, input_tokens or 0, cached_input_tokens or 0, output_tokens or 0
            )
        self.actual_usd = actual_usd
        self._meter._settle(self, actual_usd)
        return actual_usd


class SpendMeter:
    def __init__(self, ledger_path, prices_path=None, submit=None):
        self.ledger_path = Path(ledger_path)
        self._prices = yaml.safe_load(
            Path(prices_path or DEFAULT_PRICES).read_text(encoding="utf-8")
        )
        self._submit = submit
        self._spent = {bucket: 0.0 for bucket in BUCKETS}
        self._outstanding = {bucket: 0.0 for bucket in BUCKETS}
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if self.ledger_path.exists():
            for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._replay(json.loads(line))

    # -- pricing ---------------------------------------------------------
    def token_cost(self, config, input_tokens, cached_input_tokens, output_tokens) -> float:
        prices = self._prices.get(config)
        if not prices:
            return 0.0  # local/stand-in calls carry no token price
        uncached = max(0, input_tokens - cached_input_tokens)
        return (
            uncached * prices["input_per_mtok"]
            + cached_input_tokens * prices["cached_input_per_mtok"]
            + output_tokens * prices["output_per_mtok"]
        ) / 1_000_000

    def worst_case(self, config, input_tokens, max_output_tokens) -> float:
        prices = self._prices.get(config)
        if not prices:
            raise ValueError(f"no token price for {config!r}; pass reserved_usd explicitly")
        return (
            input_tokens * prices["input_per_mtok"]
            + max_output_tokens * prices["output_per_mtok"]
        ) / 1_000_000

    # -- ledger ------------------------------------------------------------
    def _append(self, event: dict) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _replay(self, event: dict) -> None:
        bucket = event.get("bucket")
        if bucket not in self._spent:
            return
        if event["kind"] == "RESERVE":
            self._outstanding[bucket] += event["reserved_usd"]
        elif event["kind"] == "SETTLE":
            self._outstanding[bucket] -= event["reserved_usd"]
            self._spent[bucket] += event["actual_usd"]

    def totals(self) -> dict:
        return dict(self._spent)

    # -- reserve / settle ----------------------------------------------------
    def reserve(self, *, config, input_tokens, max_output_tokens, turn_id, call_index,
                reserved_usd=None, pays_from=None):
        bucket = pays_from or CONFIG_BUCKET.get(config)
        if bucket is None:  # stand_in: no cost, no stop
            reservation = Reservation(self, config=config, bucket="OUT_OF_POCKET",
                                      reserved_usd=0.0, turn_id=turn_id, call_index=call_index)
            reservation.bucket = None
            return reservation
        if reserved_usd is None:
            reserved_usd = self.worst_case(config, input_tokens, max_output_tokens)
        if pays_from is None and config in CONFIG_STOP:
            stop = CONFIG_STOP[config]
            limit = STOPS[stop]
            if self._spent[bucket] + self._outstanding[bucket] + reserved_usd > limit:
                self._append({
                    "kind": "SPEND_STOP", "config": config, "bucket": bucket,
                    "spent_usd": self._spent[bucket], "reserved_usd": reserved_usd,
                    "limit_usd": limit, "turn_id": turn_id, "call_index": call_index,
                })
                if self._submit is not None:
                    self._submit("SPEND_STOP", {
                        "turn_id": turn_id, "call_index": call_index, "config": config,
                        "stop": stop, "spent_usd": self._spent[bucket],
                        "reserved_usd": reserved_usd, "limit_usd": limit,
                    })
                return None
        self._append({
            "kind": "RESERVE", "config": config, "bucket": bucket,
            "reserved_usd": reserved_usd, "turn_id": turn_id, "call_index": call_index,
        })
        self._outstanding[bucket] += reserved_usd
        return Reservation(self, config=config, bucket=bucket, reserved_usd=reserved_usd,
                           turn_id=turn_id, call_index=call_index)

    def _settle(self, reservation: Reservation, actual_usd: float) -> None:
        bucket = reservation.bucket
        if bucket is not None:
            self._append({
                "kind": "SETTLE", "config": reservation.config, "bucket": bucket,
                "reserved_usd": reservation.reserved_usd, "actual_usd": actual_usd,
                "turn_id": reservation.turn_id, "call_index": reservation.call_index,
            })
            self._outstanding[bucket] -= reservation.reserved_usd
            self._spent[bucket] += actual_usd
        if self._submit is not None:
            body = {"turn_id": reservation.turn_id, "call_index": reservation.call_index}
            for bucket_name, key in SPEND_KEYS.items():
                body[key] = self._spent[bucket_name]
            self._submit("SPEND", body)
