"""S9, piece 6: phase 3's latch-up, carried out by the wrapper (the Director's approved phase-3 document, scenario C,
and §5 selection 3). At onset, with the payload ON, HUGINN's own stuck-load term is set: the load current steps up as
PASS-3's stuck load does. Turning the payload OFF clears it, the load falls back to its base, and turning the payload
on again does not bring it back. With the payload already OFF at onset there is no latch-up, and the truth file says
so. If the payload is still ON a set time of simulation time after onset, the truth file records the damage.

On HUGINN's public P1_nominal scenario with its scripted commands removed, the payload switched by the onboard uplink;
the onset and damage times are made up, none of the held-out values."""

import json

import pytest

from harness.phase3 import HeldOut
from log.event_log import TruthLog, verify_truth
from tests.huginn_scenarios import bare
from tests.test_s9_phase3_setup import made_up
from wrapper.simulator import Simulator

LATCH = {"onset_met_s": 40, "damage_after_s": 20}


def flown(tmp_path, steps, latch_up=LATCH):
    """Fly P1 nominal from MET 0 with steps {met_s: payload state}, the payload commanded at those METs; returns
    (load current by MET, the truth file's LATCH_UP bodies by MET, the truth file's path)."""
    held = {}
    sim = Simulator(bare("P1_nominal"), windows=[(0, 10000)], latch_up=latch_up,
                    truth=TruthLog.create(tmp_path / "truth.jsonl", met_clock=lambda: held["sim"].met_s))
    held["sim"] = sim
    load = {}
    for met in range(0, 90):
        if met in steps:
            sim.uplink("CMD_PLD_SET_STATE", {"state": steps[met]})
        sim.step()
        load[met] = sim.spacecraft.eps.state.load_current_a
    records = [json.loads(line) for line in (tmp_path / "truth.jsonl").read_text(encoding="utf-8").splitlines()]
    events = {r["met_s"]: r["body"] for r in records if r["type"] == "LATCH_UP"}
    return load, events, tmp_path / "truth.jsonl"


def test_red_the_latch_up_steps_the_load_at_onset_and_payload_off_clears_it_for_good(tmp_path):
    load, events, path = flown(tmp_path, {5: "ON", 50: "OFF", 60: "ON"})
    assert {m: e["event"] for m, e in events.items()} == {40: "ONSET", 50: "CLEARED"}   # applied at that tick
    assert load[40] - load[39] == pytest.approx(0.4, abs=0.05)            # PASS-3's step
    assert load[45] - load[39] == pytest.approx(0.4, abs=0.05)            # held while the payload stays ON
    assert load[55] < load[39] - 0.05                                     # OFF: back to the base, the payload's too
    assert load[65] == pytest.approx(load[39], abs=0.05)                  # ON again: no latch-up term
    assert verify_truth(path) == []


def test_red_a_payload_still_on_at_the_damage_time_is_recorded_damaged(tmp_path):
    _, events, path = flown(tmp_path, {5: "ON"})
    assert {m: e["event"] for m, e in events.items()} == {40: "ONSET", 60: "DAMAGED"}
    assert events[60] == {"event": "DAMAGED", "onset_met_s": 40, "damage_met_s": 60, "source": "SCRIPT"}
    assert verify_truth(path) == []


def test_red_a_payload_already_off_at_onset_is_no_latch_up_and_the_truth_file_says_so(tmp_path):
    load, events, path = flown(tmp_path, {})
    assert {m: e["event"] for m, e in events.items()} == {40: "NOT_EXERCISED"}
    assert load[45] == pytest.approx(load[39], abs=0.05)
    assert verify_truth(path) == []


def test_a_sealed_scenarios_latch_up_is_given_to_the_run_as_its_script_sets_it(tmp_path):
    script = {"latch_up": {"onset_met_s": 7000, "damage": {"after_s": 120}}}
    folder, seal = made_up(tmp_path, script=script)
    assert HeldOut(folder, seal=seal).scenario("H90").latch_up == {"onset_met_s": 7000, "damage_after_s": 120}
    folder, seal = made_up(tmp_path / "none")
    assert HeldOut(folder, seal=seal).scenario("H90").latch_up is None


def test_red_the_run_gives_its_latch_up_to_the_simulator(tmp_path):
    from tests.harness_world import HarnessWorld
    run = HarnessWorld(tmp_path).run(phase=3, latch_up={"onset_met_s": 1100, "damage_after_s": 120})
    try:
        assert run.start()
        assert run.simulator.latch_up["onset_met_s"] == 1100 and run.simulator.latch_up["state"] == "WAITING"
    finally:
        run.stop()
