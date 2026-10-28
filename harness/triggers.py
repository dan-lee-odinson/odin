"""When ODIN takes a turn (CONTRACT.md §6.1, §16.1 U1).

Only one turn is in flight at a time. Action triggers that arrive while one is in flight, or together,
merge into one action turn. The pass start and the check-in are report triggers: each gets its own
report turn, in the order they arrived, and none is merged or dropped. When action and report triggers
are waiting together, the action turn runs first and the report turn next (ruled 26 October 2026).

A report waits only behind the action triggers that arrived before it or with it, never behind those
that arrived after it (the Director's ruling on U47, 27 October 2026). So a check-in that lands on an
alarm runs right after the alarm's turn, and the follow-up turns for ODIN's own command, its DECISION
and OUTCOME, come after the report. Triggers arrive together when one tick raises them, or one call
adds them.
"""

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field

TYPES = ("AOS", "LOS", "PLAN_START", "LIMIT_CHANGE", "MODE_CHANGE", "STALENESS_CHANGE", "OUTCOME",
         "FEED_REPORT", "DECISION", "CHECK_IN", "REVOKE", "RESTORE", "PERIODIC")
# Each report trigger and the report it makes due (§13, §16.1).
REPORTS = {"PLAN_START": "PASS_START", "CHECK_IN": "CHECK_IN"}
PERIODIC_S = 60


def trigger(type_, met_s, **detail):
    """One trigger as the bundle carries it: {type, met_s, detail}, detail {} for most types."""
    if type_ not in TYPES:
        raise ValueError(f"{type_} is not a trigger type")
    return {"type": type_, "met_s": met_s, "detail": detail}


@dataclass
class Turn:
    turn_kind: str                 # ACT or REPORT
    report_kind: str | None        # on a REPORT turn, the report that is due
    triggers: list
    check_in_text: str | None = None


@dataclass
class _Report:
    report_kind: str
    triggers: list
    check_in_text: str | None = None
    arrival: int = 0


@dataclass
class TriggerQueue:
    _actions: list = field(default_factory=list)    # (arrival, trigger), in the order they arrived
    _reports: list = field(default_factory=list)
    in_flight: Turn | None = None
    latest_met_s: float | None = None   # the newest trigger's, from which PERIODIC counts
    _arrival: int = 0
    _open: int = 0

    def __post_init__(self):
        self.changed = threading.Condition()   # its lock is reentrant, so together() can nest

    @contextmanager
    def together(self):
        """Triggers added inside arrive together: no turn is taken between them, and a report among
        them waits behind the action triggers among them."""
        with self.changed:
            if self._open == 0:
                self._arrival += 1
            self._open += 1
            try:
                yield
            finally:
                self._open -= 1
                self.changed.notify_all()

    def add(self, *triggers, check_in_text=None):
        """Add triggers that arrived together. A report trigger opens a report turn of its own; the
        rest wait for the next action turn."""
        with self.together():
            for one in triggers:
                if one["type"] in REPORTS:
                    self._reports.append(_Report(REPORTS[one["type"]], [one],
                                                 check_in_text if one["type"] == "CHECK_IN" else None,
                                                 self._arrival))
                else:
                    self._actions.append((self._arrival, one))
                self._seen(one)

    def add_report(self, report_kind, one):
        """A report turn for a trigger §6.1 counts among the action triggers: the HAND_BACK report at
        revocation (§9.4, §13)."""
        with self.together():
            self._reports.append(_Report(report_kind, [one], arrival=self._arrival))
            self._seen(one)

    def _seen(self, one):
        self.latest_met_s = one["met_s"] if self.latest_met_s is None else max(self.latest_met_s, one["met_s"])

    # PERIODIC counts 60 s of simulation time from the newest trigger of any kind, a PERIODIC or a report
    # trigger included, whether or not a turn ran (the Director's ruling on U45, 27 October 2026).
    def periodic_due(self, met_s):
        with self.changed:
            return self.latest_met_s is not None and met_s - self.latest_met_s >= PERIODIC_S

    def waiting(self):
        with self.changed:
            return bool(self._actions or self._reports)

    def take(self):
        """The next turn, or None while one is in flight or nothing waits. The action turn comes first
        when an action trigger arrived before the oldest waiting report or with it (§6.1, U47); it takes
        every action trigger waiting, since one turn costs the report no more for holding them all."""
        with self.changed:
            if self.in_flight is not None:
                return None
            oldest = self._reports[0] if self._reports else None
            if self._actions and (oldest is None or self._actions[0][0] <= oldest.arrival):
                self.in_flight = Turn("ACT", None, sorted((one for _, one in self._actions), key=lambda t: t["met_s"]))
                self._actions = []
            elif self._reports:
                report = self._reports.pop(0)
                self.in_flight = Turn("REPORT", report.report_kind, report.triggers, report.check_in_text)
            return self.in_flight

    def finish(self):
        """The turn in flight has ended: ODIN asked for its next turn."""
        with self.changed:
            self.in_flight = None
            self.changed.notify_all()
