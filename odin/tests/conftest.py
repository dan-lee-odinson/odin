"""Shared fixtures for M1 tests. No network, no secrets, no fault content."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PLAN_ID = "TYR0-DEV-PASS1-v1"
RUN_ID = "dev-run-m1"


def sha256_str(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def nominal_points(met_s: int = 100, soc: float = 78.0) -> dict:
    return {
        "EPS_BATT_V": {"value": 7.9, "units": "V", "limit_state": "GREEN"},
        "EPS_BATT_I": {"value": 0.4, "units": "A", "limit_state": "GREEN"},
        "EPS_BATT_SOC": {"value": soc, "units": "%", "limit_state": "GREEN"},
        "EPS_SA1_I": {"value": 0.42, "units": "A", "limit_state": "NONE"},
        "EPS_SA2_I": {"value": 0.4, "units": "A", "limit_state": "NONE"},
        "EPS_BUS_V": {"value": 5.01, "units": "V", "limit_state": "GREEN"},
        "EPS_LOAD_I": {"value": 0.75, "units": "A", "limit_state": "GREEN"},
        "EPS_MODE": {"value": "NOMINAL", "units": "n/a", "limit_state": "GREEN"},
        "ADM_ECLIPSE": {"value": "SUNLIT", "units": "n/a", "limit_state": "NONE"},
        "PLD_STATE": {"value": "OFF", "units": "n/a", "limit_state": "NONE"},
        "PLD_RATE": {"value": 1.0, "units": "Hz", "limit_state": "NONE"},
        "CDH_MET": {"value": met_s, "units": "s", "limit_state": "NONE"},
        "CDH_FRAME_CNT": {"value": met_s, "units": "n/a", "limit_state": "NONE"},
        "CDH_CMD_ACC_CNT": {"value": 0, "units": "n/a", "limit_state": "NONE"},
        "CDH_CMD_REJ_CNT": {"value": 0, "units": "n/a", "limit_state": "NONE"},
        "CDH_REJ_REASON": {"value": "NONE", "units": "n/a", "limit_state": "NONE"},
    }


def dev_plan() -> dict:
    return {
        "plan_id": PLAN_ID,
        "plan_version": 1,
        "scenario_id": "DEV-S01",
        "pass_index": 1,
        "valid_from_met_s": 0,
        "valid_until_met_s": 5400,
        "contact_window": {"aos_met_s": 0, "los_met_s": 5400},
        "objectives": ["Confirm spacecraft condition.", "Exercise the turn loop."],
        "prohibited": [],
        "envelope": [{"point": "EPS_BATT_SOC", "op": "ge", "value": 35}],
        "leases": [
            {
                "lease_id": "L1",
                "command": "CMD_MODE_SET",
                "arguments": {"target": ["NOMINAL", "LOW_POWER"]},
                "conditions": [{"point": "EPS_BATT_SOC", "op": "ge", "value": 25}],
                "max_uses": 2,
            }
        ],
        "procedures_in_force": [
            {
                "id": "PROC-001",
                "version": "1",
                "sha256": "sha256:4e086337f7dfd018dde67cf48b14feb8390b59d741d0c2c4c90bd96dfa0cae1e",
            }
        ],
        "references": [
            {
                "name": "COSMOS operations reference (frozen)",
                "sha256": "sha256:9159bf99fe60896830132fc452d307736239b0b9f3713fee475f571d7459bd05",
            }
        ],
    }


def make_bundle(turn_id: int, turn_kind: str = "ACT", report_kind=None, met_s=None) -> dict:
    met = 100 + turn_id if met_s is None else met_s
    if turn_kind == "REPORT" and report_kind is None:
        report_kind = "PASS_START"
    bundle = {
        "run_id": RUN_ID,
        "turn_id": turn_id,
        "met_s": met,
        "utc": "2026-10-28T14:10:04.210Z",
        "triggers": [{"type": "PERIODIC", "met_s": met, "detail": {}}],
        "turn_kind": turn_kind,
        "report_kind": report_kind if turn_kind == "REPORT" else None,
        "contact_state": "IN_CONTACT",
        "seat": "GROUND",
        "rung": "AI_AUTONOMOUS",
        "rung_reason": None,
        "observation": {
            "source": "COSMOS",
            "frame_met_s": met,
            "received_utc": "2026-10-28T14:10:04.150Z",
            "age_s": 0.1,
            "staleness_state": "GREEN",
            "points": nominal_points(met),
        },
        "history": {"columns": ["met_s", "EPS_BATT_SOC"], "rows": [[met, 78.0]]},
        "feeds": None,
        "gateway_feedback": [],
        "own_requests": [],
        "uses_left": {"L1": 2},
        "plan": dev_plan(),
        "next_plan_summary": None,
        "procedures": [
            {
                "id": "PROC-001",
                "version": "1",
                "sha256": "sha256:4e086337f7dfd018dde67cf48b14feb8390b59d741d0c2c4c90bd96dfa0cae1e",
                "text": "Watch EPS_BATT_SOC, EPS_MODE and PLD_STATE. Keep payload off unless needed.",
                "attachments": [],
            }
        ],
        "check_in_text": "How is the spacecraft?" if report_kind == "CHECK_IN" else None,
    }
    return bundle


def bundle_bytes(bundle: dict) -> bytes:
    return json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode("utf-8")


@pytest.fixture()
def keypair(tmp_path, monkeypatch):
    """Throwaway keypair entirely inside the test temp folder. The repo's
    keys/odin.pub (ODIN's real public key) is never touched by tests."""
    from odin.loop import signing

    priv_path = tmp_path / "odin_test_key"
    pub_path = tmp_path / "odin.pub"
    signing.generate_keypair_files(priv_path, pub_path)
    monkeypatch.setenv("ODIN_KEY_PATH", str(priv_path))
    return {"priv": priv_path, "pub": pub_path}


@pytest.fixture()
def repo_root():
    return REPO_ROOT
