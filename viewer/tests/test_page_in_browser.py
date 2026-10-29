"""The page, opened from disk in a real browser, plays each practice run and asks
for nothing but its own files.

It copies the page to a temporary folder, converts the practice runs beside it,
and opens it in headless Chrome or Edge (tests/browser_probe.py). With neither
browser installed it fails; it never skips.
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
        for run in S.practice_runs():
            path, timeline = vc.convert(run, cls.page_dir / "timelines", S.dictionary_path())
            cls.timelines[run.name] = timeline
        cls.page = browser_probe.Page()
        cls.loads = {}
        try:
            for name in S.PRACTICE_RUNS:
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
                self.assertTrue(load["drawn"]["title"].startswith(name))
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
