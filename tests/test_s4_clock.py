"""The run's clock (CONTRACT.md §4, §10.1): real time in phases 1 and 2 and phase 3's ground seat; in phase
3's onboard seat the simulator pauses while ODIN takes a turn, then advances by at least the turn's
measured wall-clock time before BALDUR-0's dispatch recheck, and quiet stretches run faster than real
time."""

import threading
import time

import pytest

from wrapper.clock import RunClock
from tests.huginn_scenarios import bare
from wrapper.simulator import Simulator


class FakeWall:
    """A wall clock that moves only when slept on, with a little drift on every call."""

    def __init__(self, drift=0.0):
        self.now = 1000.0
        self.slept = []
        self.drift = drift

    def wall(self):
        self.now += self.drift
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def simulator(start_at=0):
    return Simulator(bare("P1_nominal"), windows=[], start_at=start_at)


def test_real_time_steps_one_tick_per_wall_second_without_drift():
    fake = FakeWall(drift=0.004)
    clock = RunClock(simulator(), until_met_s=100, wall=fake.wall, sleep=fake.sleep)
    started = fake.now
    clock.run()
    assert clock.met_s == 99
    # Paced against the total, so the drift on each call is taken out of the next sleep, never added up.
    assert abs((fake.now - started) - 100.0) < 0.05
    assert all(s < 1.0 for s in fake.slept)


def test_red_pacing_tick_by_tick_would_have_drifted():
    # The same drift with one second slept per tick, the way the test above would catch.
    fake = FakeWall(drift=0.004)
    started = fake.now
    for _ in range(100):
        fake.wall()
        fake.sleep(1.0)
    assert abs((fake.now - started) - 100.0) >= 0.05


def test_rate_runs_real_time_faster_for_tests():
    fake = FakeWall()
    RunClock(simulator(), until_met_s=100, rate=10.0, wall=fake.wall, sleep=fake.sleep).run()
    assert sum(fake.slept) == pytest.approx(10.0)


def test_charged_pacing_never_sleeps():
    fake = FakeWall()
    clock = RunClock(simulator(), until_met_s=500, pacing="CHARGED", wall=fake.wall, sleep=fake.sleep)
    clock.run()
    assert clock.met_s == 499 and fake.slept == []


def test_red_pause_is_refused_in_real_time():
    clock = RunClock(simulator(), until_met_s=10)
    with pytest.raises(RuntimeError):
        clock.pause()


def a_turn_at(met_s):
    """A charged clock whose harness pauses it at met_s, as a trigger there would."""
    holder = {}

    def on_tick(frame):
        if holder["clock"].met_s == met_s:
            holder["clock"].pause()
            holder["paused"].set()

    holder["paused"] = threading.Event()
    clock = holder["clock"] = RunClock(simulator(), until_met_s=1000, pacing="CHARGED", on_tick=on_tick)
    return clock, holder["paused"]


def test_the_simulator_stays_paused_through_a_turn():
    clock, paused = a_turn_at(120)
    clock.start()
    assert paused.wait(5)
    threading.Event().wait(0.2)   # however long ODIN thinks, no tick passes
    assert clock.met_s == 120
    clock.stop()


@pytest.mark.parametrize("thinking, ticks", [(0.4, 1), (3.0, 3), (3.2, 4), (41.7, 42)])
def test_a_turn_costs_its_thinking_time_rounded_up_to_whole_ticks(thinking, ticks):
    clock, paused = a_turn_at(120)
    clock.start()
    assert paused.wait(5)
    assert clock.charge(thinking) == ticks
    assert clock.met_s == 120 + ticks
    clock.stop()


def test_the_dispatch_after_the_charge_reaches_the_spacecraft_at_the_charged_met():
    clock, paused = a_turn_at(120)
    clock.start()
    assert paused.wait(5)
    clock.charge(7.5)
    # BALDUR-0 rechecks and dispatches here, on the UPLINK route, with the clock at 128.
    assert clock.met_s == 128
    clock.simulator.uplink("CMD_PLD_SET_STATE", {"state": "ON"})
    clock.resume()
    clock.join(5)
    assert clock.simulator.applied == [(129, "CMD_PLD_SET_STATE", True, "NONE")]


def test_red_a_charge_with_the_clock_running_is_refused():
    clock = RunClock(simulator(), until_met_s=10, pacing="CHARGED")
    with pytest.raises(RuntimeError):
        clock.charge(2.0)


def test_red_switching_to_real_time_paces_from_the_switch_with_no_catch_up():
    # The tick that switches is real time's first, so the next comes a full tick after it (31 October 2026); the wall
    # time that passed while charged is never caught up.
    fake = FakeWall()
    clock = RunClock(simulator(), until_met_s=50, pacing="CHARGED", wall=fake.wall, sleep=fake.sleep)
    switched, stepped = {}, {}

    def on_tick(frame):
        stepped[clock.met_s] = fake.now
        if clock.met_s == 29 and not switched:
            fake.now += 500.0   # wall time that passed while charged
            clock.set_pacing("REAL_TIME")
            switched["at"] = fake.now

    clock.on_tick = on_tick
    clock.run()
    assert clock.met_s == 49
    assert [stepped[met] - switched["at"] for met in range(30, 50)] == pytest.approx([float(n) for n in range(1, 21)])


# A charge that lands on a seat's boundary (31 October 2026): in a phase-3 run, an onboard turn's charge stepped the
# tick of an acquisition of signal, whose switch to real time let the clock run on at once; it stepped the next tick
# while the ground seat was still waiting for COSMOS to show the first, and that frame was lost. Here the tick at 130
# switches as the harness's seat schedule does, then waits as the ground seat waits for COSMOS.

def a_turn_charged_into_real_time(rate, wait_s):
    """A charged clock paused for a turn at 120, whose tick at 130 switches it to real time and then waits wait_s.
    Returns the clock and what each tick saw: {met_s: (wall time stepped, met_s once its work was done)}."""
    seen, holder = {}, {}

    def on_tick(frame):
        clock, met = holder["clock"], holder["clock"].met_s
        stepped = time.monotonic()
        if met == 120:
            clock.pause()
            holder["paused"].set()
        if met == 130:
            clock.set_pacing("REAL_TIME")
            time.sleep(wait_s)
        seen[met] = (stepped, clock.met_s)

    holder["paused"] = threading.Event()
    clock = holder["clock"] = RunClock(simulator(), until_met_s=1000, pacing="CHARGED", rate=rate, on_tick=on_tick)
    clock.start()
    assert holder["paused"].wait(5)
    return clock, seen


def until(seen, met_s, within=5.0):
    deadline = time.monotonic() + within
    while met_s not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    return met_s in seen


def test_red_a_charge_that_lands_on_the_switch_holds_the_clock_until_that_tick_is_done():
    clock, seen = a_turn_charged_into_real_time(rate=10.0, wait_s=0.3)   # the wait longer than a tick
    try:
        assert clock.charge(10.0) == 10
        assert seen[130][1] == 130   # nothing stepped while the switching tick waited
        assert until(seen, 131)
    finally:
        clock.stop()


def test_red_the_tick_after_a_charge_crosses_into_real_time_comes_a_full_tick_later():
    clock, seen = a_turn_charged_into_real_time(rate=2.0, wait_s=0.05)   # a tick of 0.5 s
    try:
        assert clock.charge(10.0) == 10
        assert until(seen, 132)
        assert seen[131][0] - seen[130][0] >= 0.45
        assert seen[132][0] - seen[131][0] >= 0.45
    finally:
        clock.stop()


def test_red_a_turn_charged_across_the_switch_is_charged_only_up_to_it():
    # A long turn: its time would run 30 ticks past the boundary, which the new pacing does not charge.
    clock, seen = a_turn_charged_into_real_time(rate=10.0, wait_s=0.0)
    try:
        assert clock.charge(40.0) == 10
        assert clock.met_s == 130
        assert until(seen, 133)
        assert all(seen[met + 1][0] - seen[met][0] >= 0.08 for met in (130, 131, 132))
    finally:
        clock.stop()
