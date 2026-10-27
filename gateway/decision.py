"""BALDUR-0's decision on one command request: the checks of CONTRACT.md §9.1, in order, stopping at
the first that fails (§16.4 U14). The same function decides on receipt and again immediately before
dispatch (§9.3), on the context of the moment.

The decision record lists all eight checks: PASS up to a failure, FAIL at it, NOT_RUN after it, and
RECORD always PASS, because the caller logs every decision. It carries the plan, arming act, class and
lease the decision rests on, its basis, which the recheck compares.
"""

import base64
import binascii
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature

from gateway.acts import parse_utc
from gateway.rules import COMMAND_CLASS, PROTECTIVE, RUNG_ALLOWS, arguments_covered, failing, is_fresh, staleness
from log.canonical import canonical_json

CHECKS = ("PLAN", "ARMING", "ORIGIN", "CEILING", "PROHIBITED", "CLASS", "LEASE", "RECORD")
BASIS = (("plan_id", "PLAN"), ("arming_act_id", "ARMING"), ("class", "CLASS"), ("lease_id", "LEASE"))
CLOCK_SKEW_S = 30


@dataclass
class Context:
    """Everything a decision depends on, at one moment."""
    run_id: object            # the run BALDUR-0 is running, or None before one starts
    met_s: float              # simulation time now
    utc: str                  # BALDUR-0's wall clock now
    plan: object              # the Plan in force, or None
    arming: object            # the Act that arms the run, or None
    revoked: bool
    frame: object             # the newest frame, {frame_met_s, points}, or None
    odin_key: object          # ODIN's Ed25519 public key
    nonce_reused: bool        # an earlier request carried this request's nonce
    lease_uses: dict = field(default_factory=dict)   # (plan_id, lease_id) -> uses dispatched


def signature_verifies(request, odin_key):
    """§7.3, §16.3 U13: the 64-byte Ed25519 signature, in standard base64, over the canonical JSON of
    every other field."""
    try:
        signature = base64.b64decode(request["signature"], validate=True)
        odin_key.verify(signature, canonical_json({k: v for k, v in request.items() if k != "signature"}))
        return True
    except (InvalidSignature, KeyError, TypeError, ValueError, binascii.Error):
        return False


def rung(ctx):
    """§6.2, §16.1 U2: (rung, rung_reason). AI_AUTONOMOUS while a valid act arms the run, a plan is in
    force and authority is not revoked; otherwise HUMAN_ONLY, with the reason, taken in the order of
    the checks that find it."""
    if ctx.plan is None:
        return "HUMAN_ONLY", "NO_PLAN"
    if ctx.arming is None or ctx.arming.expired_at(ctx.utc):
        return "HUMAN_ONLY", "NOT_ARMED"
    if ctx.revoked:
        return "HUMAN_ONLY", "REVOKED"
    return ctx.arming.rung, None


def _plan(request, ctx, found):
    if ctx.plan is None:
        return "NO_PLAN_IN_FORCE", f"no plan of the run's chain is in force at met_s {ctx.met_s:g}"
    found["plan_id"] = ctx.plan.plan_id
    # §9.3 and the Director's ruling on U29 (27 October 2026): a request belongs to the plan it was
    # decided under and is never reassessed under another, so one naming another plan, or none, is
    # refused. At the dispatch recheck this voids a request a plan boundary has passed.
    if request["plan_id"] != ctx.plan.plan_id:
        named = f"plan {request['plan_id']}" if request["plan_id"] is not None else "no plan"
        return "PLAN_MISMATCH", f"the request names {named}; {ctx.plan.plan_id} is in force"


def _arming(request, ctx, found):
    if ctx.arming is None:
        return "NOT_ARMED", "no act arms the run"
    if ctx.arming.expired_at(ctx.utc):
        return "ACT_EXPIRED", f"{ctx.arming.act_id} expired at {ctx.arming.expires_utc}"
    if ctx.run_id not in ctx.arming.runs:
        return "ACT_NOT_FOR_RUN", f"{ctx.arming.act_id} does not cover run {ctx.run_id}"


def _origin(request, ctx, found):
    if not signature_verifies(request, ctx.odin_key):
        return "BAD_SIGNATURE", "the signature does not verify with keys/odin.pub"
    if ctx.nonce_reused:
        return "NONCE_REUSED", f"nonce {request['nonce']} was used by an earlier request"
    skew = (parse_utc(request["utc"]) - parse_utc(ctx.utc)).total_seconds()
    if abs(skew) > CLOCK_SKEW_S:
        return "CLOCK_SKEW", f"the request's utc is {skew:+.3f} s from BALDUR-0's clock, past {CLOCK_SKEW_S} s"
    # The Director's ruling on U28 (27 October 2026): a request for any run but the one BALDUR-0 is
    # running is refused here, even when the same batch act covers that run too.
    if request["run_id"] != ctx.run_id:
        return "WRONG_RUN", f"the request is for run {request['run_id']}; this run is {ctx.run_id}"


def _ceiling(request, ctx, found):
    if ctx.revoked:
        return "REVOKED", "ODIN's authority is revoked"


def _prohibited(request, ctx, found):
    if request["command"] in ctx.plan.document["prohibited"]:
        return "PROHIBITED_BY_PLAN", f"{ctx.plan.plan_id} prohibits {request['command']}"


def _class(request, ctx, found):
    base = COMMAND_CLASS[request["command"]]
    found["base_class"] = base
    if request["command"] not in PROTECTIVE and not is_fresh(ctx.frame, ctx.met_s):
        # §9.6 and the Director's ruling on U25 (27 October 2026): on stale or missing telemetry every
        # command but the protective ones is refused here, the mode command included, whatever its
        # lease's conditions, and the record keeps the dictionary's class.
        found["class"] = base
        return "NO_FRESH_TELEMETRY", staleness(ctx.frame, ctx.met_s)
    detail = None
    if base in ("C1", "C2"):
        broken = failing(ctx.plan.document["envelope"], ctx.frame)
        if broken:
            detail = "raised to C4: " + "; ".join(broken)
        found["class"] = "C4" if broken else base
    else:
        found["class"] = base   # C3 is never raised (§5.5); C4 needs no raise
    current_rung, _ = rung(ctx)
    if found["class"] not in RUNG_ALLOWS[current_rung]:
        return "RUNG_REFUSES_CLASS", f"{current_rung} does not allow {found['class']}"
    return None, detail


def _lease(request, ctx, found):
    if found["class"] != "C4":
        return None
    plan = ctx.plan
    named = [lease for lease in plan.document["leases"] if lease["command"] == request["command"]]
    if not named:
        return "NO_LEASE", f"no lease in {plan.plan_id} names {request['command']}"
    covering = [lease for lease in named if arguments_covered(lease, request["parameters"])]
    if not covering:
        return "ARGUMENTS_NOT_COVERED", (f"no lease in {plan.plan_id} for {request['command']} covers "
                                         f"{canonical_json(request['parameters']).decode('utf-8')}")
    # Plan verification refuses two leases with overlapping arguments for one command (the Director's
    # ruling on U27, 27 October 2026), so a single lease covers the request.
    [lease] = covering
    lease_id = found["lease_id"] = lease["lease_id"]
    # CLASS has refused every C4 command on stale telemetry (U25), so the conditions are judged on a
    # fresh frame, and LEASE's NO_FRESH_TELEMETRY, which §16.4 lists, is never given.
    broken = failing(lease["conditions"], ctx.frame)
    if broken:
        return "CONDITION_FAILED", f"{lease_id}: " + "; ".join(broken)
    uses = ctx.lease_uses.get((plan.plan_id, lease_id), 0)
    if lease["max_uses"] is not None and uses >= lease["max_uses"]:
        return "NO_USES_LEFT", f"{lease_id}: {uses} of {lease['max_uses']} uses dispatched"


STEPS = (_plan, _arming, _origin, _ceiling, _prohibited, _class, _lease)


def decide(request, ctx):
    """(decision record, basis) for a well-formed COMMAND_REQUEST."""
    # The Director's ruling on U26 (27 October 2026): arming_act_id names the act that arms the run
    # whenever there is one, even when the decision stops at PLAN, and the expired act on ACT_EXPIRED;
    # null only when no act arms it.
    found = {"plan_id": None, "arming_act_id": ctx.arming.act_id if ctx.arming else None,
             "base_class": None, "class": None, "lease_id": None}
    checks, refused = [], False
    for name, step in zip(CHECKS, STEPS):
        if refused:
            checks.append({"check": name, "result": "NOT_RUN", "reason": None, "detail": None})
            continue
        outcome = step(request, ctx, found)
        reason, detail = outcome if isinstance(outcome, tuple) else (outcome, None)
        refused = reason is not None
        checks.append({"check": name, "result": "FAIL" if refused else "PASS", "reason": reason, "detail": detail})
    checks.append({"check": "RECORD", "result": "PASS", "reason": None, "detail": None})
    record = {"request_id": request["request_id"], "decision": "REFUSE" if refused else "ALLOW",
              "checks": checks, "rung": rung(ctx)[0], "met_s": ctx.met_s, "utc": ctx.utc, **found}
    return record, {key: found[key] for key, _ in BASIS}


def failed_check(record):
    return next(check for check in record["checks"] if check["result"] == "FAIL")
