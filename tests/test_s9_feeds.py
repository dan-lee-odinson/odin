"""S9, piece 2: the core outside feeds, station_receiver and beacon (CONTRACT.md §6.5), as each scenario's feed details
set them, every rule read from its sealed feed details (the Director's ruling of 30 October 2026). Built from the true
state and the script; reported in contact only; a failed receiver chain shows as NO_SIGNAL, never FAULT; the beacon
keeps sending through a housekeeping halt. On made-up rules from made-up feed details: none of the held-out values."""

import pytest

from contract.validate import check
from harness.phase3 import SealBroken, core_rules
from tests.test_s9_phase3_setup import MADE_UP_FEEDS
from wrapper.feeds import CoreFeeds, CoreRules, beacon_content, signal_level_dbm

CONTACT = (810, 1230)
UTC = "2026-08-01T13:41:43.000Z"
# The rules the made-up sealed feed details state, as harness/phase3.py reads them.
RULES = CoreRules(every_s=50, reference_dbm=-80.0, reference_km=500.0, db_per_decade=10.0, level_decimals=2,
                  noise_floor_dbm=-120.0, callsign="MADE-UP", battery_v_decimals=2, soc_pct_step=10)


def state(mode="NOMINAL", battery_v=7.6614, soc_pct=66.3, frame_generated=True):
    return {"frame_generated": frame_generated,
            "eps": {"mode": mode, "battery_v": battery_v, "soc_pct": soc_pct}}


def feeds(down=()):
    return CoreFeeds(in_contact=lambda met: CONTACT[0] <= met < CONTACT[1],
                     receiver_up=lambda met: not any(start <= met < end for start, end in down),
                     slant_range_km=lambda met: 2000.0, rules=RULES)


def fly(feed, start=700, end=1300, pre_roll_until=None):
    reports = []
    for met in range(start, end):
        reports += feed.tick(met, UTC, state(), pre_roll=pre_roll_until is not None and met < pre_roll_until)
    return reports


def test_red_each_core_feed_rule_is_read_from_the_sealed_feed_details():
    assert core_rules(MADE_UP_FEEDS) == RULES


def test_red_a_feed_detail_the_seal_does_not_state_as_read_refuses_the_scenario():
    def worded(feed, field, text):
        return dict(MADE_UP_FEEDS, **{feed: dict(MADE_UP_FEEDS[feed], **{field: text})})
    with pytest.raises(SealBroken, match="the beacon's cadence"):
        core_rules(worded("beacon", "at", "now and then"))
    with pytest.raises(SealBroken, match="the receiver's cadence"):
        core_rules(worded("station_receiver", "reports", "at a multiple of 50 or a multiple of 70"))
    with pytest.raises(SealBroken, match="different cadences"):
        core_rules(worded("beacon", "at", "each MET that is a multiple of 70"))


def test_the_signal_level_follows_the_sealed_model():
    assert [signal_level_dbm(km, RULES) for km in (500.0, 200.0, 50.0, 2000.0)] == [-80.0, -76.02, -70.0, -86.02]


def test_red_a_pass_reports_the_receiver_at_acquisition_and_at_its_cadence_and_the_beacon_at_its_cadence():
    reports = fly(feeds())
    receiver = [(r["met_s"], r["content"]["status"]) for r in reports if r["feed"] == "station_receiver"]
    beacons = [r["met_s"] for r in reports if r["feed"] == "beacon"]
    assert receiver == [(810, "LOCKED")] + [(met, "LOCKED") for met in range(850, 1230, 50)]
    assert beacons == list(range(850, 1230, 50))
    assert all(r["content"]["signal_level_dbm"] == -86.02 for r in reports if r["feed"] == "station_receiver")


def test_every_report_is_a_feed_report_as_the_contract_has_it():
    for report in fly(feeds(down=[(900, 960)])):
        assert check("feed_report", report) == []


def test_red_nothing_is_reported_out_of_contact_or_in_the_silent_pre_roll():
    assert all(CONTACT[0] <= r["met_s"] < CONTACT[1] for r in fly(feeds()))
    assert fly(feeds(), start=0, end=1300, pre_roll_until=810) == fly(feeds(), start=810, end=1300)
    assert fly(feeds(), start=0, end=810) == []


def test_red_a_failed_receiver_chain_shows_as_no_signal_never_fault_and_hears_no_beacon():
    reports = fly(feeds(down=[(900, 960)]))
    receiver = {r["met_s"]: r["content"] for r in reports if r["feed"] == "station_receiver"}
    assert receiver[900] == {"status": "NO_SIGNAL", "signal_level_dbm": -120.0}
    assert receiver[960] == {"status": "LOCKED", "signal_level_dbm": -86.02}
    assert "FAULT" not in {c["status"] for c in receiver.values()}
    assert [r["met_s"] for r in reports if r["feed"] == "beacon"] == [850] + list(range(1000, 1230, 50))


@pytest.mark.parametrize("given, battery_v, soc_pct", [((7.6614, 66.3), 7.66, 70), ((6.9571, 34.9), 6.96, 30),
                                                       ((7.2, 74.9), 7.2, 70)])
def test_the_beacon_carries_mode_voltage_and_charge_rounded_as_the_rules_say(given, battery_v, soc_pct):
    assert beacon_content(state("LOW_POWER", *given), RULES) == {"callsign": "MADE-UP", "EPS_MODE": "LOW_POWER",
                                                                 "battery_v": battery_v, "soc_pct": soc_pct}


def test_the_beacon_keeps_sending_through_a_housekeeping_halt():
    feed = feeds()
    feed.tick(849, UTC, state())
    halted = feed.tick(850, UTC, state(frame_generated=False))
    assert [r["feed"] for r in halted] == ["station_receiver", "beacon"]


# -- the feeds in the harness (S9, piece 2, wired after phase 2's last scored run) ---------------------------------

class Scripted:
    """Feed reports at the METs given, as the harness asks for them each tick."""

    def __init__(self, at):
        self.at = at

    def tick(self, met_s, utc, state):
        return [{"feed": feed, "met_s": met_s, "utc": utc, "content": {"status": "LOCKED", "signal_level_dbm": -84.0}}
                for feed in self.at.get(met_s, ())]


def test_red_each_feed_report_is_a_turn_trigger_and_the_turn_that_merges_it_carries_it(tmp_path):
    from tests.harness_world import HarnessWorld, records, turns
    run = HarnessWorld(tmp_path).run(phase=3, feeds=Scripted({800: ["station_receiver", "beacon"],
                                                                860: ["station_receiver"]}))
    try:
        assert run.start()
        served = turns(run, 3)
    finally:
        run.stop()
    for bundle in served:
        assert check("turn_bundle", bundle) == []
        wanted = [(t["detail"]["feed"], t["met_s"]) for t in bundle["triggers"] if t["type"] == "FEED_REPORT"]
        assert [(r["feed"], r["met_s"]) for r in bundle["feeds"]] == wanted
    shown = [(r["feed"], r["met_s"]) for bundle in served for r in bundle["feeds"]]
    assert shown == [("station_receiver", 800), ("beacon", 800), ("station_receiver", 860)]   # each once
    assert [b["turn_kind"] for b in served] == ["ACT", "REPORT", "ACT"]   # the pass start's report waits its turn
    logged = [t for r in records(run, "TRIGGER") for t in r["body"]["triggers"] if t["type"] == "FEED_REPORT"]
    assert len(logged) == 3


def test_red_outside_feeds_are_phase_3s_only(tmp_path):
    from tests.harness_world import HarnessWorld, turns
    harness = HarnessWorld(tmp_path)
    with pytest.raises(ValueError, match="phase 3's only"):
        harness.run(feeds=Scripted({}))
    run = harness.run()
    try:
        assert run.start()
        assert turns(run, 1)[0]["feeds"] is None   # null outside phase 3
    finally:
        run.stop()


def test_a_sealed_scenarios_core_feeds_read_huginns_orbit_at_its_place_in_the_campaign_week(tmp_path):
    # The made-up sealed scenario sits where P3 does, a public phase-2 place: contact 9, MET 800 at campaign time
    # 257303 from the campaign epoch.
    import wrapper.huginn
    from harness.phase3 import HeldOut
    from sim.orbit import Orbit
    from tests.test_s9_phase3_setup import made_up
    folder, seal = made_up(tmp_path)
    feed = HeldOut(folder, seal=seal).scenario("H90").core_feeds()
    orbit = Orbit(wrapper.huginn.HUGINN / "defs" / "orbit", "2026-07-29T14:00:00Z")
    assert feed.tick(799, UTC, state()) == []                                    # before acquisition
    [receiver, beacon] = feed.tick(850, UTC, state())
    assert receiver["content"] == {"status": "LOCKED",
                                   "signal_level_dbm": signal_level_dbm(orbit.look_angles_at(850 + 257303)[2], RULES)}
    assert beacon["content"]["callsign"] == "MADE-UP"   # the made-up feed details' rules, read from the seal


def test_red_a_sealed_scenarios_receiver_fault_downs_its_receiver_for_its_span(tmp_path):
    # S9, piece 3: the own receiver chain failed from before acquisition (a made-up span covering the first contact).
    from harness.phase3 import HeldOut
    from tests.test_s9_phase3_setup import made_up
    folder, seal = made_up(tmp_path, script={"ground_receiver": {"failed_from_met_s": 0, "until_met_s": 1230}})
    scenario = HeldOut(folder, seal=seal).scenario("H90")
    assert scenario.receiver_down == [(0, 1230)]
    feed = scenario.core_feeds()
    reports = [r for met in range(800, 1230) for r in feed.tick(met, UTC, state())]
    assert {r["feed"] for r in reports} == {"station_receiver"}   # no beacon heard
    assert {(r["content"]["status"], r["content"]["signal_level_dbm"]) for r in reports} == {("NO_SIGNAL", -120.0)}
