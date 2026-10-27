"""BALDUR-0's decision on receipt (CONTRACT.md §9.1, §7.4, §5.5, §9.6; §16.4 U14): an ALLOW for each
class, the envelope's raise to C4, the protective commands, and a red case for every reason of every
check. Each test runs dev-run-0001 at met_s 100 under TYR0-DEV-PASS1-v1, with fresh telemetry at
80 % state of charge (tests/baldur_world.py), unless it says otherwise."""

from datetime import timedelta

import pytest

from contract.validate import check
from gateway import decision
from gateway.acts import Act
from gateway.plans import Plan
from tests.baldur_world import RUN, START, World, changed, example_plan, failure, utc_text


@pytest.fixture
def world(tmp_path):
    world = World(tmp_path)
    assert world.start()
    return world


def decided(world, command, parameters=None, **changes):
    record = world.decide(command, parameters, **changes)
    assert check("decision_record", record) == []
    return record


def results(record):
    return [c["result"] for c in record["checks"]]


def detail(record, name):
    return next(c["detail"] for c in record["checks"] if c["check"] == name)


def context(world, **changes):
    """A context built by hand, for the two reasons no run through the Gateway can reach."""
    plan = Plan("TYR0-DEV-PASS1-v1", "sha256:" + "0" * 64, 0, 5400, example_plan(1))
    act = Act("ARM-DEV-01", "ARM", "AI_AUTONOMOUS", (RUN,), "2026-11-04T23:59:59.000Z", "sha256:" + "1" * 64)
    values = {"run_id": RUN, "met_s": world.met, "utc": world.utc(), "plan": plan, "arming": act,
              "revoked": False, "frame": world.frame(), "odin_key": world.odin.public_key(), "nonce_reused": False}
    return decision.Context(**{**values, **changes})


# -- ALLOW, one for each class -----------------------------------------------------------------

@pytest.mark.parametrize("command, parameters, class_", [
    ("CMD_PLD_SET_STATE", {"state": "ON"}, "C1"),
    ("CMD_SAFE_ENTER", {}, "C3"),
    ("CMD_SYS_RESET", {}, "C3"),
])
def test_c1_and_c3_are_allowed_under_the_first_plan(world, command, parameters, class_):
    record = decided(world, command, parameters)
    assert record["decision"] == "ALLOW"
    assert results(record) == ["PASS"] * 8
    assert (record["base_class"], record["class"], record["lease_id"]) == (class_, class_, None)
    assert (record["plan_id"], record["arming_act_id"], record["rung"]) == ("TYR0-DEV-PASS1-v1", "ARM-DEV-01",
                                                                              "AI_AUTONOMOUS")
    assert (record["met_s"], record["utc"]) == (100.0, utc_text(START))


def test_c2_is_allowed_under_the_second_plan_which_does_not_prohibit_it(world):
    world.advance(5400)
    record = decided(world, "CMD_PLD_SET_RATE", {"rate": 2.5}, plan_id="TYR0-DEV-PASS2-v1")
    assert record["decision"] == "ALLOW"
    assert (record["plan_id"], record["base_class"], record["class"], record["lease_id"]) == (
        "TYR0-DEV-PASS2-v1", "C2", "C2", None)


def test_c4_is_allowed_under_a_lease_whose_conditions_hold(world):
    record = decided(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    assert record["decision"] == "ALLOW"
    assert (record["base_class"], record["class"], record["lease_id"]) == ("C4", "C4", "L1")


# -- the envelope's raise to C4 (§5.1, §7.4) ---------------------------------------------------

def test_an_envelope_limit_that_does_not_hold_raises_c1_to_c4_and_a_lease_can_cover_it(world):
    world.points["EPS_BATT_SOC"] = 30.0
    record = decided(world, "CMD_PLD_SET_STATE", {"state": "OFF"})
    assert record["decision"] == "ALLOW"
    assert (record["base_class"], record["class"], record["lease_id"]) == ("C1", "C4", "L2")
    assert detail(record, "CLASS") == "raised to C4: EPS_BATT_SOC ge 35 does not hold (EPS_BATT_SOC is 30.0)"


def test_an_envelope_limit_that_does_not_hold_raises_c2_to_c4(world):
    world.advance(5400)
    world.points["EPS_MODE"] = "LOW_POWER"
    record = decided(world, "CMD_PLD_SET_RATE", {"rate": 1.5})
    assert record["decision"] == "ALLOW"
    assert (record["base_class"], record["class"], record["lease_id"]) == ("C2", "C4", "L1")
    assert detail(record, "CLASS") == "raised to C4: EPS_MODE eq NOMINAL does not hold (EPS_MODE is 'LOW_POWER')"


def test_a_raised_command_with_no_lease_for_its_arguments_is_refused(world):
    world.points["EPS_BATT_SOC"] = 30.0
    record = decided(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    assert failure(record) == ("LEASE", "ARGUMENTS_NOT_COVERED")
    assert (record["base_class"], record["class"]) == ("C1", "C4")


def test_a_point_missing_from_the_frame_does_not_hold(world):
    del world.points["EPS_BATT_SOC"]
    record = decided(world, "CMD_PLD_SET_STATE", {"state": "OFF"})
    assert record["class"] == "C4"
    assert detail(record, "CLASS") == "raised to C4: EPS_BATT_SOC ge 35 does not hold (EPS_BATT_SOC is None)"


# -- the protective commands (§5.5, §9.6) ------------------------------------------------------

@pytest.mark.parametrize("command", ["CMD_SAFE_ENTER", "CMD_SYS_RESET"])
def test_an_envelope_limit_never_raises_a_protective_command(world, command):
    world.points["EPS_BATT_SOC"] = 5.0
    record = decided(world, command, {})
    assert record["decision"] == "ALLOW"
    assert (record["base_class"], record["class"], detail(record, "CLASS")) == ("C3", "C3", None)


@pytest.mark.parametrize("command", ["CMD_SAFE_ENTER", "CMD_SYS_RESET"])
@pytest.mark.parametrize("telemetry", ["a frame 600 s old", "no frame"])
def test_stale_or_missing_telemetry_never_blocks_a_protective_command(world, command, telemetry):
    world.frame_age, world.no_frame = 600.0, telemetry == "no frame"
    record = decided(world, command, {})
    assert record["decision"] == "ALLOW"
    assert record["class"] == "C3"


@pytest.mark.parametrize("command", ["CMD_SAFE_ENTER", "CMD_SYS_RESET"])
def test_a_revocation_still_takes_the_protective_commands_away(world, command):
    world.gateway.revoke()
    assert failure(decided(world, command, {})) == ("CEILING", "REVOKED")


# -- PLAN --------------------------------------------------------------------------------------

def test_a_plan_is_in_force_from_its_start_up_to_but_not_including_its_end(world):
    world.advance(5299.5)
    assert decided(world, "CMD_SAFE_ENTER", {})["plan_id"] == "TYR0-DEV-PASS1-v1"
    world.advance(0.5)
    assert decided(world, "CMD_SAFE_ENTER", {})["plan_id"] == "TYR0-DEV-PASS2-v1"


@pytest.mark.parametrize("named", [None, "TYR0-DEV-PASS2-v1"])
def test_red_plan_no_plan_in_force_once_the_chain_ends(world, named):
    world.advance(10700)
    record = decided(world, "CMD_SAFE_ENTER", {}, plan_id=named)
    assert failure(record) == ("PLAN", "NO_PLAN_IN_FORCE")
    assert results(record) == ["FAIL"] + ["NOT_RUN"] * 6 + ["PASS"]
    assert (record["plan_id"], record["rung"], record["base_class"], record["class"]) == (
        None, "HUMAN_ONLY", None, None)
    assert record["arming_act_id"] == "ARM-DEV-01"   # U26: the act that arms the run, though PLAN stopped


@pytest.mark.parametrize("named", ["TYR0-DEV-PASS2-v1", "TYR0-DEV-PASS9-v1", None])
def test_red_plan_mismatch_a_request_naming_another_plan_or_none(world, named):
    """U29: a request belongs to the plan it names; under any other it is refused, null included."""
    record = decided(world, "CMD_SAFE_ENTER", {}, plan_id=named)
    assert failure(record) == ("PLAN", "PLAN_MISMATCH")
    assert results(record) == ["FAIL"] + ["NOT_RUN"] * 6 + ["PASS"]
    assert record["plan_id"] == "TYR0-DEV-PASS1-v1"
    expected = f"plan {named}" if named else "no plan"
    assert detail(record, "PLAN") == f"the request names {expected}; TYR0-DEV-PASS1-v1 is in force"


def test_a_request_naming_the_next_plan_is_allowed_once_that_plan_is_in_force(world):
    assert failure(decided(world, "CMD_SAFE_ENTER", {}, plan_id="TYR0-DEV-PASS2-v1")) == ("PLAN", "PLAN_MISMATCH")
    world.advance(5300)
    assert decided(world, "CMD_SAFE_ENTER", {}, plan_id="TYR0-DEV-PASS2-v1")["decision"] == "ALLOW"


def test_red_plan_no_plan_in_force_before_a_run_starts(tmp_path):
    world = World(tmp_path)
    record = decided(world, "CMD_SAFE_ENTER", {})
    assert failure(record) == ("PLAN", "NO_PLAN_IN_FORCE")
    assert record["arming_act_id"] is None


# -- ARMING ------------------------------------------------------------------------------------

def test_red_arming_not_armed(tmp_path):
    # Through the Gateway a run with no valid act never starts, so its requests stop at PLAN.
    world = World(tmp_path)
    record, _ = decision.decide(world.request("CMD_SAFE_ENTER", {}), context(world, arming=None))
    assert check("decision_record", record) == []
    assert failure(record) == ("ARMING", "NOT_ARMED")
    assert (record["arming_act_id"], record["rung"]) == (None, "HUMAN_ONLY")


def test_red_arming_act_expired(tmp_path):
    world = World(tmp_path)
    plans = world.plans()
    assert world.start(plans=plans, act=world.act(plans, expires_utc=utc_text(START + timedelta(seconds=60))))
    world.advance(59)
    assert decided(world, "CMD_SAFE_ENTER", {})["decision"] == "ALLOW"
    world.advance(1)
    record = decided(world, "CMD_SAFE_ENTER", {})
    assert failure(record) == ("ARMING", "ACT_EXPIRED")
    assert (record["arming_act_id"], record["rung"]) == ("ARM-DEV-01", "HUMAN_ONLY")


def test_red_arming_act_not_for_run(tmp_path):
    # Through the Gateway a run starts only under an act that covers it, and a restore act for
    # another run is refused (WRONG_RUN), so ACT_NOT_FOR_RUN is reached here with an act built by hand.
    world = World(tmp_path)
    act = Act("ARM-DEV-02", "ARM", "AI_AUTONOMOUS", ("dev-run-0002",), "2026-11-04T23:59:59.000Z",
              "sha256:" + "1" * 64)
    record, _ = decision.decide(world.request("CMD_SAFE_ENTER", {}), context(world, arming=act))
    assert check("decision_record", record) == []
    assert failure(record) == ("ARMING", "ACT_NOT_FOR_RUN")
    assert detail(record, "ARMING") == "ARM-DEV-02 does not cover run dev-run-0001"


# -- ORIGIN ------------------------------------------------------------------------------------

def test_red_origin_a_request_signed_with_another_key(world):
    record = decided(world, "CMD_SAFE_ENTER", {}, signer="dev")
    assert failure(record) == ("ORIGIN", "BAD_SIGNATURE")


def test_red_origin_a_request_changed_after_signing(world):
    request = world.request("CMD_PLD_SET_STATE", {"state": "OFF"})
    request["parameters"] = {"state": "ON"}
    assert failure(world.gateway.receive_request(request)) == ("ORIGIN", "BAD_SIGNATURE")


def test_red_origin_a_request_replayed(world):
    request = world.request("CMD_SAFE_ENTER", {})
    assert world.gateway.receive_request(request)["decision"] == "ALLOW"
    assert failure(world.gateway.receive_request(request)) == ("ORIGIN", "NONCE_REUSED")


def test_red_origin_a_new_request_with_a_used_nonce(world):
    first = world.request("CMD_SAFE_ENTER", {})
    world.gateway.receive_request(first)
    assert failure(decided(world, "CMD_SYS_RESET", {}, nonce=first["nonce"])) == ("ORIGIN", "NONCE_REUSED")


def test_a_request_refused_before_origin_still_spends_its_nonce(world):
    first = world.request("CMD_SAFE_ENTER", {}, plan_id="TYR0-DEV-PASS2-v1")
    assert failure(world.gateway.receive_request(first)) == ("PLAN", "PLAN_MISMATCH")
    assert failure(decided(world, "CMD_SAFE_ENTER", {}, nonce=first["nonce"])) == ("ORIGIN", "NONCE_REUSED")


@pytest.mark.parametrize("run_id", ["dev-run-0002", "dev-run-0009"])
def test_red_origin_a_request_for_another_run(world, run_id):
    """U28: dev-run-0002 is covered by the same batch act, but this Gateway runs dev-run-0001."""
    record = decided(world, "CMD_SAFE_ENTER", {}, run_id=run_id)
    assert failure(record) == ("ORIGIN", "WRONG_RUN")
    assert detail(record, "ORIGIN") == f"the request is for run {run_id}; this run is dev-run-0001"


def test_a_forged_request_for_another_run_is_refused_for_its_signature(world):
    record = decided(world, "CMD_SAFE_ENTER", {}, run_id="dev-run-0002", signer="dev")
    assert failure(record) == ("ORIGIN", "BAD_SIGNATURE")


def test_a_forged_request_does_not_spend_the_nonce_it_carries(world):
    forged = world.request("CMD_SAFE_ENTER", {}, signer="dev")
    assert failure(world.gateway.receive_request(forged)) == ("ORIGIN", "BAD_SIGNATURE")
    assert decided(world, "CMD_SAFE_ENTER", {}, nonce=forged["nonce"])["decision"] == "ALLOW"


@pytest.mark.parametrize("seconds, refused", [(30, False), (-30, False), (30.001, True), (-31, True)])
def test_red_origin_clock_skew_past_30_seconds(world, seconds, refused):
    record = decided(world, "CMD_SAFE_ENTER", {}, utc=utc_text(START + timedelta(seconds=seconds)))
    assert failure(record) == (("ORIGIN", "CLOCK_SKEW") if refused else None)


# -- CEILING -----------------------------------------------------------------------------------

def test_red_ceiling_revoked(world):
    world.gateway.revoke()
    record = decided(world, "CMD_PLD_SET_STATE", {"state": "OFF"})
    assert failure(record) == ("CEILING", "REVOKED")
    assert record["rung"] == "HUMAN_ONLY"
    assert world.gateway.rung() == ("HUMAN_ONLY", "REVOKED")


# -- PROHIBITED --------------------------------------------------------------------------------

def test_red_prohibited_by_the_plan_in_force(world):
    record = decided(world, "CMD_PLD_SET_RATE", {"rate": 1.0})
    assert failure(record) == ("PROHIBITED", "PROHIBITED_BY_PLAN")
    assert detail(record, "PROHIBITED") == "TYR0-DEV-PASS1-v1 prohibits CMD_PLD_SET_RATE"
    assert (record["base_class"], record["class"]) == (None, None)


# -- CLASS -------------------------------------------------------------------------------------

@pytest.mark.parametrize("age, refused", [(10.0, False), (10.5, True)])
def test_red_class_no_fresh_telemetry_past_10_seconds(world, age, refused):
    world.frame_age = age
    record = decided(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    assert failure(record) == (("CLASS", "NO_FRESH_TELEMETRY") if refused else None)
    assert (record["base_class"], record["class"]) == ("C1", "C1")


def test_red_class_no_frame_at_all(world):
    world.no_frame = True
    record = decided(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    assert failure(record) == ("CLASS", "NO_FRESH_TELEMETRY")
    assert detail(record, "CLASS") == "no frame received"


def test_red_class_the_rung_refuses_the_class(tmp_path):
    # Every schema-valid act arms at AI_AUTONOMOUS, and every other way to HUMAN_ONLY stops at an
    # earlier check, so the rung table is reached here with an act at HUMAN_ONLY, built by hand.
    world = World(tmp_path)
    act = Act("ARM-DEV-01", "ARM", "HUMAN_ONLY", (RUN,), "2026-11-04T23:59:59.000Z", "sha256:" + "1" * 64)
    record, _ = decision.decide(world.request("CMD_SAFE_ENTER", {}), context(world, arming=act))
    assert check("decision_record", record) == []
    assert failure(record) == ("CLASS", "RUNG_REFUSES_CLASS")
    assert record["rung"] == "HUMAN_ONLY"


# -- LEASE -------------------------------------------------------------------------------------

def test_red_lease_none_names_the_command(world):
    world.advance(5400)
    record = decided(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    assert failure(record) == ("LEASE", "NO_LEASE")
    assert record["lease_id"] is None


def test_red_lease_does_not_cover_the_arguments(world):
    world.advance(5400)
    world.points["EPS_MODE"] = "LOW_POWER"
    record = decided(world, "CMD_PLD_SET_RATE", {"rate": 2.5})
    assert failure(record) == ("LEASE", "ARGUMENTS_NOT_COVERED")


def test_red_lease_condition_does_not_hold(world):
    world.points["EPS_BATT_SOC"] = 20.0
    record = decided(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    assert failure(record) == ("LEASE", "CONDITION_FAILED")
    assert record["lease_id"] == "L1"
    assert detail(record, "LEASE") == "L1: EPS_BATT_SOC ge 25 does not hold (EPS_BATT_SOC is 20.0)"


def test_red_lease_no_uses_left(world):
    for _ in range(2):
        assert decided(world, "CMD_MODE_SET", {"target": "LOW_POWER"})["decision"] == "ALLOW"
        world.gateway.dispatch_pending()
    record = decided(world, "CMD_MODE_SET", {"target": "NOMINAL"})
    assert failure(record) == ("LEASE", "NO_USES_LEFT")
    assert detail(record, "LEASE") == "L1: 2 of 2 uses dispatched"


@pytest.mark.parametrize("telemetry", ["a frame 11 s old", "no frame"])
def test_red_class_no_fresh_telemetry_refuses_the_mode_command_whatever_its_lease(world, telemetry):
    """U25: CMD_MODE_SET is refused at CLASS, though L1's condition holds on the stale frame."""
    world.frame_age, world.no_frame = 11.0, telemetry == "no frame"
    record = decided(world, "CMD_MODE_SET", {"target": "LOW_POWER"})
    assert failure(record) == ("CLASS", "NO_FRESH_TELEMETRY")
    assert (record["base_class"], record["class"], record["lease_id"]) == ("C4", "C4", None)


@pytest.mark.parametrize("command, parameters", [
    ("CMD_PLD_SET_STATE", {"state": "OFF"}), ("CMD_PLD_SET_RATE", {"rate": 1.0}),
    ("CMD_MODE_SET", {"target": "LOW_POWER"}), ("CMD_SAFE_ENTER", {}), ("CMD_SYS_RESET", {}),
])
@pytest.mark.parametrize("soc", [80.0, 30.0, 20.0])
def test_leases_no_fresh_telemetry_is_never_given(world, command, parameters, soc):
    """§16.4 lists NO_FRESH_TELEMETRY under LEASE too, but after U25 no command reaches LEASE on stale
    telemetry: each is refused at CLASS or, if protective, allowed. Under the second plan, where no
    command is prohibited, whatever the envelope says."""
    world.advance(5400)
    world.points["EPS_BATT_SOC"], world.frame_age = soc, 11.0
    record = decided(world, command, parameters)
    expected = None if command in ("CMD_SAFE_ENTER", "CMD_SYS_RESET") else ("CLASS", "NO_FRESH_TELEMETRY")
    assert failure(record) == expected


def _two_mode_leases(tmp_path):
    """A world whose first plan splits the mode command between two leases: L1 for NOMINAL, used
    above 25 % state of charge, and L3 for LOW_POWER, used above 10 %."""
    world = World(tmp_path)
    first = example_plan(1)
    l1 = {**first["leases"][0], "arguments": {"target": ["NOMINAL"]}}
    l3 = {"lease_id": "L3", "command": "CMD_MODE_SET", "arguments": {"target": ["LOW_POWER"]},
          "conditions": [{"point": "EPS_BATT_SOC", "op": "ge", "value": 10}], "max_uses": 1}
    assert world.start(plans=world.plans([changed(first, leases=[l1, first["leases"][1], l3]), example_plan(2)]))
    return world


def test_two_leases_for_one_command_each_cover_their_own_arguments(tmp_path):
    world = _two_mode_leases(tmp_path)
    world.points["EPS_BATT_SOC"] = 20.0
    assert decided(world, "CMD_MODE_SET", {"target": "LOW_POWER"})["lease_id"] == "L3"
    record = decided(world, "CMD_MODE_SET", {"target": "NOMINAL"})
    assert failure(record) == ("LEASE", "CONDITION_FAILED")
    assert record["lease_id"] == "L1"


# -- RECORD ------------------------------------------------------------------------------------

def test_every_request_is_logged_and_then_its_decision_allowed_or_refused(world):
    decided(world, "CMD_SAFE_ENTER", {})
    decided(world, "CMD_PLD_SET_RATE", {"rate": 1.0})
    decided(world, "CMD_SAFE_ENTER", {}, signer="dev")
    types = [r["type"] for r in world.records() if r["type"] in ("REQUEST", "DECISION")]
    assert types == ["REQUEST", "DECISION"] * 3
    decisions = world.bodies("DECISION")
    assert [d["decision"] for d in decisions] == ["ALLOW", "REFUSE", "REFUSE"]
    assert all([c["check"] for c in d["checks"]] == list(decision.CHECKS) for d in decisions)
    assert all(d["checks"][-1] == {"check": "RECORD", "result": "PASS", "reason": None, "detail": None}
               for d in decisions)
