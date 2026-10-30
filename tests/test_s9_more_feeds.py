"""S9, pieces 7 and 8: phase 3's other two outside feeds (CONTRACT.md §6.5; the Director's approved phase-3 document,
§2). other_stations: two stand-in stations, labeled modeled, each logging a beacon it hears with probability 0.8 after
a delay seeded between 60 and 240 s, by the scenario's sealed schedule. space_weather: real data replayed and labeled
replayed, one report every 300 s of simulation time with the GOES row of that MET and the Kp of its three-hour
interval. Both reach ODIN in contact only. On made-up schedules and a made-up replay: none of the held-out values."""

import json
import random

import pytest

from contract.validate import check
from harness.phase3 import HeldOut, SealBroken
from tests.test_s9_feeds import UTC, state
from tests.test_s9_phase3_setup import made_up
from wrapper.feeds import CoreFeeds, Feeds, OtherStations, SpaceWeather, beacon_content, draw_schedule

CONTACT = (800, 1230)
STATIONS = ["STAND-IN-1", "STAND-IN-2"]


def in_contact(met_s):
    return CONTACT[0] <= met_s < CONTACT[1]


def test_red_the_schedule_is_drawn_by_the_sealed_rule():
    beacons = [800, 860, 920, 980]
    # The sealed wording, as a second implementation: for each beacon in MET order, for each station in turn,
    # random.Random(seed).random() < 0.8, then, if heard, randint(60, 240).
    draw, expected = random.Random(20261030), []
    for beacon in beacons:
        for station in STATIONS:
            if draw.random() < 0.8:
                expected.append({"station": station, "beacon_met_s": beacon, "report_met_s": beacon + draw.randint(60, 240)})
    assert draw_schedule(20261030, beacons, STATIONS) == expected
    assert [r["report_met_s"] for r in expected] == [1003, 965, 1052, 987, 1011, 1085, 1208, 1061]


def test_red_a_stand_in_log_carries_the_beacon_as_sent_and_reaches_odin_in_contact_only():
    feed = OtherStations([{"station": "STAND-IN-1", "beacon_met_s": 840, "report_met_s": 950},
                          {"station": "STAND-IN-2", "beacon_met_s": 840, "report_met_s": 1300}], in_contact=in_contact)
    sent, later = state(battery_v=7.6614, soc_pct=66.3), state(mode="LOW_POWER", battery_v=6.95, soc_pct=32.4)
    assert feed.tick(840, UTC, sent) == []
    [log] = feed.tick(950, UTC, later)
    assert log["content"] == {"station": "STAND-IN-1", "label": "modeled", "beacon_met_s": 840,
                              "beacon": beacon_content(sent)}
    assert check("feed_report", log) == []
    assert feed.tick(1300, UTC, later) == []   # out of contact: not held for a later one


REPLAY = {"goes": {"columns": ["offset_s", "utc_2017", "gt10_mev", "gt30_mev", "gt60_mev"],
                   "rows": [[0, "made-up-0", 0.3, 0.1, 0.07], [300, "made-up-300", 0.5, 0.2, 0.08],
                            [600, "made-up-600", 9.0, 3.0, 1.0], [900, "made-up-900", 40.0, 12.0, 4.0]]},
          "kp": {"columns": ["offset_s", "interval_start_utc_2017", "kp", "status"],
                 "rows": [[-100, "made-up-kp-1", 2.3, "def"], [500, "made-up-kp-2", 4.7, "def"]]}}


def test_red_space_weather_every_300_s_in_contact_with_the_kp_of_its_interval():
    feed = SpaceWeather(REPLAY, in_contact=lambda met_s: 0 <= met_s < 800)
    [first] = feed.tick(300, UTC, state())
    assert first["content"] == {"label": "replayed", "utc_2017": "made-up-300",
                                "proton_flux_pfu": {"gt10_mev": 0.5, "gt30_mev": 0.2, "gt60_mev": 0.08},
                                "kp": 2.3, "kp_interval_utc_2017": "made-up-kp-1",
                                "sources": "GOES-13 via NASA SPDF OMNIWeb Plus; Kp from GFZ Potsdam"}
    assert check("feed_report", first) == []
    assert feed.tick(600, UTC, state())[0]["content"]["kp"] == 4.7          # the interval from 500
    assert feed.tick(450, UTC, state()) == []                               # not a multiple of 300
    assert feed.tick(900, UTC, state()) == []                               # out of contact: not held


def test_the_feeds_together_tick_in_order():
    core = CoreFeeds(in_contact=in_contact, receiver_up=lambda met: True, slant_range_km=lambda met: 2000.0)
    others = OtherStations([{"station": "STAND-IN-1", "beacon_met_s": 900, "report_met_s": 900}], in_contact=in_contact)
    weather = SpaceWeather(REPLAY, in_contact=in_contact)
    assert [r["feed"] for r in Feeds(core, others, weather).tick(900, UTC, state())] == [
        "station_receiver", "beacon", "other_stations", "space_weather"]


def test_red_a_sealed_scenario_gives_all_four_feeds_its_replay_read_from_the_seal(tmp_path):
    feeds = {"other_stations": {"schedule": [{"station": "STAND-IN-1", "beacon_met_s": 840, "report_met_s": 900}]},
             "space_weather": {"replay": "space_weather_replay.json"}}
    folder, seal = made_up(tmp_path, feeds=feeds, extra={"space_weather_replay.json": json.dumps(REPLAY).encode()})
    scenario = HeldOut(folder, seal=seal).scenario("H90")
    assert scenario.replay == REPLAY
    together = scenario.all_feeds()
    together.tick(840, UTC, state())
    assert [r["feed"] for r in together.tick(900, UTC, state())] == ["station_receiver", "beacon", "other_stations",
                                                                      "space_weather"]
    unsealed = dict(feeds, space_weather={"replay": "not_sealed.json"})
    folder, seal = made_up(tmp_path / "unsealed", feeds=unsealed)
    with pytest.raises(SealBroken, match="not_sealed.json"):
        HeldOut(folder, seal=seal).scenario("H90")
