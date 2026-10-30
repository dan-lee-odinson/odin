"""S9, pieces 7 and 8: phase 3's other two outside feeds (CONTRACT.md §6.5; the Director's approved phase-3 document,
§2). other_stations: stand-in stations, labeled modeled, each logging a beacon it hears after a seeded delay, by the
scenario's sealed schedule, drawn by the rule its sealed feed details state. space_weather: real data replayed and
labeled replayed, one report at each MET in contact on its cadence, with the replay's row of that MET and the Kp of its
interval. Both reach ODIN in contact only. Every rule is read from the sealed feed details (the Director's ruling of 30
October 2026). On made-up rules, schedules and a made-up replay: none of the held-out values."""

import json
import random

import pytest

from contract.validate import check
from harness.phase3 import HeldOut, SealBroken, draw_rule, space_weather_every_s
from tests.test_s9_feeds import RULES, UTC, state
from tests.test_s9_phase3_setup import made_up
from wrapper.feeds import CoreFeeds, Feeds, OtherStations, SpaceWeather, beacon_content, draw_schedule

CONTACT = (800, 1230)
STATIONS = ["STAND-IN-1", "STAND-IN-2"]


def in_contact(met_s):
    return CONTACT[0] <= met_s < CONTACT[1]


OTHERS = {"label": "modeled", "stations": STATIONS, "seed": 20261030,
          "draws": "for each beacon sent in the own station's contact window, in MET order, for each station in "
                   "turn, made up: random.Random(seed).random() < 0.5, then, if heard, randint(20, 50)"}
WEATHER = {"replay": "space_weather_replay.json", "at": "each MET that is a multiple of 600, made up",
           "content": {"sources": "made-up sources"}}


def test_red_the_schedule_is_drawn_by_the_rule_read_from_the_sealed_feed_details():
    rule = draw_rule({"other_stations": OTHERS})
    assert rule == {"seed": 20261030, "stations": STATIONS, "heard_p": 0.5, "delay_s": (20, 50)}
    beacons = [800, 860, 920, 980]
    # The made-up wording, as a second implementation: for each beacon in MET order, for each station in turn,
    # random.Random(seed).random() < 0.5, then, if heard, randint(20, 50).
    draw, expected = random.Random(20261030), []
    for beacon in beacons:
        for station in STATIONS:
            if draw.random() < 0.5:
                expected.append({"station": station, "beacon_met_s": beacon, "report_met_s": beacon + draw.randint(20, 50)})
    assert draw_schedule(rule["seed"], beacons, rule["stations"], rule["heard_p"], rule["delay_s"]) == expected
    assert [(r["station"], r["report_met_s"]) for r in expected] == [("STAND-IN-2", 905), ("STAND-IN-2", 1009)]
    with pytest.raises(SealBroken, match="the stand-in stations' draws"):
        draw_rule({"other_stations": dict(OTHERS, draws="by chance")})


def test_red_the_beacons_drawn_for_are_each_contacts_at_the_core_cadence(tmp_path):
    folder, seal = made_up(tmp_path)
    assert HeldOut(folder, seal=seal).scenario("H90").beacon_mets() == list(range(800, 1230, 50)) + list(
        range(6500, 6900, 50))


def test_red_a_stand_in_log_carries_the_beacon_as_sent_and_reaches_odin_in_contact_only():
    feed = OtherStations([{"station": "STAND-IN-1", "beacon_met_s": 840, "report_met_s": 950},
                          {"station": "STAND-IN-2", "beacon_met_s": 840, "report_met_s": 1300}], in_contact=in_contact,
                         rules=RULES)
    sent, later = state(battery_v=7.6614, soc_pct=66.3), state(mode="LOW_POWER", battery_v=6.95, soc_pct=32.4)
    assert feed.tick(840, UTC, sent) == []
    [log] = feed.tick(950, UTC, later)
    assert log["content"] == {"station": "STAND-IN-1", "label": "modeled", "beacon_met_s": 840,
                              "beacon": beacon_content(sent, RULES)}
    assert check("feed_report", log) == []
    assert feed.tick(1300, UTC, later) == []   # out of contact: not held for a later one


# A made-up replay, its columns named in the sealed replay's pattern: its time, utc...; its fluxes, ..._mev; its Kp
# interval's start, interval_start_...
REPLAY = {"goes": {"columns": ["offset_s", "utc_replayed", "low_mev", "high_mev"],
                   "rows": [[0, "made-up-0", 0.3, 0.1], [200, "made-up-200", 0.5, 0.2], [600, "made-up-600", 9.0, 3.0],
                            [900, "made-up-900", 40.0, 12.0], [1200, "made-up-1200", 30.0, 9.0]]},
          "kp": {"columns": ["offset_s", "interval_start_utc_replayed", "kp", "status"],
                 "rows": [[-100, "made-up-kp-1", 2.3, "def"], [500, "made-up-kp-2", 4.7, "def"]]}}


def test_red_space_weather_at_its_cadence_in_contact_with_the_kp_of_its_interval():
    assert space_weather_every_s({"space_weather": WEATHER}) == 600
    feed = SpaceWeather(REPLAY, every_s=600, sources="made-up sources", in_contact=lambda met_s: 0 <= met_s < 800)
    [first] = feed.tick(600, UTC, state())
    assert first["content"] == {"label": "replayed", "utc_replayed": "made-up-600",
                                "proton_flux_pfu": {"low_mev": 9.0, "high_mev": 3.0},
                                "kp": 4.7, "kp_interval_utc_replayed": "made-up-kp-2", "sources": "made-up sources"}
    assert check("feed_report", first) == []
    assert feed.tick(0, UTC, state())[0]["content"]["kp"] == 2.3            # the interval from -100
    assert feed.tick(200, UTC, state()) == []                               # a row, but not on the cadence
    assert feed.tick(1200, UTC, state()) == []                              # out of contact: not held


def test_the_feeds_together_tick_in_order():
    core = CoreFeeds(in_contact=in_contact, receiver_up=lambda met: True, slant_range_km=lambda met: 2000.0,
                     rules=RULES)
    others = OtherStations([{"station": "STAND-IN-1", "beacon_met_s": 1200, "report_met_s": 1200}],
                           in_contact=in_contact, rules=RULES)
    weather = SpaceWeather(REPLAY, every_s=600, sources="made-up sources", in_contact=in_contact)
    assert [r["feed"] for r in Feeds(core, others, weather).tick(1200, UTC, state())] == [
        "station_receiver", "beacon", "other_stations", "space_weather"]


def test_red_a_sealed_scenario_gives_all_four_feeds_its_replay_read_from_the_seal(tmp_path):
    feeds = {"other_stations": dict(OTHERS, schedule=[{"station": "STAND-IN-1", "beacon_met_s": 850,
                                                       "report_met_s": 1200}]),
             "space_weather": WEATHER}
    folder, seal = made_up(tmp_path, feeds=feeds, extra={"space_weather_replay.json": json.dumps(REPLAY).encode()})
    scenario = HeldOut(folder, seal=seal).scenario("H90")
    assert scenario.replay == REPLAY
    together = scenario.all_feeds()
    together.tick(850, UTC, state())
    assert [r["feed"] for r in together.tick(1200, UTC, state())] == ["station_receiver", "beacon", "other_stations",
                                                                       "space_weather"]
    unsealed = dict(feeds, space_weather={"replay": "not_sealed.json"})
    folder, seal = made_up(tmp_path / "unsealed", feeds=unsealed)
    with pytest.raises(SealBroken, match="not_sealed.json"):
        HeldOut(folder, seal=seal).scenario("H90")
