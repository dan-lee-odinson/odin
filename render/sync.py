# SPDX-License-Identifier: GPL-3.0-or-later
"""A3: the sync file written beside each clip.

One small JSON with the run's ID, the timeline's SHA-256 (of the timeline
file's bytes), the MET of the first frame, the MET step per frame, and the
frame rate. VERDA's pane reads it to stay on its playhead: frame i
(1-based, as Blender numbers frames) is at
MET = first_frame_met_s + (i - 1) * met_step_s.
"""

import hashlib
import json
from fractions import Fraction
from pathlib import Path


def timeline_sha256(path):
    """SHA-256 of a timeline file's bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_sync(run_id, timeline_path, first_frame_met_s, met_step_s, fps):
    """The sync dict, exactly the fields the brief's A3 names."""
    return {
        "run_id": run_id,
        "timeline_sha256": timeline_sha256(timeline_path),
        "first_frame_met_s": first_frame_met_s,
        "met_step_s": met_step_s,
        "fps": fps,
    }


def write_sync(path, sync):
    Path(path).write_text(json.dumps(sync, indent=2) + "\n", encoding="utf-8")


def read_sync(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def frame_met(sync, frame_index):
    """MET of a 1-based frame index under a sync dict."""
    return sync["first_frame_met_s"] + (frame_index - 1) * sync["met_step_s"]


def to_fraction(value):
    """An exact Fraction for an int, a Fraction, or text like "1/15".

    Text is read exactly as written: "1/15" stays a fifteenth, never a
    rounded decimal. Floats are refused for steps and METs, because a
    float has already lost the exact value before it gets here."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        return Fraction(value.strip())
    raise ValueError("expected an int or exact fraction text, got %r"
                     % (value,))


def parse_met_step(value):
    """A positive exact MET step (a fifteenth of a second is fine)."""
    step = to_fraction(value)
    if step <= 0:
        raise ValueError("MET step must be positive, got %r" % (value,))
    return step


def step_text(value):
    """Canonical command-line text: "5" for whole steps, "1/15" else."""
    frac = to_fraction(value)
    if frac.denominator == 1:
        return str(frac.numerator)
    return "%d/%d" % (frac.numerator, frac.denominator)


def sync_number(value):
    """The JSON number for an exact MET or step.

    Whole values stay ints, so whole-second steps write the same sync
    files as before A8; a fraction becomes the nearest float, which
    VERDA reads as a number."""
    frac = to_fraction(value)
    return frac.numerator if frac.denominator == 1 else float(frac)


def frame_mets(start_met, end_met, step):
    """The exact MET of every frame from start to end at step.

    Frame i (0-based here) sits at start + i * step, each computed
    from the exact fraction, so a 1/15 s step lands every frame on
    its fifteenth with no accumulated rounding."""
    start = to_fraction(start_met)
    end = to_fraction(end_met)
    step = parse_met_step(step)
    if end < start:
        raise ValueError("MET end %s is before start %s"
                         % (step_text(end), step_text(start)))
    count = int((end - start) // step) + 1
    return [start + i * step for i in range(count)]


def pullback_progress(met, span_start, span_end):
    """Pull-back progress (0 to 1) of one MET within its full span.

    Measured against the whole pull-back span, never the rendered
    subrange: a probe renders a span's first frames, and those frames
    must sit at the start of the move, not spread the whole move
    across however many frames happen to be rendered (A9B)."""
    start, end = to_fraction(span_start), to_fraction(span_end)
    if end <= start:
        raise ValueError("pull-back span end must follow its start")
    progress = (to_fraction(met) - start) / (end - start)
    return float(min(Fraction(1), max(Fraction(0), progress)))
