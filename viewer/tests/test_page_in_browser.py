"""The page, opened from disk in a real browser, plays each run (each practice run
beside the Director's pass of its scenario, and the ground-seat run), and each of
his passes no run pairs with yet, and asks for nothing but its own files.

It copies the page to a temporary folder, converts the runs and passes beside it,
with the scenarios' own commands, and opens it in headless Chrome or Edge
(tests/browser_probe.py). With neither browser installed it fails; it never skips.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import _support as S
import browser_probe
import verda_convert as vc

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
        cls.page = browser_probe.Page()
        cls.loads = {}
        try:
            for name in sorted(cls.timelines):
                cls.page.open("about:blank", settle=0.3)
                cls.page.requests, cls.page.errors = [], []
                cls.page.open(browser_probe.page_url(cls.page_dir, name))
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
