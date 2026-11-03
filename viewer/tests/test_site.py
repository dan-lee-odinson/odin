"""The replay site, built as the repository's workflow builds it (site/build_site.py),
from VERDA's inputs in place of the committed records; then read as GitHub Pages
serves it, over HTTP, and from disk, in headless Chrome or Edge.

Each refusal of the build is shown at work: a run missing from the records, a clip
the site does not carry, a clip pinned to another timeline file, SPARK-R2's timeline
in other bytes, a run whose check fails, and a site folder that already exists.
"""

import argparse
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _support as S
import browser_probe
import build_site
import clips
from test_clips import index_of
from test_page_in_browser import CLIP_STATE, SCRUB_TO

SPARK_R2 = "PH2-PASS3-SPARK-R2"
SITE_CLIP = "PH2-PASS3-SPARK-R2_instrument_site"
FOOTAGE_CLIP = "PH2-PASS3-SPARK-R2_instrument_footage"
# The file the animation session rendered SPARK-R2's clips from (VERDA's out/for-render/).
STAGE_ONE = "d0f1a57349d60cbee5835f3bac6a945e02762ecf49387ebca6caa968d12fe617"
# Phase 3's scenarios A and D, each flown five times by each model.
PHASE3_SITE_RUNS = tuple("PH3-%s-%s-R%d" % (s, a, n) for s in ("H02", "H04") for a in ("SPARK", "OPEN") for n in range(1, 6))

_built = {}


def build_args(out, clip_names=(SITE_CLIP,), runs=None):
    return argparse.Namespace(runs=str(runs or S.runs_dir()), passes=str(S.passes_dir()), plans=str(S.plans_dir()),
                              scripted=str(S.scripted_path()), dictionary=str(S.dictionary_path()),
                              clip=[str(S.clips_dir() / (n + ".sync.json")) for n in clip_names], out=str(out))


def built_site():
    """The site, built once for the module."""
    if not _built:
        tmp = tempfile.TemporaryDirectory()
        out = Path(tmp.name, "site")
        result = build_site.build(build_args(out))
        _built.update(tmp=tmp, out=out, result=result)
    return _built


def tearDownModule():
    if _built:
        _built["tmp"].cleanup()


class SiteBuild(unittest.TestCase):
    def site(self):
        """The site's folder; a site that will not build fails the test."""
        try:
            return built_site()["out"]
        except build_site.SiteError as exc:
            self.fail("the site was not built: %s" % exc)

    def test_the_site_holds_exactly_its_runs_and_the_page_as_it_is(self):
        out = self.site()
        entries, _ = index_of(out / "timelines")
        self.assertEqual(sorted(e["id"] for e in entries), sorted(S.SCORED_RUNS + PHASE3_SITE_RUNS))
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["fonts", "index.html", "timelines", "verda.css", "verda.js"])
        for name in ("index.html", "verda.js", "verda.css"):
            self.assertEqual((out / name).read_bytes(), (S.page_dir() / name).read_bytes(), name)

    def test_each_phase_2_run_is_beside_its_pass_and_each_phase_3_run_alone(self):
        entries, _ = index_of(self.site() / "timelines")
        for e in entries:
            with self.subTest(run=e["id"]):
                if e["id"].startswith("PH2-"):
                    self.assertEqual((e.get("beside") or {}).get("pass"), S.PASS_OF[e["id"].split("-")[1]])
                else:
                    self.assertNotIn("beside", e)

    def test_spark_r2_carries_the_site_clip_and_no_other(self):
        out = self.site() / "timelines"
        _, listed = index_of(out)
        self.assertEqual([(c["run_id"], c["file"], c["problems"]) for c in listed], [(SPARK_R2, "clips/%s.mp4" % SITE_CLIP, [])])
        self.assertEqual(sorted(p.name for p in (out / "clips").iterdir()),
                         [SITE_CLIP + ".caption.txt", SITE_CLIP + ".mp4", SITE_CLIP + ".sync.json"])
        self.assertEqual(listed[0]["timeline_sha256"], clips.sha256_of(out / (SPARK_R2 + ".js")))

    def test_spark_r2_is_the_file_its_clips_were_rendered_from(self):
        self.assertEqual(clips.sha256_of(self.site() / "timelines" / (SPARK_R2 + ".js")), "sha256:" + STAGE_ONE)


class SiteRefusals(unittest.TestCase):
    def test_a_run_missing_from_the_records_stops_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp, "runs")
            runs.mkdir()
            with self.assertRaises(build_site.SiteError) as caught:
                build_site.build(build_args(Path(tmp, "site"), runs=runs))
            self.assertFalse(Path(tmp, "site").exists())
        self.assertTrue(str(caught.exception).startswith("missing from "), caught.exception)
        self.assertIn("PH3-H04-SPARK-R1", str(caught.exception))

    def test_a_clip_the_site_does_not_carry_is_refused(self):
        for names, says in (((SITE_CLIP, FOOTAGE_CLIP), FOOTAGE_CLIP + ".sync.json is not a clip the site carries"),
                            ((), "no clip given for " + SPARK_R2)):
            with self.subTest(clips=names), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(build_site.SiteError) as caught:
                    build_site.build(build_args(Path(tmp, "site"), clip_names=names))
                self.assertTrue(str(caught.exception).startswith(says), caught.exception)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_a_clip_pinned_to_another_timeline_stops_the_build(self):
        built = built_site()["out"] / "timelines"
        with tempfile.TemporaryDirectory() as tmp:
            timelines, source = Path(tmp, "timelines"), Path(tmp, "clips")
            timelines.mkdir()
            source.mkdir()
            shutil.copyfile(built / (SPARK_R2 + ".js"), timelines / (SPARK_R2 + ".js"))
            shutil.copyfile(S.clips_dir() / (SITE_CLIP + ".mp4"), source / (SITE_CLIP + ".mp4"))
            sync = json.loads((S.clips_dir() / (SITE_CLIP + ".sync.json")).read_text(encoding="utf-8"))
            self.assertEqual(len(build_site.check_clips(built)), 1)
            # One hex digit of the pinned hash changed: a clip rendered from another timeline file.
            sync["timeline_sha256"] = sync["timeline_sha256"][:-1] + ("0" if sync["timeline_sha256"][-1] != "0" else "1")
            (source / (SITE_CLIP + ".sync.json")).write_text(json.dumps(sync), encoding="utf-8")
            list(clips.place_clips(source, timelines))
            with self.assertRaises(build_site.SiteError) as caught:
                build_site.check_clips(timelines)
        self.assertIn("pins sha256:" + sync["timeline_sha256"], str(caught.exception))

    def test_spark_r2_in_other_bytes_stops_the_build(self):
        built = built_site()["out"] / "timelines"
        build_site.check_pins(built)
        with tempfile.TemporaryDirectory() as tmp:
            data = (built / (SPARK_R2 + ".js")).read_bytes()
            Path(tmp, SPARK_R2 + ".js").write_bytes(data.replace(b'"title": "PH2-PASS3-SPARK-R2"', b'"title": "PH2-PASS3-SPARK-R2 "', 1))
            with self.assertRaises(build_site.SiteError) as caught:
                build_site.check_pins(tmp)
        self.assertIn("not the %s its clips were rendered from" % STAGE_ONE, str(caught.exception))

    def test_a_run_whose_check_fails_or_that_left_a_file_unread_stops_the_build(self):
        good = {"integrity": [{"label": "Event log", "chain": "VERIFIED", "ok": True}], "warnings": []}
        build_site.check_timeline("good", good)
        broken = {"integrity": [{"label": "Event log", "chain": "BROKEN", "ok": False}], "warnings": []}
        unread = dict(good, warnings=["notes.jsonl was not read"])
        for name, timeline in (("broken", broken), ("unread", unread)):
            with self.subTest(timeline=name), self.assertRaises(build_site.SiteError):
                build_site.check_timeline(name, timeline)

    def test_the_build_never_writes_into_a_folder_that_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(build_site.SiteError) as caught:
                build_site.build(build_args(Path(tmp)))
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertIn("never overwrites", str(caught.exception))


class SiteInBrowser(unittest.TestCase):
    """The page works, and the clip plays, served as GitHub Pages serves it and opened from disk."""

    @classmethod
    def setUpClass(cls):
        cls.out = built_site()["out"]
        cls.page = browser_probe.Page()

    @classmethod
    def tearDownClass(cls):
        cls.page.close()

    def read_site(self, url_of, own):
        page = self.page
        page.open("about:blank", settle=0.3)
        page.requests, page.errors = [], []
        page.open(url_of(SPARK_R2, "&met=1000"), settle=2.0)
        found = {"at": page.evaluate(CLIP_STATE),
                 "drawn": page.evaluate("({lanes: document.querySelectorAll('.lane-label').length,"
                                        " title: document.getElementById('title').textContent})")}
        page.evaluate("(() => { const s = document.getElementById('speed'); s.value = '10'; s.dispatchEvent(new Event('change'));"
                      " document.getElementById('btn-play').click(); })()")
        page.wait(1.0)
        found["playing"] = page.evaluate("({paused: document.getElementById('clip').paused,"
                                         " rate: document.getElementById('clip').playbackRate,"
                                         " time: document.getElementById('clip').currentTime})")
        page.evaluate("document.getElementById('btn-play').click()")
        found["stopped"] = page.evaluate(CLIP_STATE)
        page.open("about:blank", settle=0.3)
        page.open(url_of("PH3-H04-SPARK-R1", "&met=7300"), settle=1.5)
        found["d"] = page.evaluate("({title: document.getElementById('title').textContent,"
                                   " pane: document.getElementById('clip-panel').getClientRects().length})")
        found["errors"], found["asked"] = list(page.errors), list(page.requests)
        self.assertEqual(found["errors"], [])
        self.assertTrue(found["at"]["note"].startswith("Frame 201 of 426, MET 1000"), found["at"]["note"])
        self.assertTrue(found["at"]["src"].endswith("/timelines/clips/%s.mp4" % SITE_CLIP), found["at"]["src"])
        self.assertTrue(found["drawn"]["title"].startswith(SPARK_R2 + " beside the Director's pass"))
        self.assertGreater(found["drawn"]["lanes"], 10)
        # At 10x, ten seconds of MET a second: the clip plays itself at 10 / (30 x 1) of its pace.
        self.assertFalse(found["playing"]["paused"])
        self.assertAlmostEqual(found["playing"]["rate"], 1 / 3, places=3)
        self.assertGreater(found["playing"]["time"], 200 / 30)
        self.assertTrue(found["stopped"]["paused"] and found["stopped"]["note"].startswith("Frame "), found["stopped"])
        self.assertTrue(found["d"]["title"].startswith("PH3-H04-SPARK-R1"), found["d"])
        self.assertEqual(found["d"]["pane"], 0)
        for url in found["asked"]:
            with self.subTest(url=url):
                self.assertTrue(own(url), url)
        return found

    def test_the_pane_carries_its_caption_and_the_column_holds_it(self):
        short = "The animation shows simulated data drawn from the run's own record. The spacecraft's look and pose are drawn."
        page = self.page
        page.call("Emulation.setDeviceMetricsOverride", {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False})
        try:
            page.open("about:blank", settle=0.3)
            page.open(browser_probe.page_url(self.out, SPARK_R2, "&met=800"), settle=2.0)
            fits = {}
            for met in (800, 909, 959, 1158):
                page.evaluate(SCRUB_TO % met)
                page.wait(0.2)
                fits[met] = page.evaluate("""(() => { const p = document.getElementById('clip-panel'), s = document.getElementById('side');
                    return [p.scrollHeight - p.clientHeight, s.scrollHeight - s.clientHeight]; })()""")
            line = page.evaluate("""(() => { const c = document.getElementById('clip-caption'), copy = c.cloneNode(true);
                copy.querySelectorAll('button').forEach((b) => b.remove());
                return {text: copy.textContent.trim(), shown: c.getClientRects().length > 0,
                        link: document.getElementById('btn-caption').getClientRects().length > 0}; })()""")
            page.evaluate("document.getElementById('btn-caption').click()")
            opened = page.evaluate("""({text: (document.querySelector('#cites .cites-answer') || {}).textContent,
                now: document.querySelector('.now-panel').getClientRects().length,
                panel: document.querySelector('.inspector-panel').getBoundingClientRect().height})""")
            page.open("about:blank", settle=0.3)
            page.open(browser_probe.page_url(self.out, "PH3-H04-SPARK-R1", "&met=7300"))
            alone = page.evaluate("document.getElementById('clip-caption').getClientRects().length")
        finally:
            page.call("Emulation.clearDeviceMetricsOverride")
        self.assertEqual(line, {"text": short, "shown": True, "link": True})
        caption = (self.out / "timelines" / "clips" / (SITE_CLIP + ".caption.txt")).read_text(encoding="utf-8")
        self.assertEqual(caption, build_site.SITE_CAPTIONS[SPARK_R2])
        self.assertEqual(opened.get("text"), caption)
        self.assertEqual(opened["now"], 0)
        self.assertGreater(opened["panel"], 300)
        self.assertEqual(alone, 0)
        for met, (panel, side) in fits.items():
            with self.subTest(met=met):
                self.assertLessEqual(panel, 0, "the pane's caption is cut")
                self.assertLessEqual(side, 0)

    def test_served_over_http_the_page_works_and_the_clip_plays(self):
        with browser_probe.Server(self.out) as server:
            def own(url):
                path = url[len(server.origin):].split("#")[0]
                return url.startswith(server.origin + "/") and (self.out / path.lstrip("/")).is_file()
            self.read_site(server.url, own)
            asked = list(server.asked)
        for path in ("/index.html", "/verda.js", "/verda.css", "/timelines/index.js", "/timelines/%s.js" % SPARK_R2,
                     "/timelines/%s.beside.js" % SPARK_R2, "/timelines/clips/%s.mp4" % SITE_CLIP):
            self.assertIn(path, asked)

    def test_from_disk_the_page_works_and_the_clip_plays(self):
        base = self.out.resolve().as_uri() + "/"

        def own(url):
            return url.startswith(base) and (self.out / url[len(base):].split("#")[0]).is_file()
        self.read_site(lambda run, extra="": browser_probe.page_url(self.out, run, extra), own)


if __name__ == "__main__":
    unittest.main()
