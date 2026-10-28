"""The frames the seat has received, as the turn bundle and the history call read them (CONTRACT.md §6.2,
§6.4, §8.1, §16.1 U3, §16.5).

In the onboard seat every frame comes from the tap beside the simulator; in the ground seat, from
COSMOS. Each is kept decoded, with when it arrived. The observation is the newest frame's points with
their units and limit states; a history is a table, one row per received frame, of the raw values of
the points asked for, in the dictionary's order.

A view says how to read one dictionary's frames. HUGINN's frame carries its own time, CDH_MET, and its
counter, CDH_FRAME_CNT, and its limit states follow from the dictionary (U7). In phase 1, COSMOS's demo target
simulates itself inside COSMOS: an INST HEALTH_STATUS packet's time is the run's MET when the harness read it,
its counter COSMOS's RECEIVED_COUNT, and its limit states COSMOS's own (the Director's ruling on U58, 28
October 2026).
"""

import threading

from wrapper.frames import POINTS, limit_state, points

STALE_YELLOW_S, STALE_RED_S = 10, 30


def ground_staleness(last_new_count_met_s, met_s):
    """The ground monitor's state: yellow at 10 s and red at 30 s of simulation time without a new
    CDH_FRAME_CNT (§6.1); red when no frame has ever arrived."""
    if last_new_count_met_s is None:
        return "RED"
    age = met_s - last_new_count_met_s
    return "RED" if age >= STALE_RED_S else "YELLOW" if age >= STALE_YELLOW_S else "GREEN"


class HuginnView:
    names = tuple(POINTS)
    mode = "EPS_MODE"

    def entry(self, frame, received_utc, met_s, count=None, limits=None):
        return {"frame": frame, "received_utc": received_utc, "met_s": frame["CDH_MET"],
                "count": frame["CDH_FRAME_CNT"], "limits": {p: limit_state(p, v) for p, v in frame.items()}}

    def describe(self, entry):
        return points(entry["frame"])


class InstView:
    mode = None

    def __init__(self, dictionary):
        group = dictionary["telemetry_groups"][0]
        self.names = tuple(point["mnemonic"] for point in group["points"])
        self._units = {point["mnemonic"]: point["units"] for point in group["points"]}

    def entry(self, frame, received_utc, met_s, count=None, limits=None):
        return {"frame": frame, "received_utc": received_utc, "met_s": met_s, "count": count, "limits": limits}

    def describe(self, entry):
        return {name: {"value": entry["frame"][name], "units": self._units[name], "limit_state": entry["limits"][name]}
                for name in self.names}


HUGINN = HuginnView()


class FrameStore:
    def __init__(self, source, view=HUGINN):
        """source: COSMOS in the ground seat, ONBOARD beside the simulator (§6.4). view: the dictionary's."""
        self.source = source
        self.view = view
        self._lock = threading.Lock()
        self._frames = []   # entries, oldest first
        self._last_new_count = None

    def receive(self, frame, received_utc, met_s, *, count=None, limits=None):
        """A decoded frame, as it arrived at met_s; for INST, with COSMOS's count and limit states."""
        entry = self.view.entry(frame, received_utc, met_s, count, limits)
        with self._lock:
            if not self._frames or entry["count"] != self._frames[-1]["count"]:
                self._last_new_count = met_s
            self._frames.append(entry)

    def frames(self):
        """Every frame received, oldest first."""
        with self._lock:
            return [entry["frame"] for entry in self._frames]

    def latest(self):
        with self._lock:
            return self._frames[-1]["frame"] if self._frames else None

    def latest_limits(self):
        with self._lock:
            return self._frames[-1]["limits"] if self._frames else None

    def telemetry(self):
        """The newest frame as BALDUR-0 reads it, {frame_met_s, points}, or None."""
        with self._lock:
            newest = self._frames[-1] if self._frames else None
        return None if newest is None else {"frame_met_s": newest["met_s"], "points": dict(newest["frame"])}

    def staleness(self, met_s):
        """The ground monitor's state, or None in the onboard seat, which has no ground monitor (§6.4)."""
        if self.source != "COSMOS":
            return None
        with self._lock:
            return ground_staleness(self._last_new_count, met_s)

    def observation(self, met_s, ground_link=None):
        """§6.4: during an outage there is no new frame and the observation says so; nothing is filled in.
        ground_link: in the ground seat, the seat's interface's {state, received_count} as COSMOS reports them,
        read through the connector (S5; the Director's scoring ruling of 28 October 2026, selection 1). The
        onboard seat has no ground link, so it is null there."""
        if (self.source == "COSMOS") != (ground_link is not None):
            raise ValueError("the ground seat's observation carries the ground link, and only the ground seat's")
        with self._lock:
            newest = self._frames[-1] if self._frames else None
        return {"source": self.source,
                "frame_met_s": newest["met_s"] if newest else None,
                "received_utc": newest["received_utc"] if newest else None,
                "age_s": met_s - newest["met_s"] if newest else None,
                "staleness_state": self.staleness(met_s),
                "ground_link": ground_link,
                "points": self.view.describe(newest) if newest else None}

    def history(self, names, met_s, window_s):
        """{columns, rows}: the frames stamped within the last window_s seconds before met_s, met_s
        included, one row each, with the raw values of the named points in the dictionary's order."""
        columns = [name for name in self.view.names if name in set(names)]
        with self._lock:
            entries = [e for e in self._frames if met_s - window_s < e["met_s"] <= met_s]
        return {"columns": ["met_s", *columns], "rows": [[e["met_s"], *(e["frame"][c] for c in columns)] for e in entries]}
