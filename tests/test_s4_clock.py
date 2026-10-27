"""The run's clock (CONTRACT.md §4, §10.1): real time in phases 1 and 2 and phase 3's ground seat; in phase
3's onboard seat the simulator pauses while ODIN takes a turn, then advances by at least the turn's
measured wall-clock time before BALDUR-0's dispatch recheck, and quiet stretches run faster than real
time."""

import threading

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


def test_switching_to_real_time_starts_pacing_afresh_with_no_catch_up():
    fake = FakeWall()
    clock = RunClock(simulator(), until_met_s=50, pacing="CHARGED", wall=fake.wall, sleep=fake.sleep)
    switched = {}

    def on_tick(frame):
        if clock.met_s == 29 and not switched:
            fake.now += 500.0   # wall time that passed while charged
            clock.set_pacing("REAL_TIME")
            switched["at"] = fake.now

    clock.on_tick = on_tick
    clock.run()
    assert clock.met_s == 49
    assert fake.now - switched["at"] == pytest.approx(20.0)
