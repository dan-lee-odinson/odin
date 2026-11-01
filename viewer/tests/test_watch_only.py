"""VERDA is watch-only: the converter writes its own timeline files and nothing else,
and leaves every run folder, pass folder, plan, scripted-commands file and clip as it
found them."""

import hashlib
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
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
            passes, plans, clips = Path(tmp, "pass-records"), Path(tmp, "plans"), Path(tmp, "clips")
            shutil.copytree(S.passes_dir(), passes)
            shutil.copytree(S.plans_dir(), plans)
            shutil.copytree(S.clips_dir(), clips)
            scripted = Path(tmp, "scripted-commands", S.scripted_path().name)
            scripted.parent.mkdir()
            shutil.copy(S.scripted_path(), scripted)
            out = Path(tmp, "out")
            before = snapshot(tmp)
            with redirect_stdout(io.StringIO()):
                status = vc.main(["--all", str(runs), "--out", str(out), "--dictionary", str(S.dictionary_path()),
                                  "--passes", str(passes), "--plans", str(plans), "--scripted", str(scripted),
                                  "--clips", str(clips)])
            after = snapshot(tmp)
        self.assertEqual(status, 0)
        added = sorted(set(after) - set(before))
        # Each run's own timeline, named by its run_id (the ground-seat run's is dev-s6-0001); a beside file
        # for each run paired with his pass, which is every run but the ground-seat one; the index; the clip.
        ids = ["dev-s6-0001" if name == S.GROUND_SEAT_RUN else name for name in S.ALL_RUNS]
        expected = ["out/%s.js" % i for i in ids] + ["out/%s.beside.js" % i for i in ids if i != "dev-s6-0001"]
        expected += ["out/index.js"] + ["out/clips/%s" % p.name for p in S.clips_dir().iterdir() if p.suffix != ".md"]
        self.assertEqual(added, sorted(expected))
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
