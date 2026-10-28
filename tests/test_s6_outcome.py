"""BALDUR-0's OUTCOME (CONTRACT.md §9.3, §16.4 U17): read from telemetry, never assumed. The counters'
change by the next frame with the affected point; a reset's acknowledgement is the post-reset counter
epoch; no counter change within 10 s is NO_ACKNOWLEDGEMENT."""

import pytest

from contract.validate import check
from tests.baldur_world import World


@pytest.fixture
def world(tmp_path):
    world = World(tmp_path)
    assert world.start()
    world.points.update(CDH_CMD_ACC_CNT=3, CDH_CMD_REJ_CNT=0, PLD_STATE="OFF")
    return world


def dispatched(world, command, parameters=None):
    record = world.decide(command, parameters or {})
    assert record["decision"] == "ALLOW"
    world.gateway.dispatch_pending()
    return record["request_id"]


def next_frame(world, **points):
    world.advance(1)
    world.points.update(points)
    return world.gateway.observe(world.frame())


def test_an_accepted_command_is_read_from_the_next_frame(world):
    request_id = dispatched(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    [outcome] = next_frame(world, CDH_CMD_ACC_CNT=4, PLD_STATE="ON")
    assert outcome == {"request_id": request_id, "outcome": "ACCEPTED", "acc_before": 3, "acc_after": 4,
                       "rej_before": 0, "rej_after": 0, "rej_reason": "NONE",
                       "point": {"mnemonic": "PLD_STATE", "value": "ON"}, "frame_met_s": 101, "met_s": 101,
                       "utc": outcome["utc"]}
    assert check("outcome", outcome) == []
    assert world.bodies("OUTCOME") == [outcome]


def test_a_rejection_carries_the_spacecrafts_reason(world):
    dispatched(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    [outcome] = next_frame(world, CDH_CMD_REJ_CNT=1, CDH_REJ_REASON="MODE_INHIBIT")
    assert (outcome["outcome"], outcome["rej_reason"], outcome["point"]) == (
        "REJECTED", "MODE_INHIBIT", {"mnemonic": "PLD_STATE", "value": "OFF"})
    assert check("outcome", outcome) == []


def test_a_reset_is_acknowledged_by_the_counter_epoch(world):
    dispatched(world, "CMD_SYS_RESET")
    [outcome] = next_frame(world, CDH_CMD_ACC_CNT=1, CDH_CMD_REJ_CNT=0)
    assert (outcome["outcome"], outcome["acc_before"], outcome["acc_after"], outcome["point"]) == ("ACCEPTED", 3, 1, None)


def test_red_a_frame_from_before_the_dispatch_shows_no_outcome(world):
    dispatched(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    world.points.update(CDH_CMD_ACC_CNT=4)
    assert world.gateway.observe(world.frame()) == []   # stamped at the dispatch's own met_s


def test_red_no_counter_change_in_10_seconds_is_no_acknowledgement_never_assumed(world):
    request_id = dispatched(world, "CMD_SAFE_ENTER")
    for _ in range(9):
        assert next_frame(world) == []
    [outcome] = next_frame(world)
    assert outcome == {"request_id": request_id, "outcome": "NO_ACKNOWLEDGEMENT", "acc_before": 3, "acc_after": None,
                       "rej_before": 0, "rej_after": None, "rej_reason": None, "point": None, "frame_met_s": None,
                       "met_s": 110, "utc": outcome["utc"]}
    assert check("outcome", outcome) == []


def test_no_frame_during_a_halt_still_ends_in_no_acknowledgement(world):
    dispatched(world, "CMD_SAFE_ENTER")
    world.no_frame = True
    world.advance(10)
    [outcome] = world.gateway.observe(None)
    assert outcome["outcome"] == "NO_ACKNOWLEDGEMENT"


def test_two_waiting_commands_are_given_the_counters_moves_in_dispatch_order(world):
    first = dispatched(world, "CMD_PLD_SET_STATE", {"state": "ON"})
    second = dispatched(world, "CMD_PLD_SET_STATE", {"state": "OFF"})
    outcomes = next_frame(world, CDH_CMD_ACC_CNT=4, CDH_CMD_REJ_CNT=1, CDH_REJ_REASON="ARG_RANGE")
    assert [(o["request_id"], o["outcome"]) for o in outcomes] == [(first, "ACCEPTED"), (second, "REJECTED")]


# A reset's acknowledgement is the post-reset counter epoch, which needs no earlier frame, so a reset dispatched
# before the seat has any frame is still read as ACCEPTED; any other command with no frame before it has nothing
# to compare and stays NO_ACKNOWLEDGEMENT, which is honest (the Director's word of 28 October 2026, on S5's
# live check).
def test_a_reset_dispatched_before_any_frame_is_acknowledged_by_the_epoch(world):
    world.no_frame = True
    request_id = dispatched(world, "CMD_SYS_RESET")
    world.no_frame = False
    [outcome] = next_frame(world, CDH_CMD_ACC_CNT=1, CDH_CMD_REJ_CNT=0)
    assert (outcome["request_id"], outcome["outcome"], outcome["acc_before"], outcome["acc_after"]) == (
        request_id, "ACCEPTED", None, 1)
    assert check("outcome", outcome) == []


def test_red_another_command_dispatched_before_any_frame_stays_no_acknowledgement(world):
    world.no_frame = True
    dispatched(world, "CMD_SAFE_ENTER")
    world.no_frame = False
    for _ in range(9):
        assert next_frame(world, CDH_CMD_ACC_CNT=4, EPS_MODE="SAFE") == []
    [outcome] = next_frame(world)
    assert (outcome["outcome"], outcome["acc_before"]) == ("NO_ACKNOWLEDGEMENT", None)


def reset_epochs(scenario, windows, step_s=60):
    """[(reset MET, (CDH_CMD_ACC_CNT, CDH_CMD_REJ_CNT) in the first frame after it)] for a reset sent up at the
    first tick of each contact, before the seat has any frame, and through each housekeeping halt from the tick
    after it began, every step_s, the scenario's scripted commands outside the contacts kept as a run keeps
    them. A reset that lands on the halt's own first tick is applied before the fault, in HUGINN's order within
    a tick, and the halt then begins: ODIN cannot answer a halt on the tick it begins."""
    from wrapper.simulator import Simulator

    probe = Simulator(scenario, windows=windows)
    end = probe.start_met_s + scenario.duration_s
    halted = []
    while probe.met_s < end - 1:
        if probe.step() is None:
            halted.append(probe.met_s)
    began = [t for i, t in enumerate(halted) if i == 0 or t - halted[i - 1] > 1]
    times = sorted({aos for aos, _ in windows}
                   | {t for t in halted if any(0 < t - start and (t - start - 1) % step_s == 0 for start in began)})
    found = []
    for at in times:
        simulator = Simulator(scenario, windows=windows, start_at=at)
        simulator.uplink("CMD_SYS_RESET", {})
        frame = None
        while frame is None and simulator.met_s < end - 1:
            frame = simulator.step()
        found.append((at, (frame["CDH_CMD_ACC_CNT"], frame["CDH_CMD_REJ_CNT"]) if frame else None))
    return found


PHASE_2 = {"P1_nominal": [(0, 410)], "P2_array_string_loss": [(2190, 2520), (21800, 22230)],
           "P3_stuck_load": [(800, 1230)], "P4_hk_generation_halt": [(1100, 1530)]}


@pytest.mark.parametrize("name", sorted(PHASE_2))
def test_a_reset_at_any_contact_start_or_halt_of_phase_2_shows_its_epoch(name):
    from wrapper.huginn import load_scenario

    found = reset_epochs(load_scenario(name), PHASE_2[name])
    assert found and all(epoch == (1, 0) for _, epoch in found), [f for f in found if f[1] != (1, 0)]
