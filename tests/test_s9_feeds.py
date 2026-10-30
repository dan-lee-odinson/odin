"""S9, piece 2: the core outside feeds, station_receiver and beacon (CONTRACT.md §6.5), as each scenario's feed details
set them. Built from the true state and the script; reported in contact only; a failed receiver chain shows as
NO_SIGNAL, never FAULT; the beacon keeps sending through a housekeeping halt."""

import pytest

from contract.validate import check
from wrapper.feeds import NOISE_FLOOR_DBM, CoreFeeds, beacon_content, signal_level_dbm

CONTACT = (800, 1230)
UTC = "2026-08-01T13:41:43.000Z"


def state(mode="NOMINAL", battery_v=7.6614, soc_pct=66.3, frame_generated=True):
    return {"frame_generated": frame_generated,
            "eps": {"mode": mode, "battery_v": battery_v, "soc_pct": soc_pct}}


def feeds(down=()):
    return CoreFeeds(in_contact=lambda met: CONTACT[0] <= met < CONTACT[1],
                     receiver_up=lambda met: not any(start <= met < end for start, end in down),
                     slant_range_km=lambda met: 2000.0)


def fly(feed, start=700, end=1300, pre_roll_until=None):
    reports = []
    for met in range(start, end):
        reports += feed.tick(met, UTC, state(), pre_roll=pre_roll_until is not None and met < pre_roll_until)
    return reports


def test_the_signal_level_falls_20_db_a_decade_of_range_from_minus_90_at_1000_km():
    assert (signal_level_dbm(1000.0), signal_level_dbm(2000.0), signal_level_dbm(500.0)) == (-90.0, -96.0, -84.0)


def test_red_a_pass_reports_the_receiver_at_acquisition_and_each_minute_and_the_beacon_each_minute():
    reports = fly(feeds())
    receiver = [(r["met_s"], r["content"]["status"]) for r in reports if r["feed"] == "station_receiver"]
    beacons = [r["met_s"] for r in reports if r["feed"] == "beacon"]
    assert receiver == [(800, "LOCKED")] + [(met, "LOCKED") for met in range(840, 1230, 60)]
    assert beacons == list(range(840, 1230, 60))
    assert all(r["content"]["signal_level_dbm"] == -96.0 for r in reports if r["feed"] == "station_receiver")


def test_every_report_is_a_feed_report_as_the_contract_has_it():
    for report in fly(feeds(down=[(900, 960)])):
        assert check("feed_report", report) == []


def test_red_nothing_is_reported_out_of_contact_or_in_the_silent_pre_roll():
    assert all(CONTACT[0] <= r["met_s"] < CONTACT[1] for r in fly(feeds()))
    assert fly(feeds(), start=0, end=1300, pre_roll_until=800) == fly(feeds(), start=800, end=1300)
    assert fly(feeds(), start=0, end=800) == []


def test_red_a_failed_receiver_chain_shows_as_no_signal_never_fault_and_hears_no_beacon():
    reports = fly(feeds(down=[(900, 960)]))
    receiver = {r["met_s"]: r["content"] for r in reports if r["feed"] == "station_receiver"}
    assert receiver[900] == {"status": "NO_SIGNAL", "signal_level_dbm": NOISE_FLOOR_DBM}
    assert receiver[960] == {"status": "LOCKED", "signal_level_dbm": -96.0}
    assert "FAULT" not in {c["status"] for c in receiver.values()}
    assert [r["met_s"] for r in reports if r["feed"] == "beacon"] == [840] + list(range(960, 1230, 60))


@pytest.mark.parametrize("given, battery_v, soc_pct", [((7.6614, 66.3), 7.7, 65), ((7.64, 67.6), 7.6, 70),
                                                       ((6.95, 32.4), 7.0, 30)])
def test_the_beacon_carries_mode_voltage_to_a_tenth_and_charge_to_the_nearest_5(given, battery_v, soc_pct):
    assert beacon_content(state("LOW_POWER", *given)) == {"callsign": "HUGINN", "EPS_MODE": "LOW_POWER",
                                                          "battery_v": battery_v, "soc_pct": soc_pct}


def test_the_beacon_keeps_sending_through_a_housekeeping_halt():
    feed = feeds()
    feed.tick(839, UTC, state())
    halted = feed.tick(840, UTC, state(frame_generated=False))
    assert [r["feed"] for r in halted] == ["station_receiver", "beacon"]
