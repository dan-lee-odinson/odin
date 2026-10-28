"""What each tick of a run makes happen, as triggers (CONTRACT.md §6.1, §16.1 U1).

The watcher sees the simulation clock, the plan in force, the newest frame the seat received and, in
the ground seat, the staleness monitor's state. It reports acquisition and loss of signal at the run's
contact windows, the start of each plan in the chain, every change in a point's limit state or in
EPS_MODE between one received frame and the next, and every change of the staleness monitor.
Outcomes, decisions, check-ins, revocation and restore come from elsewhere in the harness, and
PERIODIC from the trigger queue's count.
"""

from harness.triggers import trigger
from wrapper.frames import limit_state
from wrapper.link import in_window


class Watcher:
    def __init__(self, windows):
        """windows: the run's contact windows, (aos_met_s, los_met_s), each half-open, taken from its
        verified plan chain (the Director's ruling of 27 October 2026)."""
        self.windows = sorted(windows)
        self.in_contact = None
        self._plan_id = None
        self._limits = None
        self._mode = None
        self._staleness = None

    def tick(self, met_s, *, plan_id, frame=None, staleness=None):
        """The triggers of the tick at met_s, in a fixed order. frame is a frame received since the
        last tick, decoded, or None; staleness the monitor's state, or None in the onboard seat."""
        found = []
        inside = in_window(met_s, self.windows)
        # The run's first tick reports AOS if it starts inside a window, and nothing if outside one.
        if inside != bool(self.in_contact) and (self.in_contact is not None or inside):
            found.append(trigger("AOS" if inside else "LOS", met_s))
        self.in_contact = inside
        if plan_id is not None and plan_id != self._plan_id:
            found.append(trigger("PLAN_START", met_s, plan_id=plan_id))
        self._plan_id = plan_id
        if frame is not None:
            limits = {point: limit_state(point, value) for point, value in frame.items()}
            if self._limits is not None:
                found += [trigger("LIMIT_CHANGE", met_s, point=point, **{"from": self._limits[point], "to": state})
                          for point, state in limits.items() if state != self._limits[point]]
                if frame["EPS_MODE"] != self._mode:
                    found.append(trigger("MODE_CHANGE", met_s, **{"from": self._mode, "to": frame["EPS_MODE"]}))
            self._limits, self._mode = limits, frame["EPS_MODE"]
        if staleness is not None and self._staleness is not None and staleness != self._staleness:
            found.append(trigger("STALENESS_CHANGE", met_s, **{"from": self._staleness, "to": staleness}))
        self._staleness = staleness
        return found
