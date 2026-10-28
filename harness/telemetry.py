"""The frames the seat has received, as the turn bundle and the history call read them (CONTRACT.md §6.2,
§6.4, §8.1, §16.1 U3, §16.5).

In the onboard seat every frame comes from the tap beside the simulator; in the ground seat, from
COSMOS. Each is kept decoded, with when it arrived. The observation is the newest frame's points with
their units and limit states; a history is a table, one row per received frame, of the raw values of
the points asked for, in the dictionary's order.
"""

import threading

from wrapper.frames import POINTS, points

STALE_YELLOW_S, STALE_RED_S = 10, 30


def ground_staleness(last_new_count_met_s, met_s):
    """The ground monitor's state: yellow at 10 s and red at 30 s of simulation time without a new
    CDH_FRAME_CNT (§6.1); red when no frame has ever arrived."""
    if last_new_count_met_s is None:
        return "RED"
    age = met_s - last_new_count_met_s
    return "RED" if age >= STALE_RED_S else "YELLOW" if age >= STALE_YELLOW_S else "GREEN"


class FrameStore:
    def __init__(self, source):
        """source: COSMOS in the ground seat, ONBOARD beside the simulator (§6.4)."""
        self.source = source
        self._lock = threading.Lock()
        self._frames = []   # (frame, received_utc), oldest first
        self._last_new_count = None

    def receive(self, frame, received_utc, met_s):
        """A decoded frame, as it arrived at met_s."""
        with self._lock:
            if not self._frames or frame["CDH_FRAME_CNT"] != self._frames[-1][0]["CDH_FRAME_CNT"]:
                self._last_new_count = met_s
            self._frames.append((frame, received_utc))

    def latest(self):
        with self._lock:
            return self._frames[-1][0] if self._frames else None

    def telemetry(self):
        """The newest frame as BALDUR-0 reads it, {frame_met_s, points}, or None."""
        frame = self.latest()
        return None if frame is None else {"frame_met_s": frame["CDH_MET"], "points": dict(frame)}

    def staleness(self, met_s):
        """The ground monitor's state, or None in the onboard seat, which has no ground monitor (§6.4)."""
        if self.source != "COSMOS":
            return None
        with self._lock:
            return ground_staleness(self._last_new_count, met_s)

    def observation(self, met_s, ground_link=None):
        """§6.4: during an outage there is no new frame and the observation says so; nothing is filled in.
        ground_link: in the ground seat, HUGINN_INT's {state, received_count} as COSMOS reports them, read
        through the connector (S5; the Director's scoring ruling of 28 October 2026, selection 1). The
        onboard seat has no ground link, so it is null there."""
        if (self.source == "COSMOS") != (ground_link is not None):
            raise ValueError("the ground seat's observation carries the ground link, and only the ground seat's")
        with self._lock:
            newest = self._frames[-1] if self._frames else None
        frame, received_utc = newest if newest else (None, None)
        return {"source": self.source,
                "frame_met_s": frame["CDH_MET"] if frame else None,
                "received_utc": received_utc,
                "age_s": met_s - frame["CDH_MET"] if frame else None,
                "staleness_state": self.staleness(met_s),
                "ground_link": ground_link,
                "points": points(frame) if frame else None}

    def history(self, names, met_s, window_s):
        """{columns, rows}: the frames stamped within the last window_s seconds before met_s, met_s
        included, one row each, with the raw values of the named points in the dictionary's order."""
        columns = [name for name in POINTS if name in set(names)]
        with self._lock:
            frames = [frame for frame, _ in self._frames if met_s - window_s < frame["CDH_MET"] <= met_s]
        return {"columns": ["met_s", *columns], "rows": [[f["CDH_MET"], *(f[c] for c in columns)] for f in frames]}
