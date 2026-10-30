"""Phase 3's four outside feeds (CONTRACT.md §6.5): the two core feeds, station_receiver and beacon (S9, piece 2),
built from the simulator's true state and the scenario's script and disclosed as modeled; other_stations (piece 7),
stand-in stations' logs of the beacon, labeled modeled; and space_weather (piece 8), real data replayed and labeled
replayed. Feeds puts them together, in that order within a tick.

Each scenario's own feed details, its sealed `feeds` section, set every rule here: CONTRACT.md §6.5 leaves them to the
approved scenario drafts, and by the Director's ruling of 30 October 2026 each is read from the seal at run time
(harness/phase3.py), so nothing here holds one. The own station's receiver reports LOCKED, with a signal level from the
slant range, while the station hears the spacecraft, and NO_SIGNAL at the noise floor otherwise; a failed receiver
chain shows as NO_SIGNAL, never FAULT. It reports at each change of state and at each MET in contact that is a
multiple of the feeds' cadence. The beacon goes out on the same cadence, through a housekeeping halt too, and is
reported when the own station hears it. Reports reach ODIN in contact only: none in the silent pre-roll, and none held
for a later contact.

Nothing here runs a turn or touches the link: the harness calls tick() once a tick, with what the station hears and
the spacecraft's true state, and delivers what it returns as turn triggers.
"""

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class CoreRules:
    """The core feeds' details, as a scenario's sealed feed details set them (harness/phase3.py reads them)."""
    every_s: int              # the receiver's and the beacon's cadence
    reference_dbm: float      # the signal level at reference_km
    reference_km: float
    db_per_decade: float      # how far it falls in a decade of range
    level_decimals: int       # the signal level's rounding
    noise_floor_dbm: float    # the level reported with NO_SIGNAL
    callsign: str
    battery_v_decimals: int   # the beacon's battery voltage, rounded to so many decimals
    soc_pct_step: int         # its state of charge, to the nearest step


def signal_level_dbm(slant_range_km, rules):
    """The own station's signal level from the spacecraft, by the rules' model."""
    return round(rules.reference_dbm + rules.db_per_decade * math.log10(rules.reference_km / slant_range_km),
                 rules.level_decimals)


def beacon_content(state, rules):
    """The beacon's content from the spacecraft's true state: its callsign, its mode, and its battery voltage and state
    of charge, rounded as the rules say."""
    eps = state["eps"]
    return {"callsign": rules.callsign, "EPS_MODE": eps["mode"],
            "battery_v": round(eps["battery_v"], rules.battery_v_decimals),
            "soc_pct": int(rules.soc_pct_step * round(eps["soc_pct"] / rules.soc_pct_step))}


class CoreFeeds:
    """station_receiver and beacon, tick by tick, for one run.

    in_contact(met_s): whether met_s is inside one of the run's contact windows. receiver_up(met_s): whether the own
    station's receiver chain works, False through a scripted receiver fault. slant_range_km(met_s): the range from the
    station to the spacecraft, from HUGINN's look angles at that MET. rules: the scenario's CoreRules."""

    def __init__(self, *, in_contact, receiver_up, slant_range_km, rules):
        self.in_contact, self.receiver_up, self.slant_range_km = in_contact, receiver_up, slant_range_km
        self.rules = rules
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
        if changed or met_s % self.rules.every_s == 0:
            level = signal_level_dbm(self.slant_range_km(met_s), self.rules) if heard else self.rules.noise_floor_dbm
            reports.append({"feed": "station_receiver", "met_s": met_s, "utc": utc,
                            "content": {"status": status, "signal_level_dbm": level}})
        if heard and met_s % self.rules.every_s == 0:
            reports.append({"feed": "beacon", "met_s": met_s, "utc": utc,
                            "content": beacon_content(state, self.rules)})
        return reports


# -- other_stations (S9, piece 7) ---------------------------------------------------------------------------------

def draw_schedule(seed, beacon_mets, stations, heard_p, delay_s):
    """The stand-in stations' logs, by the sealed feed details' rule, read from the seal (harness/phase3.py): for each
    beacon sent in the own station's contact window, in MET order, for each station in turn,
    random.Random(seed).random() < heard_p, then, if heard, randint(*delay_s) for its delay.
    [{station, beacon_met_s, report_met_s}], in the order drawn."""
    draw = random.Random(seed)
    schedule = []
    for beacon_met in sorted(beacon_mets):
        for station in stations:
            if draw.random() < heard_p:
                schedule.append({"station": station, "beacon_met_s": beacon_met,
                                 "report_met_s": beacon_met + draw.randint(*delay_s)})
    return schedule


class OtherStations:
    """The stand-in stations under the same pass, labeled modeled: each logs a beacon it hears after its delay, as
    the scenario's sealed schedule sets them, whatever the own station's receiver does. A log reaches ODIN in contact
    only, and one falling out of contact is not held. Its content carries the beacon as it was sent, by the core
    feeds' rules."""

    def __init__(self, schedule, *, in_contact, rules):
        self.schedule, self.in_contact, self.rules = list(schedule), in_contact, rules
        self._sent = {}   # beacon_met_s: the beacon's content, as it was sent

    def tick(self, met_s, utc, state, *, pre_roll=False):
        if any(row["beacon_met_s"] == met_s for row in self.schedule):
            self._sent[met_s] = beacon_content(state, self.rules)
        if pre_roll or not self.in_contact(met_s):
            return []
        return [{"feed": "other_stations", "met_s": met_s, "utc": utc,
                 "content": {"station": row["station"], "label": "modeled", "beacon_met_s": row["beacon_met_s"],
                             "beacon": self._sent[row["beacon_met_s"]]}}
                for row in self.schedule if row["report_met_s"] == met_s and row["beacon_met_s"] in self._sent]


# -- space_weather (S9, piece 8) ----------------------------------------------------------------------------------

class SpaceWeather:
    """Real space weather, replayed and labeled replayed, from the scenario's sealed replay file: its GOES integral
    proton fluxes and its Kp index, replayed from the replay's MET 0 (its offset_s is the MET at which each value is
    replayed). One report at each MET in contact that is a multiple of every_s: the GOES row whose offset_s is that
    MET, and the Kp of the interval holding it, each field under the replay's own name for it (its time column, the
    one named utc..., its flux columns, ..._mev, and its Kp interval's start, interval_start_...), with the sources
    the feed details name. every_s and sources come from the sealed feed details (harness/phase3.py). Out of contact
    none is held."""

    def __init__(self, replay, *, every_s, sources, in_contact):
        self.in_contact, self.every_s, self.sources = in_contact, every_s, sources
        goes, kp = replay["goes"], replay["kp"]
        self._goes = {row[0]: dict(zip(goes["columns"], row)) for row in goes["rows"]}
        self._kp = sorted((dict(zip(kp["columns"], row)) for row in kp["rows"]), key=lambda k: k["offset_s"])
        self._time = next(name for name in goes["columns"] if name.startswith("utc"))
        self._fluxes = [name for name in goes["columns"] if name.endswith("_mev")]
        self._interval = next(name for name in kp["columns"] if name.startswith("interval_start_"))

    def tick(self, met_s, utc, state, *, pre_roll=False):
        if pre_roll or met_s % self.every_s or not self.in_contact(met_s) or met_s not in self._goes:
            return []
        goes = self._goes[met_s]
        kp = next((k for k in reversed(self._kp) if k["offset_s"] <= met_s), None)
        interval = "kp_interval_" + self._interval[len("interval_start_"):]
        return [{"feed": "space_weather", "met_s": met_s, "utc": utc,
                 "content": {"label": "replayed", self._time: goes[self._time],
                             "proton_flux_pfu": {name: goes[name] for name in self._fluxes},
                             "kp": kp["kp"] if kp else None,
                             interval: kp[self._interval] if kp else None,
                             "sources": self.sources}}]


class Feeds:
    """The run's feeds together, as the harness ticks them: each tick's reports in the order of the feeds given."""

    def __init__(self, *feeds):
        self.feeds = feeds

    def tick(self, met_s, utc, state, *, pre_roll=False):
        return [report for feed in self.feeds for report in feed.tick(met_s, utc, state, pre_roll=pre_roll)]
