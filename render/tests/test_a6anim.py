# SPDX-License-Identifier: GPL-3.0-or-later
"""A6 animate tests: the materials-pass clips, checked frame by frame
against the timeline and their sync files, exactly as for A5.

Same run and span as A5 (dev-ph2-p3-open-01, MET 800-1225, step 5,
10 fps, 960 x 540), rendered into out/a6anim so the A5 clips stay.
Every test has a red case in tests/show_red.py.
Env override for red cases: ANIM_A6ANIM_DIR.
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

ANIM_DIR = Path(os.environ.get("ANIM_A6ANIM_DIR", ROOT / "out" / "a6anim"))
TIMELINE = ROOT / "inputs" / "timelines" / "dev-ph2-p3-open-01.js"
RUN = "dev-ph2-p3-open-01"


def need(path):
    """Skip, with the reason stated, when a needed file is absent
    (the deposit leaves out the inputs' data files and outputs)."""
    if not Path(path).is_file():
        raise unittest.SkipTest(
            "needs %s - inputs/ and out/ are not in the deposit" % path)
    return path


class TestA6AnimClips(unittest.TestCase):
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
            self.assertEqual(report["samples"], 48)
            self.assertEqual(report["fps"], 10)
            self.assertEqual(report["met_range"], [800, 1225])
            self.assertEqual(sync["run_id"], RUN)
            self.assertEqual(sync["timeline_sha256"],
                             Y.timeline_sha256(TIMELINE))
            self.assertEqual(sync["first_frame_met_s"], 800)
            self.assertEqual(sync["met_step_s"], 5)
            self.assertEqual(sync["fps"], 10)
            self.assertEqual(len(report["frames"]), 86)
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
            at900 = [f for f in report["frames"] if f["met_s"] == 900]
            self.assertEqual(len(at900), 1)
            self.assertEqual(at900[0]["load_limit"], "YELLOW_HIGH")
            self.assertTrue(at900[0]["in_contact"])
            self.assertTrue(all(f["weather"] is None
                                for f in report["frames"]))


if __name__ == "__main__":
    unittest.main()
