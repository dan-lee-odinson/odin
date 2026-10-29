"""VERDA is watch-only: the converter writes its own timeline files and nothing else,
and leaves every run folder, pass folder and plan as it found them."""

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import _support as S
import verda_convert as vc


def snapshot(folder):
    out = {}
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file():
            out[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class WatchOnly(unittest.TestCase):
    def test_converter_writes_only_its_files_and_leaves_the_run_untouched(self):
        source = S.practice_runs()[0]
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp, "run", source.name)
            shutil.copytree(source, run)
            out = Path(tmp, "out")
            before = snapshot(tmp)
            vc.convert(run, out, S.dictionary_path())
            after = snapshot(tmp)
        added = sorted(set(after) - set(before))
        self.assertEqual(added, ["out/%s.js" % source.name, "out/index.js"])
        self.assertEqual({k: after[k] for k in before}, before, "a file that was there before changed")

    def test_with_passes_it_writes_only_timelines_and_leaves_passes_and_plans_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp, "runs")
            for source in S.all_runs():
                shutil.copytree(source, runs / source.name)
            passes, plans = Path(tmp, "pass-records"), Path(tmp, "plans")
            shutil.copytree(S.passes_dir(), passes)
            shutil.copytree(S.plans_dir(), plans)
            scripted = Path(tmp, "scripted-commands", S.scripted_path().name)
            scripted.parent.mkdir()
            shutil.copy(S.scripted_path(), scripted)
            out = Path(tmp, "out")
            before = snapshot(tmp)
            results = list(vc.convert_all(sorted(runs.iterdir()), out, S.dictionary_path(), True, passes, plans, scripted))
            after = snapshot(tmp)
        self.assertEqual([r[1] is not None for r in results], [True] * 7)
        added = sorted(set(after) - set(before))
        # The ground-seat run's timeline is named by its run_id, dev-s6-0001.
        names = list(S.PRACTICE_RUNS) + ["dev-s6-0001", "pass-2026-09-13-P1", "pass-2026-09-20-P2a",
                                         "pass-2026-09-20-P2b", "index"]
        self.assertEqual(added, sorted("out/%s.js" % name for name in names))
        self.assertEqual({k: after[k] for k in before}, before, "a file that was there before changed")

    def test_output_names_cannot_leave_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Each name goes into an empty child folder, so a name that got through could
            # only reach that child or the temporary folder, never anywhere else.
            inner = Path(tmp, "out")
            for name in ("../escape.js", "a/b.js", "a\\b.js", "..", ""):
                with self.subTest(name=name):
                    try:
                        vc._write_output(inner, name, "x")
                    except ValueError:
                        continue
                    except Exception as exc:  # noqa: BLE001 - any other outcome is a failure
                        self.fail("%r was not refused; writing it raised %r" % (name, exc))
                    self.fail("%r was written" % name)
            left = sorted(p.relative_to(tmp).as_posix() for p in Path(tmp).rglob("*"))
            self.assertIn(left, ([], ["out"]))


if __name__ == "__main__":
    unittest.main()
