"""The page, opened from disk in a real browser, plays each run (each beside the
Director's pass of its plan or scenario, and the ground-seat run alone), plays an
animation clip locked to its playhead, and asks for nothing but its own files.

It copies the page to a temporary folder, converts the runs and passes beside it,
with the scenarios' own commands, places the animation clips, and opens it in
headless Chrome or Edge (tests/browser_probe.py). With neither browser installed
it fails; it never skips.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _support as S
import browser_probe
import clips
import verda_convert as vc

# Waits until the clip has settled on the playhead (or 8 s), then says where it is.
CLIP_STATE = """new Promise((resolve) => {
  const v = document.getElementById('clip');
  const t0 = performance.now();
  const check = () => {
    const note = document.getElementById('clip-note').textContent;
    const settled = /^(Frame|Holding)/.test(note) && !v.seeking && v.readyState >= 2;
    if (settled || performance.now() - t0 > 8000) {
      resolve({note: note, time: v.currentTime, paused: v.paused, rate: v.playbackRate, src: v.currentSrc,
               boxHidden: document.getElementById('clip-box').hidden});
    } else setTimeout(check, 50);
  };
  check();
})"""
SCRUB_TO = "(() => { const s = document.getElementById('scrub'); s.value = '%d'; s.dispatchEvent(new Event('input')); })()"

PAGE_FILES = ("index.html", "verda.js", "verda.css")
PAGE_FOLDERS = ("fonts",)


class PageInBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.page_dir = Path(cls.tmp.name, "page")
        cls.page_dir.mkdir()
        for name in PAGE_FILES:
            shutil.copy(S.page_dir() / name, cls.page_dir / name)
        for name in PAGE_FOLDERS:
            shutil.copytree(S.page_dir() / name, cls.page_dir / name)
        cls.timelines = {}
        for _, path, timeline in vc.convert_all(S.all_runs(), cls.page_dir / "timelines", S.dictionary_path(),
                                                True, S.passes_dir(), S.plans_dir(), S.scripted_path()):
            if path is None:
                raise AssertionError("a timeline could not be made: %s" % timeline)
            cls.timelines[timeline["id"]] = timeline
        cls.placed = [p for _, p, problems in clips.place_clips(S.clips_dir(), cls.page_dir / "timelines") if p]
        vc.write_index(cls.page_dir / "timelines")
        cls.page = browser_probe.Page()
        cls.loads = {}
        try:
            for name in sorted(cls.timelines):
                cls.page.open("about:blank", settle=0.3)
                cls.page.requests, cls.page.errors = [], []
                cls.page.open(browser_probe.page_url(cls.page_dir, name), settle=1.2)
                drawn = cls.page.evaluate(
                    "({lanes: document.querySelectorAll('.lane-label').length,"
                    " title: document.getElementById('title').textContent,"
                    " banner: document.getElementById('banner').className,"
                    " loaded: !!(window.VERDA_TIMELINES && window.VERDA_TIMELINES[%r])})" % name)
                cls.loads[name] = {"requests": list(cls.page.requests), "errors": list(cls.page.errors), "drawn": drawn}
        except Exception:
            cls.page.close()
            cls.tmp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.page.close()
        cls.tmp.cleanup()

    def test_asks_only_for_its_own_files_on_disk(self):
        base = self.page_dir.resolve().as_uri() + "/"
        for name, load in self.loads.items():
            with self.subTest(run=name):
                wanted = {base + p for p in ("index.html", "verda.css", "verda.js", "fonts/Michroma-Regular.ttf",
                                             "timelines/index.js", "timelines/%s.js" % name)}
                if self.timelines[name]["header"].get("pass"):
                    wanted.add(base + "timelines/%s.beside.js" % name)
                if name == S.PREVIEW_RUN:
                    wanted.add(base + "timelines/clips/%s_preview.mp4" % name)
                asked = {url.split("#")[0] for url in load["requests"]}
                self.assertEqual(asked, wanted)

    def test_no_script_or_console_errors(self):
        for name, load in self.loads.items():
            with self.subTest(run=name):
                self.assertEqual(load["errors"], [])

    def test_draws_every_lane_of_each_run(self):
        for name, load in self.loads.items():
            with self.subTest(run=name):
                self.assertTrue(load["drawn"]["loaded"])
                self.assertEqual(load["drawn"]["lanes"], len(self.timelines[name]["lanes"]))
                self.assertTrue(load["drawn"]["title"].startswith(self.timelines[name]["title"]))
                self.assertNotIn("bad", load["drawn"]["banner"])

    def test_hover_and_click_show_a_request_and_its_records(self):
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, "dev-practice-p3"))
        found = page.evaluate("""(() => {
            const label = [...document.querySelectorAll('text[data-hit]')].find((t) => t.textContent.includes('ACCEPTED'));
            if (!label) return null;
            const r = label.getBoundingClientRect();
            const at = {bubbles: true, clientX: r.left + 4, clientY: r.top + 4};
            label.dispatchEvent(new MouseEvent('mousemove', at));
            const tip = document.getElementById('tooltip');
            const hover = tip.hidden ? '' : tip.textContent;
            label.dispatchEvent(new MouseEvent('click', at));
            return {hover: hover, title: document.getElementById('inspector-title').textContent,
                    record: document.getElementById('inspector').textContent};
        })()""")
        self.assertIsNotNone(found, "no request chain label on the page")
        self.assertIn("BALDUR-0 allowed it at MET 900", found["hover"])
        self.assertIn("Outcome ACCEPTED at MET 902", found["hover"])
        self.assertTrue(found["title"].startswith("Request "))
        for record_type in ("REQUEST", "DECISION", "DISPATCH", "OUTCOME"):
            self.assertIn('"type": "%s"' % record_type, found["record"])

    def test_hover_and_click_show_the_directors_command_and_his_rows(self):
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, "dev-practice-p3"))
        found = page.evaluate("""(() => {
            const label = [...document.querySelectorAll('text[data-hit]')].find((t) => t.textContent.endsWith('-> sent -> accepted'));
            if (!label) return null;
            const r = label.getBoundingClientRect();
            const at = {bubbles: true, clientX: r.left + 4, clientY: r.top + 4};
            label.dispatchEvent(new MouseEvent('mousemove', at));
            const tip = document.getElementById('tooltip');
            const hover = tip.hidden ? '' : tip.textContent;
            label.dispatchEvent(new MouseEvent('click', at));
            return {hover: hover, title: document.getElementById('inspector-title').textContent,
                    record: document.getElementById('inspector').textContent};
        })()""")
        self.assertIsNotNone(found, "no label of the Director's command on the page")
        self.assertIn("The Director sent CMD_PLD_SET_STATE state=OFF at 2026-10-11 17:07:43.660 UTC", found["hover"])
        self.assertIn("MET 958.54, between his frames at MET 958", found["hover"])
        self.assertTrue(found["title"].startswith("The Director\u2019s command \u00b7 MET 958.54"), found["title"])
        for name in ('"file": "commands.csv"', '"file": "telemetry_hk.csv"', '"CDH_MET": "959"'):
            self.assertIn(name, found["record"])

    def test_hover_and_click_show_the_scenarios_command_apart_from_his(self):
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, "dev-practice-p4"))
        found = page.evaluate("""(() => {
            const label = [...document.querySelectorAll('text[data-hit]')].find((t) => t.textContent === "CMD_SYS_RESET, in contact: ODIN's runs drop it");
            if (!label) return null;
            const r = label.getBoundingClientRect();
            const at = {bubbles: true, clientX: r.left + 4, clientY: r.top + 4};
            label.dispatchEvent(new MouseEvent('mousemove', at));
            const tip = document.getElementById('tooltip');
            const hover = tip.hidden ? '' : tip.textContent;
            label.dispatchEvent(new MouseEvent('click', at));
            return {hover: hover, title: document.getElementById('inspector-title').textContent,
                    record: document.getElementById('inspector').textContent,
                    subs: [...document.querySelectorAll('text.lane-sub')].map((t) => t.textContent)};
        })()""")
        self.assertIsNotNone(found, "no label of the scenario's command on the page")
        self.assertTrue(found["hover"].startswith(
            "The scenario\u2019s own command, not the Director\u2019s: CMD_SYS_RESET at MET 1320"), found["hover"])
        self.assertIn("his pass carried it; ODIN\u2019s runs drop it", found["hover"])
        self.assertNotIn("The Director sent", found["hover"])
        self.assertTrue(found["title"].startswith("The scenario\u2019s command \u00b7 MET 1320"), found["title"])
        for text in ('"not_the_directors"', '"source": "sim/scenarios/P4_hk_generation_halt.yaml:31"', '"CDH_MET": "1199"'):
            self.assertIn(text, found["record"])
        # The lane says it whole, beside the commands.
        self.assertIn("ODIN's runs drop the in-contact ones", found["subs"])

    def test_the_ground_seat_age_lane_names_what_its_bundles_recorded(self):
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, "dev-s6-0001"))
        found = page.evaluate("""(() => ({
            tags: [...document.querySelectorAll('text.strip-tag')].map((t) => t.textContent),
            labels: [...document.querySelectorAll('text.ev-label')].map((t) => t.textContent)}))()""")
        self.assertEqual(found["tags"], ["STALENESS", "LINK"])
        for state in ("GREEN", "YELLOW", "CONNECTED"):
            self.assertIn(state, found["labels"])

    def labels_starting(self, run_id, start):
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, run_id))
        return page.evaluate("""(() => {
            const plot = document.querySelector('#plot-clip rect').getBBox();
            return [...document.querySelectorAll('text.ev-label')].filter((t) => t.textContent.startsWith(%s))
                .map((t) => { const b = t.getBBox(); return {text: t.textContent, left: b.x, right: b.x + b.width,
                                                            plotLeft: plot.x, plotRight: plot.x + plot.width}; });
        })()""" % json.dumps(start))

    def test_a_name_near_the_right_edge_is_written_whole(self):
        # The ground-seat run's fault starts at MET 900, ten seconds before the end of its view; in this
        # P2B run ODIN's load shed comes near the end of its pass.
        for run_id, start, whole in (("dev-s6-0001", "Fault onset", "Fault onset: stuck_load"),
                                     ("PH2-PASS2B-OPEN-R1", "CMD_PLD_SET_STATE state=OFF -> ALLOW",
                                      "CMD_PLD_SET_STATE state=OFF -> ALLOW -> sent -> ACCEPTED")):
            with self.subTest(run=run_id):
                found = self.labels_starting(run_id, start)
                self.assertEqual([f["text"] for f in found], [whole])
                self.assertGreaterEqual(found[0]["left"], found[0]["plotLeft"])
                self.assertLessEqual(found[0]["right"], found[0]["plotRight"])

    def test_a_run_opens_on_its_pass(self):
        # A P2B run starts at MET 0, and its pass begins at MET 21800.
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, "PH2-PASS2B-OPEN-R1"))
        found = page.evaluate("""({met: document.getElementById('met').textContent,
            ticks: [...document.querySelectorAll('text.axis-text')].map((t) => Number(t.textContent))})""")
        self.assertEqual(self.timelines["PH2-PASS2B-OPEN-R1"]["met_range"][0], 0)
        self.assertEqual(found["met"], "MET 21780 s")
        self.assertGreaterEqual(min(found["ticks"]), 21780)
        self.assertLessEqual(max(found["ticks"]), 22250)

    def test_a_known_met_lands_on_the_frame_the_sync_file_gives(self):
        # The preview's sync file: first frame MET 890, a frame every 5 s of MET, 10 frames a second.
        sync = json.loads((S.clips_dir() / (S.PREVIEW_RUN + "_preview.sync.json")).read_text(encoding="utf-8"))
        self.assertEqual((sync["first_frame_met_s"], sync["met_step_s"], sync["fps"]), (890, 5, 10))
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, S.PREVIEW_RUN, "&met=910"))
        at_910 = page.evaluate(CLIP_STATE)
        page.evaluate(SCRUB_TO % 922)
        at_922 = page.evaluate(CLIP_STATE)
        # MET 910 is (910 - 890) / 5 = 4 frames in: the fifth frame, shown from 0.4 s to 0.5 s of the clip.
        self.assertTrue(at_910["note"].startswith("Frame 5 of 9, MET 910"), at_910["note"])
        self.assertTrue(at_910["src"].endswith("timelines/clips/%s_preview.mp4" % S.PREVIEW_RUN), at_910["src"])
        self.assertTrue(0.4 <= at_910["time"] < 0.5, at_910["time"])
        # MET 922 lies between the frames for 920 and 925: the one for 920, 6 frames in.
        self.assertTrue(at_922["note"].startswith("Frame 7 of 9, MET 920"), at_922["note"])
        self.assertTrue(0.6 <= at_922["time"] < 0.7, at_922["time"])

    def test_a_mismatched_hash_shows_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            page_dir = Path(tmp, "page")
            shutil.copytree(self.page_dir, page_dir, ignore=shutil.ignore_patterns("timelines"))
            vc.convert(S.runs_dir() / S.PREVIEW_RUN, page_dir / "timelines", S.dictionary_path())
            source = Path(tmp, "clips")
            source.mkdir()
            name = S.PREVIEW_RUN + "_preview"
            shutil.copy(S.clips_dir() / (name + ".mp4"), source / (name + ".mp4"))
            sync = json.loads((S.clips_dir() / (name + ".sync.json")).read_text(encoding="utf-8"))
            # One hex digit of the pinned hash changed: a clip rendered from another timeline file.
            sync["timeline_sha256"] = sync["timeline_sha256"][:-1] + ("0" if sync["timeline_sha256"][-1] != "0" else "1")
            (source / (name + ".sync.json")).write_text(json.dumps(sync), encoding="utf-8")
            list(clips.place_clips(source, page_dir / "timelines"))
            vc.write_index(page_dir / "timelines")
            page = self.page
            page.open("about:blank", settle=0.3)
            page.requests = []
            page.open(browser_probe.page_url(page_dir, S.PREVIEW_RUN, "&met=910"))
            found = page.evaluate("""({note: document.getElementById('clip-note').textContent,
                boxHidden: document.getElementById('clip-box').hidden,
                src: document.getElementById('clip').currentSrc, srcAttr: document.getElementById('clip').getAttribute('src')})""")
            asked = list(page.requests)
        self.assertTrue(found["boxHidden"])
        self.assertEqual((found["src"], found["srcAttr"]), ("", None))
        self.assertTrue(found["note"].startswith("Not played: it was rendered from another timeline file."), found["note"])
        self.assertFalse([u for u in asked if u.endswith(".mp4")], "the clip was fetched")

    def test_the_clip_holds_outside_its_frames_and_follows_play_and_pause(self):
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, S.PREVIEW_RUN, "&met=1000"))
        after = page.evaluate(CLIP_STATE)
        page.evaluate(SCRUB_TO % 850)
        before = page.evaluate(CLIP_STATE)
        self.assertTrue(after["note"].startswith("Holding at the last frame: the clip ends at MET 930."), after["note"])
        self.assertTrue(0.8 <= after["time"] < 0.9, after["time"])
        self.assertTrue(before["note"].startswith("Holding at the first frame: the clip starts at MET 890."), before["note"])
        self.assertTrue(0.0 <= before["time"] < 0.1, before["time"])
        # Played at 10x, ten seconds of MET a second: the clip plays itself at 10 / (10 x 5) = 0.2 of its pace.
        page.evaluate(SCRUB_TO % 892)
        page.evaluate("(() => { const s = document.getElementById('speed'); s.value = '10'; s.dispatchEvent(new Event('change'));"
                      " document.getElementById('btn-play').click(); })()")
        page.wait(1.0)
        playing = page.evaluate("({paused: document.getElementById('clip').paused, rate: document.getElementById('clip').playbackRate})")
        page.evaluate("document.getElementById('btn-play').click()")
        stopped = page.evaluate(CLIP_STATE)
        met = int(page.evaluate("document.getElementById('met').textContent").split()[1])
        self.assertEqual(playing, {"paused": False, "rate": 0.2})
        self.assertTrue(stopped["paused"])
        # Paused, it shows the playhead's own frame.
        frame = (met - 890) // 5
        self.assertTrue(stopped["note"].startswith("Frame %d of 9, MET %d" % (frame + 1, 890 + 5 * frame)), (met, stopped["note"]))
        self.assertTrue(frame / 10 <= stopped["time"] < (frame + 1) / 10, stopped["time"])

    def test_every_lane_fits_a_1920_by_1080_screen(self):
        page = self.page
        page.call("Emulation.setDeviceMetricsOverride", {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False})
        try:
            for run_id in (S.PREVIEW_RUN, "PH2-PASS1-SPARK-R1", "PH2-PASS2B-OPEN-R1", "PH2-PASS4-SPARK-R1", "dev-practice-p4"):
                with self.subTest(run=run_id):
                    page.open("about:blank", settle=0.3)
                    page.open(browser_probe.page_url(self.page_dir, run_id))
                    found = page.evaluate("""(() => { const l = document.getElementById('lanes');
                        return {scroll: l.scrollHeight, client: l.clientHeight}; })()""")
                    self.assertLessEqual(found["scroll"], found["client"])
        finally:
            page.call("Emulation.clearDeviceMetricsOverride")

    def test_play_moves_the_playhead(self):
        page = self.page
        page.open("about:blank", settle=0.3)
        page.open(browser_probe.page_url(self.page_dir, "dev-practice-p4"))
        before = page.evaluate("document.getElementById('met').textContent")
        page.evaluate("document.getElementById('btn-play').click()")
        page.wait(1.5)
        after = page.evaluate("document.getElementById('btn-play').click(), document.getElementById('met').textContent")
        self.assertEqual(before, "MET 1100 s")
        self.assertGreater(int(after.split()[1]), 1100, after)


if __name__ == "__main__":
    unittest.main()
