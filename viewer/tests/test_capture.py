"""The capture tool's own checks (capture/verda_capture.py), without filming: its seek
lives in its own copy of the page and nowhere else, a shot runs from its first MET to
its last, it names each clip frame as the page does, and it never films a clip
pinned to another timeline file.
"""

import argparse
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _support as S
import verda_capture as cap

FOOTAGE = "PH2-PASS3-SPARK-R2_instrument_footage"


class CaptureTool(unittest.TestCase):
    def test_the_seek_is_the_capture_tools_own(self):
        js = (S.page_dir() / "verda.js").read_text(encoding="utf-8")
        self.assertNotIn("VERDA_SEEK", js)
        self.assertEqual(js.count(cap.SEEK_ANCHOR), 1)
        with tempfile.TemporaryDirectory() as tmp:
            copy = cap.copy_page(Path(tmp, "page"))
            copied = (copy / "verda.js").read_text(encoding="utf-8")
        self.assertEqual(copied.count("window.VERDA_SEEK = function (met) {"), 1)
        self.assertEqual(copied.replace(cap.SEEK_HOOK, ""), js)

    def test_a_moving_shot_runs_from_its_first_met_to_its_last(self):
        shot = argparse.Namespace(hold=None, start=880.0, to=1000.0, speed=2.0, fps=30)
        mets = cap.frame_mets(shot)
        self.assertEqual((len(mets), mets[0], mets[435], mets[-1]), (1801, 880.0, 909.0, 1000.0))
        with self.assertRaises(cap.CaptureError):
            cap.frame_mets(argparse.Namespace(hold=None, start=880.0, to=1000.05, speed=2.0, fps=30))
        held = cap.frame_mets(argparse.Namespace(hold=1158.0, seconds=12.0, fps=30))
        self.assertEqual((len(held), set(held)), (360, {1158.0}))

    def test_the_capture_names_each_clip_frame_as_the_page_does(self):
        sync = json.loads((S.clips_dir() / (FOOTAGE + ".sync.json")).read_text(encoding="utf-8"))
        shot = argparse.Namespace(hold=None, start=880.0, to=1000.0, speed=2.0, fps=30)
        self.assertEqual([cap.clip_frame(sync, 1801, met) for met in cap.frame_mets(shot)], list(range(1801)))
        self.assertEqual((cap.clip_frame(sync, 1801, 870.0), cap.clip_frame(sync, 1801, 1010.0)), (0, 1800))

    def test_a_clip_pinned_to_another_timeline_is_not_filmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "clip")
            source.mkdir()
            shutil.copyfile(S.clips_dir() / (FOOTAGE + ".mp4"), source / (FOOTAGE + ".mp4"))
            sync = json.loads((S.clips_dir() / (FOOTAGE + ".sync.json")).read_text(encoding="utf-8"))
            sync["timeline_sha256"] = sync["timeline_sha256"][:-1] + ("0" if sync["timeline_sha256"][-1] != "0" else "1")
            (source / (FOOTAGE + ".sync.json")).write_text(json.dumps(sync), encoding="utf-8")
            shot = argparse.Namespace(run=str(S.runs_dir() / "PH2-PASS3-SPARK-R2"), passes=str(S.passes_dir()),
                                      plans=str(S.plans_dir()), scripted=str(S.scripted_path()),
                                      dictionary=str(S.dictionary_path()), clip=str(source / (FOOTAGE + ".sync.json")),
                                      expect_timeline=None)
            work = Path(tmp, "work")
            work.mkdir()
            with self.assertRaises(cap.CaptureError) as caught:
                cap.build_page(shot, work)
        self.assertIn("the clip pins PH2-PASS3-SPARK-R2 sha256:" + sync["timeline_sha256"], str(caught.exception))


if __name__ == "__main__":
    unittest.main()
