"""S9, piece 5, part 2: a run that moves between seats (CONTRACT.md §10.1; the Director's approved phase-3 document,
§0 and §3): the ground seat in contact, in real time through COSMOS; the onboard seat out of contact, beside the
simulator, on the pause-and-charge clock. The run follows the scenario's seat schedule: at each boundary the seat, the
store it reads, the clock's pacing and BALDUR-0's route change together.

Flown here on a made-up chain of two short contacts of P3's pass against tests/fake_cosmos.py, with turns taken
in-process as ODIN's loop takes them: none of it is a held-out scenario."""

import json
import time
from datetime import datetime

import pytest

from contract.validate import check
from tests.harness_world import HarnessWorld
from tests.test_s5_connector import RATE, cosmos, free_port  # noqa: F401  (the fake COSMOS fixture)

SEATS = [(800, 830, "GROUND", "REAL_TIME"), (830, 900, "ONBOARD", "CHARGED"), (900, 940, "GROUND", "REAL_TIME")]
AOS = 900   # the second contact's acquisition of signal, where the onboard seat hands back to the ground seat


def seat_at(met_s):
    return next(seat for start, end, seat, _ in SEATS if start <= met_s < end)


def fly(tmp_path, cosmos, seats=SEATS, on_served=None):
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
            if on_served is not None:
                on_served(run, served[-1])
    finally:
        run.stop()
    return run, served


def charged_onto_the_acquisition(past_s):
    """The first onboard turn, measured as having taken long enough for its charge to reach AOS and run past_s ticks
    beyond it: the turn's time, which the harness measures from the bundle served, set back to that."""
    def on_served(run, bundle):
        if bundle["seat"] == "ONBOARD" and not hasattr(run, "charged_from"):
            run.charged_from = bundle["met_s"]
            run._served_at = time.monotonic() - (AOS - bundle["met_s"] + past_s - 0.5)
    return on_served


# The Director's ruling of 31 October 2026: in a phase-3 run, an onboard turn's charge stepped the acquisition's tick,
# whose switch to real time let the clock step the next while the ground seat waited for COSMOS to show the first, and
# the first was lost. A charge onto the acquisition, and a long turn's charge across it, now stop there; the ground
# seat then runs in real time from that tick, and no frame is lost.
@pytest.mark.parametrize("past_s", [0, 20], ids=["landing on the acquisition", "a long turn across it"])
def test_red_a_charge_onto_the_acquisition_loses_no_frame_and_the_ground_seat_runs_in_real_time(tmp_path, cosmos,
                                                                                                 past_s):
    run, _ = fly(tmp_path, cosmos, on_served=charged_onto_the_acquisition(past_s))
    assert run.charged_from < AOS
    truth = [json.loads(line) for line in (run.folder / "truth.jsonl").read_bytes().splitlines()]
    assert [r for r in truth if r["type"] == "GROUND_MISSED"] == []
    stepped = {r["met_s"]: datetime.fromisoformat(r["utc"].replace("Z", "+00:00")) for r in truth
               if r["type"] == "TRUE_STATE"}
    assert all((stepped[met + 1] - stepped[met]).total_seconds() >= 0.8 / RATE for met in range(AOS, AOS + 5))


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
