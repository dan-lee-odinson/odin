# SPDX-License-Identifier: GPL-3.0-or-later
"""A5 animate tests: the true-scale clips, their sync files, and the
record state carried in each frame of the animate reports.

The clips are dev-ph2-p3-open-01 rendered through render_clip.py at
960 x 540 (no scored PASS3 timeline is in inputs; the Director's
fallback names this run). Every test has a red case in
tests/show_red.py. Env override for red cases: ANIM_A5ANIM_DIR.
"""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sync as Y  # noqa: E402
import timeline as T  # noqa: E402

ANIM_DIR = Path(os.environ.get("ANIM_A5ANIM_DIR", ROOT / "out" / "a5anim"))
TIMELINE = ROOT / "inputs" / "timelines" / "dev-ph2-p3-open-01.js"
RUN = "dev-ph2-p3-open-01"


def need(path):
    """Skip, with the reason stated, when a needed file is absent
    (the deposit leaves out the inputs' data files and outputs)."""
    if not Path(path).is_file():
        raise unittest.SkipTest(
            "needs %s - inputs/ and out/ are not in the deposit" % path)
    return path


class TestA5AnimClips(unittest.TestCase):
    def test_clips_syncs_and_frames(self):
        timeline = T.load_timeline(need(TIMELINE))
        need(ANIM_DIR / ("%s_a5_clean.mp4" % RUN))
        for cut in ("instrument", "clean"):
            clip = ANIM_DIR / ("%s_a5_%s.mp4" % (RUN, cut))
            self.assertTrue(clip.is_file(), "missing clip %s" % clip.name)
            self.assertGreater(clip.stat().st_size, 50000, clip.name)
            sync = Y.read_sync(ANIM_DIR / ("%s_a5_%s.sync.json" % (RUN, cut)))
            report = json.loads(
                (ANIM_DIR / ("%s_a5_%s_report.json" % (RUN, cut)))
                .read_text(encoding="utf-8"))
            self.assertEqual(report["cut"], cut)
            self.assertEqual(report["resolution"], [960, 540])
            self.assertEqual(report["fps"], 10)
            self.assertEqual(sync["run_id"], RUN)
            self.assertEqual(sync["timeline_sha256"],
                             Y.timeline_sha256(TIMELINE))
            self.assertEqual(sync["first_frame_met_s"],
                             report["met_range"][0])
            self.assertEqual(sync["fps"], 10)
            self.assertGreaterEqual(len(report["frames"]), 80)
            # Every frame's MET follows the sync file, and every frame's
            # recorded state is the timeline's own state at that MET.
            for frame in report["frames"]:
                self.assertEqual(Y.frame_met(sync, frame["frame"]),
                                 frame["met_s"])
                state = T.state_at(timeline, frame["met_s"])
                for key in ("sunlit", "mode", "payload_on", "load_i",
                            "load_limit", "in_contact"):
                    self.assertEqual(
                        frame[key], state[key],
                        "%s frame %d %s: report %r, record %r"
                        % (cut, frame["frame"], key, frame[key], state[key]))
            # Known moment: at MET 900 the load limit is YELLOW_HIGH and
            # the run is in contact (the stills' moment).
            at900 = [f for f in report["frames"] if f["met_s"] == 900]
            self.assertEqual(len(at900), 1)
            self.assertEqual(at900[0]["load_limit"], "YELLOW_HIGH")
            self.assertTrue(at900[0]["in_contact"])
            # No feed in this run's record, so no space weather anywhere.
            self.assertTrue(all(f["weather"] is None
                                for f in report["frames"]))


if __name__ == "__main__":
    unittest.main()
