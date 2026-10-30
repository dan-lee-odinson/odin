"""The two core outside feeds, station_receiver and beacon (CONTRACT.md §6.5; S9, piece 2): reports built from the
simulator's true state and the scenario's script, and disclosed as modeled.

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
