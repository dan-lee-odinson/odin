"""Phase 3's four outside feeds (CONTRACT.md §6.5): the two core feeds, station_receiver and beacon (S9, piece 2),
built from the simulator's true state and the scenario's script and disclosed as modeled; other_stations (piece 7),
two stand-in stations' logs of the beacon, labeled modeled; and space_weather (piece 8), real data replayed and
labeled replayed. Feeds puts them together, in that order within a tick.

Each scenario's own feed details (its `feeds` section) set what this does. The own station's receiver reports LOCKED,
with a signal level from the slant range, while the station hears the spacecraft, and NO_SIGNAL at the noise floor
otherwise; a failed receiver chain shows as NO_SIGNAL, never FAULT. It reports at each change of state and at each
MET in contact that is a multiple of 60. The beacon goes out at each MET that is a multiple of 60, through a
housekeeping halt too, and is reported when the own station hears it. Reports reach ODIN in contact only: none in the
silent pre-roll, and none held for a later contact.

Nothing here runs a turn or touches the link: the harness calls tick() once a tick, with what the station hears and
the spacecraft's true state, and delivers what it returns as turn triggers.
"""

import math
import random

NOISE_FLOOR_DBM = -130.0
REFERENCE_DBM, REFERENCE_KM = -90.0, 1000.0   # -90.0 dBm at 1000 km, falling 20 dB a decade of range
EVERY_S = 60
CALLSIGN = "HUGINN"


def signal_level_dbm(slant_range_km):
    """The own station's signal level from the spacecraft, to 0.1 dB."""
    return round(REFERENCE_DBM + 20 * math.log10(REFERENCE_KM / slant_range_km), 1)


def beacon_content(state):
    """The beacon's content from the spacecraft's true state: its mode, its battery voltage to 0.1 V and its state of
    charge to the nearest 5 %."""
    eps = state["eps"]
    return {"callsign": CALLSIGN, "EPS_MODE": eps["mode"], "battery_v": round(eps["battery_v"], 1),
            "soc_pct": int(5 * round(eps["soc_pct"] / 5))}


class CoreFeeds:
    """station_receiver and beacon, tick by tick, for one run.

    in_contact(met_s): whether met_s is inside one of the run's contact windows. receiver_up(met_s): whether the own
    station's receiver chain works, False through a scripted receiver fault. slant_range_km(met_s): the range from the
    station to the spacecraft, from HUGINN's look angles at that MET."""

    def __init__(self, *, in_contact, receiver_up, slant_range_km):
        self.in_contact, self.receiver_up, self.slant_range_km = in_contact, receiver_up, slant_range_km
        self._status = None   # the receiver's last status, reported or not

    def hears(self, met_s):
        return self.in_contact(met_s) and self.receiver_up(met_s)

    def tick(self, met_s, utc, state, *, pre_roll=False):
        """The reports due at met_s, as feed_report objects, in the order station_receiver then beacon. pre_roll: the
        silent roll to the first contact, when nothing is delivered."""
        heard = self.hears(met_s)
        status = "LOCKED" if heard else "NO_SIGNAL"
        changed, self._status = status != self._status, status
        if pre_roll or not self.in_contact(met_s):
            return []
        reports = []
        if changed or met_s % EVERY_S == 0:
            level = signal_level_dbm(self.slant_range_km(met_s)) if heard else NOISE_FLOOR_DBM
            reports.append({"feed": "station_receiver", "met_s": met_s, "utc": utc,
                            "content": {"status": status, "signal_level_dbm": level}})
        if heard and met_s % EVERY_S == 0:
            reports.append({"feed": "beacon", "met_s": met_s, "utc": utc, "content": beacon_content(state)})
        return reports


# -- other_stations (S9, piece 7) ---------------------------------------------------------------------------------

HEARD_P, DELAY_S = 0.8, (60, 240)


def draw_schedule(seed, beacon_mets, stations):
    """The stand-in stations' logs, by the sealed feed details' rule: for each beacon sent in the own station's
    contact window, in MET order, for each station in turn, random.Random(seed).random() < 0.8, then, if heard,
    randint(60, 240) for its delay. [{station, beacon_met_s, report_met_s}], in the order drawn."""
    draw = random.Random(seed)
    schedule = []
    for beacon_met in sorted(beacon_mets):
        for station in stations:
            if draw.random() < HEARD_P:
                schedule.append({"station": station, "beacon_met_s": beacon_met,
                                 "report_met_s": beacon_met + draw.randint(*DELAY_S)})
    return schedule


class OtherStations:
    """Two stand-in stations under the same pass, labeled modeled: each logs a beacon it hears after its delay, as
    the scenario's sealed schedule sets them, whatever the own station's receiver does. A log reaches ODIN in contact
    only, and one falling out of contact is not held. Its content carries the beacon as it was sent."""

    def __init__(self, schedule, *, in_contact):
        self.schedule, self.in_contact = list(schedule), in_contact
        self._sent = {}   # beacon_met_s: the beacon's content, as it was sent

    def tick(self, met_s, utc, state, *, pre_roll=False):
        if any(row["beacon_met_s"] == met_s for row in self.schedule):
            self._sent[met_s] = beacon_content(state)
        if pre_roll or not self.in_contact(met_s):
            return []
        return [{"feed": "other_stations", "met_s": met_s, "utc": utc,
                 "content": {"station": row["station"], "label": "modeled", "beacon_met_s": row["beacon_met_s"],
                             "beacon": self._sent[row["beacon_met_s"]]}}
                for row in self.schedule if row["report_met_s"] == met_s and row["beacon_met_s"] in self._sent]


# -- space_weather (S9, piece 8) ----------------------------------------------------------------------------------

SPACE_WEATHER_EVERY_S = 300
SOURCES = "GOES-13 via NASA SPDF OMNIWeb Plus; Kp from GFZ Potsdam"


class SpaceWeather:
    """Real space weather, replayed and labeled replayed: the GOES-13 integral proton fluxes and the Kp index of the
    10 September 2017 event, replayed from the flare at the scenario's MET 0 (the sealed replay file's offset_s is the
    MET at which each value is replayed). One report at each MET in contact that is a multiple of 300: the GOES row
    whose offset_s is that MET, and the Kp of the three-hour interval holding it. Out of contact none is held."""

    def __init__(self, replay, *, in_contact):
        self.in_contact = in_contact
        goes, kp = replay["goes"], replay["kp"]
        self._goes = {row[0]: dict(zip(goes["columns"], row)) for row in goes["rows"]}
        self._kp = sorted((dict(zip(kp["columns"], row)) for row in kp["rows"]), key=lambda k: k["offset_s"])

    def tick(self, met_s, utc, state, *, pre_roll=False):
        if pre_roll or met_s % SPACE_WEATHER_EVERY_S or not self.in_contact(met_s) or met_s not in self._goes:
            return []
        goes = self._goes[met_s]
        kp = next((k for k in reversed(self._kp) if k["offset_s"] <= met_s), None)
        return [{"feed": "space_weather", "met_s": met_s, "utc": utc,
                 "content": {"label": "replayed", "utc_2017": goes["utc_2017"],
                             "proton_flux_pfu": {"gt10_mev": goes["gt10_mev"], "gt30_mev": goes["gt30_mev"],
                                                 "gt60_mev": goes["gt60_mev"]},
                             "kp": kp["kp"] if kp else None,
                             "kp_interval_utc_2017": kp["interval_start_utc_2017"] if kp else None,
                             "sources": SOURCES}}]


class Feeds:
    """The run's feeds together, as the harness ticks them: each tick's reports in the order of the feeds given."""

    def __init__(self, *feeds):
        self.feeds = feeds

    def tick(self, met_s, utc, state, *, pre_roll=False):
        return [report for feed in self.feeds for report in feed.tick(met_s, utc, state, pre_roll=pre_roll)]
