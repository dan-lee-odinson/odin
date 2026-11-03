"""The converter's side of the animation pane: a run beside the Director's pass
is two files, the run's own timeline and a beside file, so that the run's file
stays what a clip pins; and each clip and its sync file are placed beside the
timelines and listed in index.js.

The page's side (a clip locked to the playhead, and one rendered from another
timeline file shown nowhere) is in test_page_in_browser.py.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _support as S
import clips
import verda_convert as vc


def index_of(out):
    text = (Path(out) / "index.js").read_text(encoding="utf-8")
    timelines, _, rest = text.partition("window.VERDA_INDEX = ")[2].partition(";\nwindow.VERDA_CLIPS = ")
    return json.loads(timelines), json.loads(rest.rstrip().rstrip(";"))


class BesideFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.alone, cls.paired = Path(cls.tmp.name, "alone"), Path(cls.tmp.name, "paired")
        run = S.runs_dir() / S.PREVIEW_RUN
        vc.convert(run, cls.alone, S.dictionary_path())
        _, cls.timeline = vc.convert(run, cls.paired, S.dictionary_path(), True,
                                     S.passes_dir() / "2026-10-11-P3", S.plans_dir(), S.scripted_path())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_paired_run_is_its_own_timeline_and_a_beside_file(self):
        name = S.PREVIEW_RUN
        self.assertEqual(sorted(p.name for p in self.paired.glob("*.js")),
                         sorted([name + ".js", name + ".beside.js", "index.js"]))
        own = (self.paired / (name + ".js")).read_bytes()
        # The run's own file is byte for byte what the converter makes of the run alone.
        self.assertEqual(own, (self.alone / (name + ".js")).read_bytes())
        _, plain = vc.read_timeline_script(self.paired / (name + ".js"))
        _, beside = vc.read_beside_script(self.paired / (name + ".beside.js"))
        self.assertEqual(beside["run_sha256"], clips.sha256_of(self.paired / (name + ".js")))
        self.assertEqual(vc.with_beside(plain, beside), self.timeline)
        self.assertNotIn("pass", plain["header"])
        self.assertEqual(self.timeline["header"]["pass"]["name"], "2026-10-11-P3")
        entries, _ = index_of(self.paired)
        self.assertEqual(entries[0]["beside"]["file"], name + ".beside.js")
        self.assertEqual(entries[0]["sha256"], beside["run_sha256"])
        self.assertTrue(entries[0]["title"].endswith("beside the Director's pass 2026-10-11-P3"))

    def test_the_preview_pins_the_run_timeline_as_converted(self):
        sync = json.loads((S.clips_dir() / (S.PREVIEW_RUN + "_preview.sync.json")).read_text(encoding="utf-8"))
        self.assertEqual(sync["run_id"], S.PREVIEW_RUN)
        for out in (self.alone, self.paired):
            with self.subTest(out=out.name):
                self.assertEqual(clips.sha256_of(out / (S.PREVIEW_RUN + ".js")), "sha256:" + sync["timeline_sha256"])


class PlacedClips(unittest.TestCase):
    def test_places_each_clip_and_lists_it_in_the_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "out")
            vc.convert(S.runs_dir() / S.PREVIEW_RUN, out, S.dictionary_path())
            placed = list(clips.place_clips(S.clips_dir(), out))
            vc.write_index(out)
            entries, listed = index_of(out)
            copied = {p.name: p.read_bytes() for p in (out / "clips").iterdir()}
        # Every clip in the folder, each with its sync file: the preview and SPARK-R2's two.
        names = [p.name for p in S.clips_dir().glob("*.sync.json")]
        self.assertIn(S.PREVIEW_RUN + "_preview.sync.json", names)
        self.assertEqual({s.name: (p, problems) for s, p, problems in placed},
                         {n: ({"clip": n[:-len(".sync.json")] + ".mp4", "sync": n}, []) for n in names})
        self.assertEqual(len(copied), 2 * len(names))
        for name, data in copied.items():
            self.assertEqual(data, (S.clips_dir() / name).read_bytes(), name)
        sync = json.loads((S.clips_dir() / (S.PREVIEW_RUN + "_preview.sync.json")).read_text(encoding="utf-8"))
        self.assertEqual(len(listed), len(names))
        entry = next(e for e in listed if e["run_id"] == S.PREVIEW_RUN)
        self.assertEqual({k: entry[k] for k in ("run_id", "first_frame_met_s", "met_step_s", "fps")},
                         {k: sync[k] for k in ("run_id", "first_frame_met_s", "met_step_s", "fps")})
        self.assertEqual(entry["timeline_sha256"], "sha256:" + sync["timeline_sha256"])
        self.assertEqual(entry["timeline_sha256"], entries[0]["sha256"])
        self.assertEqual((entry["file"], entry["problems"]), ("clips/%s_preview.mp4" % S.PREVIEW_RUN, []))
        self.assertEqual(entry["clip_sha256"], clips.sha256_of(S.clips_dir() / (S.PREVIEW_RUN + "_preview.mp4")))
        self.assertIsNone(entry["caption"])

    def test_a_clips_caption_goes_with_it_into_the_index(self):
        name = S.PREVIEW_RUN + "_preview"
        caption = "A clip's caption, as its renderer wrote it — a dash and all."
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp, "clips"), Path(tmp, "out")
            source.mkdir()
            for ext in (".mp4", ".sync.json"):
                shutil.copy(S.clips_dir() / (name + ext), source / (name + ext))
            (source / (name + clips.CAPTION)).write_bytes(caption.encode("utf-8"))
            vc.convert(S.runs_dir() / S.PREVIEW_RUN, out, S.dictionary_path())
            placed = [p for _, p, problems in clips.place_clips(source, out)]
            vc.write_index(out)
            _, listed = index_of(out)
            copied = (out / "clips" / (name + clips.CAPTION)).read_bytes()
        self.assertEqual(placed, [{"clip": name + ".mp4", "sync": name + ".sync.json", "caption": name + clips.CAPTION}])
        self.assertEqual(copied, caption.encode("utf-8"))
        self.assertEqual([c["caption"] for c in listed], [caption])

    def test_a_sync_file_with_no_clip_or_a_bad_field_is_not_placed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "clips")
            source.mkdir()
            good = json.loads((S.clips_dir() / (S.PREVIEW_RUN + "_preview.sync.json")).read_text(encoding="utf-8"))
            (source / "lonely.sync.json").write_text(json.dumps(good), encoding="utf-8")
            (source / "badfps.sync.json").write_text(json.dumps(dict(good, fps=0)), encoding="utf-8")
            shutil.copy(S.clips_dir() / (S.PREVIEW_RUN + "_preview.mp4"), source / "badfps.mp4")
            placed = {s.name: problems for s, p, problems in clips.place_clips(source, Path(tmp, "out"))}
            self.assertFalse(Path(tmp, "out", "clips").exists())
        self.assertEqual(placed["lonely.sync.json"], ["lonely.sync.json: no clip beside it"])
        self.assertEqual(placed["badfps.sync.json"], ["badfps.sync.json: fps is not above 0"])


if __name__ == "__main__":
    unittest.main()
