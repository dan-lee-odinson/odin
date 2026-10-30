# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a VERDA timeline and giving the scene state at one MET (A2).

Pure Python, so the tests can check known moments against the timeline's
own values. The timeline format is defined in
``inputs/timeline-format/VERDA-README.md``: one JS assignment of one JSON
object; telemetry in ``series`` by ``<source>:<point>`` with samples
``[met_s, value, limit_state, provenance]``; contact as spans on the
``contact`` lane; ODIN's requests with BALDUR-0's decisions in ``requests``.

Choices, stated:
- Spacecraft state reads the ``truth`` source when a point has one (the
  simulator's own state), else ``odin``. Both name the same points.
- Before a series' first sample there is no value, and the state says so
  (None): the animation shows nothing for it (the brief, rule 2). The P3
  timelines' telemetry starts at contact, MET 800.
- Space weather is read only from a feed file of reports (the contract's
  form: feed, met_s, utc, content). A run whose record carries no feed
  gets weather None at every MET (the brief, rule 3).
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
P3_ORBIT_CSV = ROOT / "inputs" / "orbit" / "P3-orbit.csv"


def load_timeline(path):
    """Load a VERDA timeline (.js wrapper or plain JSON) as a dict."""
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        return json.loads(text)
    start = text.index("= {") + 2
    return json.loads(text[start:].rstrip().rstrip(";"))


def sample_at(samples, met_s):
    """The last sample at or before a MET, or None before the first."""
    chosen = None
    for sample in samples:
        if sample[0] <= met_s:
            chosen = sample
        else:
            break
    return chosen


def series_samples(timeline, point):
    """Samples for one telemetry point, truth source preferred."""
    series = timeline.get("series", {})
    for source in ("truth", "odin"):
        entry = series.get("%s:%s" % (source, point))
        if entry:
            return entry.get("samples", [])
    return []


def point_at(timeline, point, met_s):
    """(value, limit_state) at a MET, or (None, None) with no sample yet."""
    sample = sample_at(series_samples(timeline, point), met_s)
    if sample is None:
        return None, None
    return sample[1], sample[2]


def contact_spans(timeline):
    """Recorded contact spans (the plan's window, severity planned, is not)."""
    return [(span["start"], span["end"]) for span in timeline.get("spans", [])
            if span.get("lane") == "contact"
            and span.get("severity") != "planned"]


def load_feed(path):
    """Space-weather reports from a feed file, or [] when there is none."""
    if path is None:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [r for r in data.get("reports", []) if r.get("feed") == "space_weather"]


def weather_at(reports, met_s):
    """The last space-weather report's content at a MET, or None."""
    weather = None
    for report in reports:
        if report.get("met_s", 0) <= met_s:
            weather = report.get("content")
    return weather


def state_at(timeline, met_s, feed_reports=()):
    """Everything the A2 scene shows, as the record has it at one MET."""
    eclipse, _ = point_at(timeline, "ADM_ECLIPSE", met_s)
    mode, mode_limit = point_at(timeline, "EPS_MODE", met_s)
    payload, _ = point_at(timeline, "PLD_STATE", met_s)
    load_i, load_limit = point_at(timeline, "EPS_LOAD_I", met_s)
    sa1_i, _ = point_at(timeline, "EPS_SA1_I", met_s)
    sa2_i, _ = point_at(timeline, "EPS_SA2_I", met_s)
    return {
        "met_s": met_s,
        "sunlit": None if eclipse is None else eclipse == "SUNLIT",
        "mode": mode,
        "mode_limit": mode_limit,
        "payload_on": None if payload is None else payload == "ON",
        "load_i": load_i,
        "load_limit": load_limit,
        "sa1_i": sa1_i,
        "sa2_i": sa2_i,
        "in_contact": any(start <= met_s <= end
                          for start, end in contact_spans(timeline)),
        "weather": weather_at(feed_reports, met_s),
    }


def request_cues(timeline):
    """ODIN acts and BALDUR-0 decides: cue dicts in MET order."""
    cues = []
    for request in timeline.get("requests", []):
        if request.get("met_s") is not None:
            cues.append({"met_s": request["met_s"], "kind": "odin",
                         "command": request.get("command")})
        if request.get("decision_met_s") is not None:
            cues.append({"met_s": request["decision_met_s"], "kind": "baldur",
                         "decision": request.get("decision")})
        if request.get("dispatch_met_s") is not None:
            cues.append({"met_s": request["dispatch_met_s"], "kind": "dispatch",
                         "command": request.get("command")})
    return sorted(cues, key=lambda cue: cue["met_s"])


def telemetry_span(timeline):
    """(first, last) MET with ADM_ECLIPSE samples, or (None, None)."""
    samples = series_samples(timeline, "ADM_ECLIPSE")
    if not samples:
        return None, None
    return samples[0][0], samples[-1][0]


def orbit_path_for(run_id):
    """The orbit file supplying a run's position, or None when it has none.

    The two phase-2 PASS-3 runs share inputs/orbit/P3-orbit.csv. Phase 1's
    R4 flew COSMOS's demo target, which has no orbit, so it gets no orbit
    animation (inputs/orbit/README.md).
    """
    if run_id.startswith("dev-ph2-p3-"):
        return P3_ORBIT_CSV
    return None  # no orbit on record for this run
