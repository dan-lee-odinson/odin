"""VERDA is watch-only: the converter writes its own two files and nothing else."""

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
