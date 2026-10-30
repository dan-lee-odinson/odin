"""S9, piece 5, part 2: a run that moves between seats (CONTRACT.md §10.1; the Director's approved phase-3 document,
§0 and §3): the ground seat in contact, in real time through COSMOS; the onboard seat out of contact, beside the
simulator, on the pause-and-charge clock. The run follows the scenario's seat schedule: at each boundary the seat, the
store it reads, the clock's pacing and BALDUR-0's route change together.

Flown here on a made-up chain of two short contacts of P3's pass against tests/fake_cosmos.py, with turns taken
in-process as ODIN's loop takes them: none of it is a held-out scenario."""

import json

import pytest

from contract.validate import check
from tests.harness_world import HarnessWorld
from tests.test_s5_connector import RATE, cosmos, free_port  # noqa: F401  (the fake COSMOS fixture)

SEATS = [(800, 830, "GROUND", "REAL_TIME"), (830, 900, "ONBOARD", "CHARGED"), (900, 940, "GROUND", "REAL_TIME")]


def seat_at(met_s):
    return next(seat for start, end, seat, _ in SEATS if start <= met_s < end)


def fly(tmp_path, cosmos, seats=SEATS):
    _, api, link_at = cosmos
    harness = HarnessWorld(tmp_path)
    plans = harness.world.plans([
        harness.plan(valid_from_met_s=800, valid_until_met_s=850, contact_window={"aos_met_s": 800, "los_met_s": 830}),
        harness.plan(plan_id="TYR0-P3-PASS2-v1", pass_index=2, valid_from_met_s=850, valid_until_met_s=940,
                     contact_window={"aos_met_s": 900, "los_met_s": 930})], signer="dev")
    run = harness.run(plans=plans, phase=3, seat="GROUND", pacing="REAL_TIME", rate=RATE, cosmos=api,
                      link_at=link_at, seats=seats)
    served = []
    try:
        assert run.start()
        for _ in range(200):
            data = run.next_turn()
            if json.loads(data).get("run_complete"):
                break
            served.append(json.loads(data))
    finally:
        run.stop()
    return run, served


def test_red_the_run_switches_seat_and_pacing_at_each_boundary_of_its_schedule(tmp_path, cosmos):
    run, _ = fly(tmp_path, cosmos)
    assert run.seat_changes == [(830, "ONBOARD", "CHARGED"), (900, "GROUND", "REAL_TIME")]


def test_red_each_turn_is_served_in_its_seat_reading_its_seats_own_store(tmp_path, cosmos):
    _, served = fly(tmp_path, cosmos)
    assert {seat_at(b["met_s"]) for b in served} == {"GROUND", "ONBOARD"}
    for bundle in served:
        assert check("turn_bundle", bundle) == []
        assert bundle["seat"] == seat_at(bundle["met_s"])
        assert bundle["observation"]["source"] == ("COSMOS" if bundle["seat"] == "GROUND" else "ONBOARD")
        assert (bundle["observation"]["ground_link"] is None) == (bundle["seat"] == "ONBOARD")


def test_red_the_onboard_seat_keeps_the_history_of_the_contact_the_ground_seat_flew(tmp_path, cosmos):
    _, served = fly(tmp_path, cosmos)
    onboard = [b for b in served if b["seat"] == "ONBOARD"]
    assert onboard
    rows = [row for b in onboard for row in (b["history"] or {}).get("rows", [])]
    assert any(row[0] < 830 for row in rows)   # frames from the first contact, while the ground seat flew it


def test_red_a_seat_schedule_with_the_ground_seat_off_real_time_is_refused(tmp_path):
    with pytest.raises(ValueError, match="ground seat runs in real time"):
        HarnessWorld(tmp_path).run(phase=3, seats=[(800, 830, "ONBOARD", "CHARGED"), (830, 900, "GROUND", "CHARGED")])
