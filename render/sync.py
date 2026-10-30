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
