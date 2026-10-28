"""Fake-harness fixtures for ODIN's own testing: nominal HUGINN frames,
a made-up plan, no fault content (AGENTS §3)."""
import hashlib
import json


def nominal_points(met_s=100):
    values = {
        "EPS_BATT_V": (7.9, "V", "GREEN"), "EPS_BATT_I": (0.4, "A", "GREEN"),
        "EPS_BATT_SOC": (78.0, "%", "GREEN"), "EPS_SA1_I": (0.42, "A", "NONE"),
        "EPS_SA2_I": (0.4, "A", "NONE"), "EPS_BUS_V": (5.01, "V", "GREEN"),
        "EPS_LOAD_I": (0.75, "A", "GREEN"), "EPS_MODE": ("NOMINAL", "n/a", "GREEN"),
        "ADM_ECLIPSE": ("SUNLIT", "n/a", "NONE"), "PLD_STATE": ("OFF", "n/a", "NONE"),
        "PLD_RATE": (1.0, "Hz", "NONE"), "CDH_MET": (met_s, "s", "NONE"),
        "CDH_FRAME_CNT": (met_s, "n/a", "NONE"), "CDH_CMD_ACC_CNT": (0, "n/a", "NONE"),
        "CDH_CMD_REJ_CNT": (0, "n/a", "NONE"), "CDH_REJ_REASON": ("NONE", "n/a", "NONE"),
    }
    return {k: {"value": v, "units": u, "limit_state": s} for k, (v, u, s) in values.items()}


def make_m3_bundle():
    """One fixed, small ACT bundle for the M3 measurement (Part 2)."""
    plan = {
        "plan_id": "TYR0-M3-DEV-v1", "plan_version": 1, "scenario_id": "DEV-M3",
        "pass_index": 1, "valid_from_met_s": 0, "valid_until_met_s": 5400,
        "contact_window": {"aos_met_s": 0, "los_met_s": 5400},
        "objectives": ["Confirm the spacecraft's condition."],
        "prohibited": [], "envelope": [{"point": "EPS_BATT_SOC", "op": "ge", "value": 35}],
        "leases": [{"lease_id": "L1", "command": "CMD_MODE_SET",
                    "arguments": {"target": ["NOMINAL", "LOW_POWER"]},
                    "conditions": [{"point": "EPS_BATT_SOC", "op": "ge", "value": 25}],
                    "max_uses": 2}],
        "procedures_in_force": [{"id": "PROC-001", "version": "1",
                                 "sha256": "sha256:" + hashlib.sha256(b"PROC-001").hexdigest()}],
        "references": [],
    }
    bundle = {
        "run_id": "m3-check", "turn_id": 1, "met_s": 100,
        "utc": "2026-10-27T00:00:00.000Z",
        "triggers": [{"type": "PERIODIC", "met_s": 100, "detail": {}}],
        "turn_kind": "ACT", "report_kind": None, "contact_state": "IN_CONTACT",
        "seat": "GROUND", "rung": "AI_AUTONOMOUS", "rung_reason": None,
        "observation": {"source": "COSMOS", "frame_met_s": 100,
                        "received_utc": "2026-10-27T00:00:00.000Z", "age_s": 0.1,
                        "staleness_state": "GREEN", "points": nominal_points(100)},
        "history": {"columns": ["met_s", "EPS_BATT_SOC"], "rows": [[100, 78.0]]},
        "feeds": None, "gateway_feedback": [], "own_requests": [],
        "uses_left": {"L1": 2}, "plan": plan, "next_plan_summary": None,
        "procedures": [{"id": "PROC-001", "version": "1",
                        "sha256": plan["procedures_in_force"][0]["sha256"],
                        "text": "Watch EPS_BATT_SOC, EPS_MODE and PLD_STATE.",
                        "attachments": []}],
        "check_in_text": None,
    }
    return bundle


def bundle_bytes(bundle):
    return json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode("utf-8")
