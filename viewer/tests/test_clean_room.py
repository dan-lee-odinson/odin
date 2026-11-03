"""The clean-room tests: no VERDA file imports HUGINN's old viewer package or names
the folders of HUGINN's old viewer or its replay schema, and no file a deposit takes
holds a path under a user's own folder.

The patterns are put together from pieces, so this file does not itself hold the
names it looks for, and a scan of this file finds nothing.
"""

import os
import re
import unittest
from pathlib import Path

import _support as S

PACKAGE = "v" + "e"
FOLDERS = (PACKAGE, "view" + "er", "re" + "play")
SCHEMA = "re" + "play" + "_" + "schema"

# A folder name as a path segment: "<name>/" or "<name>\", not inside a longer word.
FOLDER_PATTERN = re.compile(r"(?<![A-Za-z0-9_.-])(?:%s)[/\\]" % "|".join(FOLDERS), re.I)
SCHEMA_PATTERN = re.compile(re.escape(SCHEMA), re.I)
IMPORT_PATTERNS = (
    re.compile(r"^\s*import\s+%s(?:\s|\.|,|$)" % PACKAGE, re.M),
    re.compile(r"^\s*from\s+%s(?:\s|\.)" % PACKAGE, re.M),
    re.compile(r"""\b(?:require|import)\s*\(\s*['"]%s(?:['"/])""" % PACKAGE),
    re.compile(r"""\bfrom\s+['"]%s(?:['"/])""" % PACKAGE),
    re.compile(r"""__import__\s*\(\s*['"]%s['"]""" % PACKAGE),
    re.compile(r"""import_module\s*\(\s*['"]%s(?:['"]|\.)""" % PACKAGE),
)

# A path under a user's own folder: "C:\<Users>\<name>" or "C:/<Users>/<name>", the
# same with doubled backslashes as in source code or JSON, "/<Users>/<name>" (macOS,
# also as a file URL) or "/home/<name>" (Linux). Everything in a deposit becomes
# public, and such a path names a person's account on a machine.
USERS = "Us" + "ers"
USER_PATH_PATTERN = re.compile(
    r"(?:\b[A-Za-z]:[\\/]{1,2}|(?<![\w.\\/-])[\\/]{1,3})(?:%s|home)[\\/]{1,2}[^\\/\s\"'`<>|]" % USERS, re.I)


def user_folder_paths(text):
    """Each place in the text that holds a path under a user's folder, with what follows it."""
    return [text[m.start():m.end() + 40].split("\n")[0] for m in USER_PATH_PATTERN.finditer(text)]


# What is not VERDA's own: the inputs Claude Code placed, deposits already made,
# scratch files, generated timelines, caches, and the pinned ffmpeg build the
# capture tool encodes with (a third-party program no deposit takes).
SKIP_DIRS = {"inputs", "to-claude-code", ".scratch", "timelines", "__pycache__", ".git", "ffmpeg"}
# The Director's brief to this session: an input that names the folders VERDA must
# never open. It is not VERDA's file and is never deposited.
SKIP_FILES = {"VERDA_BRIEF.md"}


def verda_files():
    out = []
    for folder, dirs, files in os.walk(S.ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if Path(folder) == S.ROOT and name in SKIP_FILES:
                continue
            out.append(Path(folder, name))
    return sorted(out)


def text_of(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


class CleanRoom(unittest.TestCase):
    def test_the_scan_sees_verda_files(self):
        names = {p.relative_to(S.ROOT).as_posix() for p in verda_files()}
        for expected in ("convert/verda_convert.py", "page/verda.js", "page/index.html", "tests/test_clean_room.py"):
            self.assertIn(expected, names)

    def test_nothing_imports_the_old_viewer_package(self):
        for path in verda_files():
            text = text_of(path)
            for pattern in IMPORT_PATTERNS:
                with self.subTest(file=path.relative_to(S.ROOT).as_posix(), pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))

    def test_nothing_names_the_old_viewer_folders(self):
        for path in verda_files():
            text = text_of(path)
            with self.subTest(file=path.relative_to(S.ROOT).as_posix()):
                self.assertEqual(FOLDER_PATTERN.findall(text), [])
                self.assertEqual(SCHEMA_PATTERN.findall(text), [])

    def test_no_deposited_file_holds_a_user_folder_path(self):
        files = S.deposit_files()
        names = {p.relative_to(S.ROOT).as_posix() for p in files}
        for expected in ("README.md", "convert/verda_convert.py", "page/verda.js", "page/fonts/OFL.txt",
                         "tests/test_clean_room.py"):
            self.assertIn(expected, names)
        for path in files:
            with self.subTest(file=path.relative_to(S.ROOT).as_posix()):
                self.assertEqual(user_folder_paths(text_of(path)), [])


if __name__ == "__main__":
    unittest.main()
