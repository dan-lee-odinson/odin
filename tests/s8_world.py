"""Made-up event records and frames for S8's tests, in the shapes the event log and the truth file give them."""

from tests.baldur_world import NOMINAL_POINTS

CHECKS = ("PLAN", "ARMING", "ORIGIN", "CEILING", "PROHIBITED", "CLASS", "LEASE", "RECORD")


def record(type_, met_s, **body):
    return {"type": type_, "met_s": met_s, "body": dict(body, met_s=met_s) if type_ != "PLAN_IN_FORCE" else body}


def decision(request_id, met_s, fail=None):
    """A DECISION record: ALLOW, or REFUSE at fail = (check, reason)."""
    checks = [{"check": c, "result": "FAIL" if fail and c == fail[0] else "PASS",
               "reason": fail[1] if fail and c == fail[0] else None, "detail": ""} for c in CHECKS]
    return record("DECISION", met_s, request_id=request_id, decision="REFUSE" if fail else "ALLOW", checks=checks)


def request(request_id, met_s, command="CMD_PLD_SET_STATE", **parameters):
    return record("REQUEST", met_s, request_id=request_id, command=command, parameters=parameters or {"state": "OFF"})


def dispatch(request_id, met_s, command="CMD_PLD_SET_STATE", lease_id=None, **parameters):
    return record("DISPATCH", met_s, request_id=request_id, command=command,
                  parameters=parameters or {"state": "OFF"}, route="UPLINK", lease_id=lease_id)


def outcome(request_id, met_s, result="ACCEPTED", rej_reason=None):
    return record("OUTCOME", met_s, request_id=request_id, outcome=result, frame_met_s=met_s, rej_reason=rej_reason)


def report(met_s, kind="CHECK_IN", actions=(), evidence=(), timeline=()):
    return record("REPORT", met_s, report_kind=kind, turn_id=1, actions=list(actions), timeline=list(timeline),
                  condition={"summary": "", "evidence": list(evidence)})


def frame(met_s, **points):
    return {**NOMINAL_POINTS, "CDH_MET": met_s, "CDH_FRAME_CNT": met_s, **points}


def frames(*made):
    return {f["CDH_MET"]: f for f in made}
