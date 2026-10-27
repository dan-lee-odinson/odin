"""BALDUR-0 between a decision and the spacecraft (CONTRACT.md §9.3, §9.4, §9.6; §16.4 U17).

Immediately before an allowed command goes out, the whole decision is run again on the newest
telemetry and the current met_s. The command goes out only if the result and its basis, the plan,
arming act, class and lease, are unchanged; otherwise DECISION_VOIDED names the check, and nothing is
sent. A request a plan boundary has passed fails PLAN as PLAN_MISMATCH (U29). A use counts against its
lease when the command is dispatched. Revocation voids every request still waiting, at once.
"""

from datetime import timedelta

import pytest

from tests.baldur_world import START, World, utc_text


@pytest.fixture
def world(tmp_path):
    world = World(tmp_path)
    assert world.start()
    return world


def allowed(world, command, parameters=None, **changes):
    record = world.decide(command, parameters, **changes)
    assert record["decision"] == "ALLOW", record
    return record


def voided(written):
    return [(body["check"], body["reason"]) for type_, body in written if type_ == "DECISION_VOIDED"]


# -- dispatch ----------------------------------------------------------------------------------

def test_an_allowed_command_goes_out_once_through_cosmos_in_the_ground_seat(world):
    record = allowed(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    assert world.gateway.pending() == [record["request_id"]]
    assert world.sent == []
    written = world.gateway.dispatch_pending()
    assert [type_ for type_, _ in written] == ["DISPATCH"]
    assert written[0][1] == {"request_id": record["request_id"], "command": "CMD_PLD_SET_STATE",
                             "parameters": {"state": "ON"}, "route": "COSMOS", "lease_id": None,
                             "met_s": 100.0, "utc": world.utc()}
    assert world.sent == [("CMD_PLD_SET_STATE", {"state": "ON"}, "COSMOS")]
    assert world.gateway.pending() == [] and world.gateway.dispatch_pending() == []
    assert world.bodies("DISPATCH") == [written[0][1]]


def test_in_the_onboard_seat_a_command_goes_straight_to_the_uplink(world):
    world.seat = "ONBOARD"
    allowed(world, "CMD_SAFE_ENTER", {})
    world.gateway.dispatch_pending()
    assert world.sent == [("CMD_SAFE_ENTER", {}, "UPLINK")]


def test_a_refused_request_never_waits_and_is_never_sent(world):
    world.decide("CMD_PLD_SET_RATE", {"rate": 1.0})
    assert world.gateway.pending() == []
    assert world.gateway.dispatch_pending() == [] and world.sent == []


def test_requests_go_out_oldest_first(world):
    first = allowed(world, "CMD_PLD_SET_STATE", {"state": "OFF"})
    second = allowed(world, "CMD_SAFE_ENTER", {})
    assert [body["request_id"] for _, body in world.gateway.dispatch_pending()] == [first["request_id"],
                                                                                    second["request_id"]]


def test_a_use_is_counted_against_its_lease_when_dispatched_not_when_allowed(world):
    allowed(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    allowed(world, "CMD_MODE_SET", {"target": "NOMINAL"})
    assert world.gateway.uses_left() == {"L1": 2}
    written = world.gateway.dispatch_pending()
    assert [body["lease_id"] for _, body in written] == ["L1", "L1"]
    assert world.gateway.uses_left() == {"L1": 0}


def test_each_plan_counts_its_own_leases(world):
    allowed(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    world.gateway.dispatch_pending()
    assert world.gateway.uses_left() == {"L1": 1}
    world.advance(5400)
    assert world.gateway.uses_left() == {"L1": 4}   # TYR0-DEV-PASS2-v1's own L1, for CMD_PLD_SET_RATE


def test_a_route_that_fails_leaves_the_request_waiting_and_counts_no_use(world):
    record = allowed(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    world.route_down = True
    with pytest.raises(ConnectionError):
        world.gateway.dispatch_pending()
    assert world.gateway.pending() == [record["request_id"]]
    assert world.bodies("DISPATCH") == [] and world.gateway.uses_left() == {"L1": 2}
    world.route_down = False
    assert [type_ for type_, _ in world.gateway.dispatch_pending()] == ["DISPATCH"]
    assert world.gateway.uses_left() == {"L1": 1}


# -- the recheck (§9.3) ------------------------------------------------------------------------

def test_a_command_allowed_under_one_plan_is_voided_once_the_boundary_passes(world):
    """Done-when of S3: decided under one plan, dispatched after the boundary, voided. The request
    names the plan it was decided under, so the recheck refuses it at PLAN (U29)."""
    world.advance(5290)                                       # met_s 5390, TYR0-DEV-PASS1-v1
    record = allowed(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    world.advance(20)                                         # met_s 5410, TYR0-DEV-PASS2-v1
    written = world.gateway.dispatch_pending()
    assert voided(written) == [("PLAN", "PLAN_MISMATCH")]
    assert written[0][1]["detail"] == "the request names plan TYR0-DEV-PASS1-v1; TYR0-DEV-PASS2-v1 is in force"
    assert written[0][1]["decision_record_id"] == next(
        r["record_id"] for r in world.records("DECISION") if r["body"]["request_id"] == record["request_id"])
    assert world.sent == []
    # The same command, sent afresh under the new plan and naming it, is allowed.
    allowed(world, "CMD_PLD_SET_STATE", {"state": "ON"})


def test_a_leased_command_waiting_across_the_boundary_is_voided_at_plan(world):
    world.advance(5290)
    allowed(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    world.advance(20)
    assert voided(world.gateway.dispatch_pending()) == [("PLAN", "PLAN_MISMATCH")]
    assert world.sent == [] and world.gateway.uses_left() == {"L1": 4}


def test_telemetry_gone_stale_while_waiting_voids_all_but_the_protective_commands(world):
    allowed(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    allowed(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    allowed(world, "CMD_SYS_RESET", {})
    world.frame_age = 11.0
    written = world.gateway.dispatch_pending()
    assert voided(written) == [("CLASS", "NO_FRESH_TELEMETRY"), ("CLASS", "NO_FRESH_TELEMETRY")]   # U25
    assert world.sent == [("CMD_SYS_RESET", {}, "COSMOS")]


def test_a_class_raised_while_waiting_changes_the_basis(world):
    allowed(world, "CMD_PLD_SET_STATE", {"state": "OFF"})            # C1, no lease
    world.points["EPS_BATT_SOC"] = 30.0                                # now C4 under L2
    written = world.gateway.dispatch_pending()
    assert voided(written) == [("CLASS", "BASIS_CHANGED")]
    assert written[0][1]["detail"] == "class was C1 when allowed and is C4 now"


def test_a_lease_condition_that_stops_holding_while_waiting_voids_the_command(world):
    allowed(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    world.points["EPS_BATT_SOC"] = 20.0
    assert voided(world.gateway.dispatch_pending()) == [("LEASE", "CONDITION_FAILED")]


def test_uses_spent_by_those_ahead_void_a_leased_command_still_waiting(world):
    for target in ("LOW_POWER", "NOMINAL", "LOW_POWER"):
        allowed(world, "CMD_MODE_SET", {"target": target})          # each allowed: none dispatched yet
    written = world.gateway.dispatch_pending()
    assert [type_ for type_, _ in written] == ["DISPATCH", "DISPATCH", "DECISION_VOIDED"]
    assert voided(written) == [("LEASE", "NO_USES_LEFT")]
    assert len(world.sent) == 2


def test_an_act_expiring_while_a_command_waits_voids_it(tmp_path):
    world = World(tmp_path)
    plans = world.plans()
    assert world.start(plans=plans, act=world.act(plans, expires_utc=utc_text(START + timedelta(seconds=30))))
    allowed(world, "CMD_SAFE_ENTER", {})
    world.advance(30)
    assert voided(world.gateway.dispatch_pending()) == [("ARMING", "ACT_EXPIRED")]


# -- revocation (§9.4) -------------------------------------------------------------------------

def test_revocation_voids_every_waiting_request_at_once(world):
    records = [allowed(world, "CMD_SAFE_ENTER", {}), allowed(world, "CMD_MODE_SET", {"target": "LOW_POWER"})]
    written = world.gateway.revoke()
    assert voided(written) == [("CEILING", "REVOKED")] * 2
    assert [body["request_id"] for _, body in written] == [r["request_id"] for r in records]
    assert world.gateway.pending() == [] and world.gateway.dispatch_pending() == [] and world.sent == []
    assert world.bodies("DECISION_VOIDED") == [body for _, body in written]


def test_the_harness_not_baldur0_writes_the_revoke_record(world):
    world.gateway.revoke()
    assert world.records("REVOKE") == []
