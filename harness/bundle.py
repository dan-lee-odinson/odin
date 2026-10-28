"""The turn bundle the harness serves at GET /turn/next (CONTRACT.md §6.2, §16.1).

Every field is present, null when its subject does not exist (§16 U15). The bundle is served as its
canonical JSON (§4), so its hash is the same whoever computes it: the TRIGGER record's bundle_sha256,
and the agent_input_hash ODIN's request carries.
"""

import json
import re
from pathlib import Path

from log.canonical import canonical_json
from wrapper.frames import POINTS

HISTORY_S = 300
SUMMARY = ("valid_from_met_s", "valid_until_met_s", "prohibited", "envelope", "leases")


def procedure_points(procedures):
    """The points whose mnemonics appear in the procedures' text, matched whole (§16.1 U3)."""
    text = "\n".join(p["text"] for p in procedures or ())
    return [name for name in POINTS if re.search(rf"\b{name}\b", text)]


def next_plan(chain, plan, met_s):
    """The plan after the one in force; before the chain starts, its first plan; None after its last."""
    later = [p for p in chain.plans if p.valid_from_met_s > (plan.valid_from_met_s if plan else met_s)]
    return min(later, key=lambda p: p.valid_from_met_s) if later else None


def read_records(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines()]


def from_the_log(records):
    """(gateway_feedback, own_requests): BALDUR-0's DECISION and DECISION_VOIDED records since ODIN's
    latest request, oldest first, each as {type, record} (§16.1 U6), and every request ODIN has made
    in the run, oldest first."""
    requests = [r for r in records if r["type"] == "REQUEST"]
    since = requests[-1]["record_id"] if requests else None
    feedback = [{"type": r["type"], "record": r["body"]} for r in records
                if since is not None and r["record_id"] > since and r["type"] in ("DECISION", "DECISION_VOIDED")]
    return feedback, [r["body"] for r in requests]


def build_bundle(*, run_id, turn_id, turn, met_s, utc, contact_state, seat, gateway, store, procedures,
                 records, feeds=None, ground_link=None):
    """turn: the harness.triggers.Turn being served. store: the seat's FrameStore. procedures: the
    run's ProcedureLibrary. records: the event log's records so far. ground_link: in the ground seat,
    HUGINN_INT's {state, received_count} as COSMOS reports them; None in the onboard seat."""
    plan = gateway.chain.plan_at(met_s)
    following = next_plan(gateway.chain, plan, met_s)
    rung, rung_reason = gateway.rung()
    in_force = procedures.for_plan(plan)
    feedback, own_requests = from_the_log(records)
    return {
        "run_id": run_id, "turn_id": turn_id, "met_s": met_s, "utc": utc,
        "triggers": turn.triggers, "turn_kind": turn.turn_kind, "report_kind": turn.report_kind,
        "contact_state": contact_state, "seat": seat, "rung": rung, "rung_reason": rung_reason,
        "observation": store.observation(met_s, ground_link),
        "history": store.history(procedure_points(in_force), met_s, HISTORY_S),
        "feeds": feeds,
        "gateway_feedback": feedback,
        "own_requests": own_requests,
        "uses_left": gateway.uses_left(),
        "plan": plan.document if plan else None,
        "next_plan_summary": {name: following.document[name] for name in SUMMARY} if following else None,
        "procedures": in_force,
        "check_in_text": turn.check_in_text,
    }


def bundle_bytes(bundle):
    return canonical_json(bundle)
