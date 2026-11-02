"""Show that the checks' new seal changes nothing but E's check added, with its test and red cases (the Director's
ruling of 30 October 2026, "Seal E's check now; fly E after A-D if time allows"). Held out; writes nothing.

    python compare_checks_seals.py OLD_FOLDER NEW_FOLDER     compare two sealed checks folders
    python compare_checks_seals.py --self-test               the rule on planted changes, in memory

The checks' first seal's files are kept, read-only, in ../checks-seal-1-2026-10-30/. The old folder must still match
the seal committed then. Every file must be in both folders, and each may change only by an addition, every old line
kept in order:
- phase3_checks.py: one block, E's section (from its "# -- E" comment), inserted just before CHECKS, and the CHECKS
  line given "E": check_e and nothing else;
- test_phase3_checks.py: lines added at its end only, E's section, whose tests are all E's (test_..._e_...);
- show_red_phase3.py: cases added at the end of CASES only, each titled "E: ".
The manifest's every entry must be its file's hash.
"""

import difflib
import hashlib
import re
import sys
from pathlib import Path

FIRST_SEAL = "sha256:fe3af633dae31c5304d932317806c0b45043e5588d0e8c575d22432ce996d901"
FILES = ("phase3_checks.py", "show_red_phase3.py", "test_phase3_checks.py")
CHECKS_LINE = 'CHECKS = {"A": check_a, "B": check_b, "C": check_c, "D": check_d}'
CHECKS_LINE_E = 'CHECKS = {"A": check_a, "B": check_b, "C": check_c, "D": check_d, "E": check_e}'


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def files_in(folder):
    return {p.name: p.read_bytes() for p in sorted(Path(folder).iterdir()) if p.is_file()}


def insertions(old, new):
    """[(old line index, [inserted lines])] if new is old with lines only inserted, else None."""
    a, b = old.decode("utf-8").split("\n"), new.decode("utf-8").split("\n")
    found = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "insert":
            found.append((i1, b[j1:j2]))
        elif tag != "equal":
            return None
    return found


def checks_change(old, new):
    """None if phase3_checks.py gains only E's section before CHECKS and "E" in CHECKS; else what else changed."""
    text = old.decode("utf-8")
    if text.count(CHECKS_LINE) != 1:
        return "the old file's CHECKS line is not the sealed one"
    added = insertions(old, new.replace(CHECKS_LINE_E.encode(), CHECKS_LINE.encode()))
    if added is None or new.decode("utf-8").count(CHECKS_LINE_E) != 1:
        return "lines changed or removed, or CHECKS not given E alone"
    if len(added) != 1:
        return f"{len(added)} inserted blocks, not one"
    at, lines = added[0]
    if text.split("\n")[at] != CHECKS_LINE or not lines[0].startswith("# -- E "):
        return "the inserted block is not E's section just before CHECKS"
    defined = re.findall(r"^def (\w+)", "\n".join(lines), re.M)
    if defined != ["check_e"]:
        return f"the inserted block defines {defined}, not check_e alone"
    return None


def tests_change(old, new):
    """None if test_phase3_checks.py gains only E's section at its end; else what else changed."""
    if not new.startswith(old):
        return "lines changed or added before its end"
    added = new[len(old):].decode("utf-8")
    if not re.search(r"^# -- E ", added, re.M):
        return "the added lines are not E's section"
    tests = re.findall(r"^def (test_\w+)", added, re.M)
    if not tests or any("_e_" not in name for name in tests):
        return f"the added tests are {tests}, not E's alone"
    return None


def red_change(old, new):
    """None if show_red_phase3.py gains only cases titled "E: " at the end of CASES; else what else changed."""
    added = insertions(old, new)
    if added is None or len(added) != 1:
        return "lines changed or removed, or added in more than one place"
    at, lines = added[0]
    a = old.decode("utf-8").split("\n")
    start = a.index("CASES = [")
    if at != a.index("]", start):
        return "the added lines are not at the end of CASES"
    titles = re.findall(r'^    \("([^"]*)"', "\n".join(lines), re.M)
    if not titles or any(not t.startswith("E: ") for t in titles):
        return f"the added cases are {titles}, not E's alone"
    return None


RULES = {"phase3_checks.py": checks_change, "test_phase3_checks.py": tests_change, "show_red_phase3.py": red_change}


def compare(old, new):
    """[problems]; empty when the new seal differs from the old only as the ruling allows."""
    problems = []
    if sorted(old) != sorted(new):
        problems.append(f"files differ: only old {sorted(set(old) - set(new))}, only new {sorted(set(new) - set(old))}")
    for name in FILES:
        if name in old and name in new:
            why = RULES[name](old[name], new[name])
            if why:
                problems.append(f"{name}: {why}")
    if "MANIFEST.sha256" in new:
        listed = {line.split("  ")[1]: line.split("  ")[0] for line in new["MANIFEST.sha256"].decode().splitlines()}
        if sorted(listed) != sorted(n for n in new if n != "MANIFEST.sha256"):
            problems.append(f"the new manifest lists {sorted(listed)}")
        for name, data in new.items():
            if name != "MANIFEST.sha256" and listed.get(name) != hashlib.sha256(data).hexdigest():
                problems.append(f"the new manifest's hash for {name} is not the file's")
    return problems


def self_test(old, new):
    """The rule on the real old and new folders, with one change planted in the new at a time."""
    def planted(name, before, after):
        changed = dict(new)
        assert changed[name].count(before) == 1, (name, before)
        changed[name] = changed[name].replace(before, after)
        changed["MANIFEST.sha256"] = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n"
                                             for n, d in sorted(changed.items()) if n != "MANIFEST.sha256").encode()
        return compare(old, changed)

    def added(extra):
        changed = dict(new, **extra)
        changed["MANIFEST.sha256"] = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n"
                                             for n, d in sorted(changed.items()) if n != "MANIFEST.sha256").encode()
        return compare(old, changed)

    cases = {
        "only E's check, its test and red cases added": (compare(old, new), True),
        "A's check changed too": (planted("phase3_checks.py", b"and los is not None and after < los",
                                          b"and los is not None and after <= los"), False),
        "D's test changed too": (planted("test_phase3_checks.py", b"def test_red_d_odins_success_and_the_system_checks",
                                         b"def test_red_d_odins_success_and_its_system_checks"), False),
        "a red case of D's added with E's": (planted("show_red_phase3.py", b'    ("E: a shed accepted outside contact B',
                                                     b'    ("D: one more",\n     "t", "x", "y"),\n'
                                                     b'    ("E: a shed accepted outside contact B'), False),
        "a second check function added": (planted("phase3_checks.py", b"\n\nCHECKS = {",
                                                  b"\n\ndef check_f(records, frames, truth_records):\n    return None"
                                                  b"\n\n\nCHECKS = {"), False),
        "a file added": (added({"extra.py": b"x\n"}), False),
        "the manifest's hash wrong": (compare(old, dict(new, **{"MANIFEST.sha256": new["MANIFEST.sha256"].replace(
            new["MANIFEST.sha256"][:4], b"0000", 1)})), False),
    }
    ok = True
    for name, (problems, allowed) in cases.items():
        right = (problems == []) == allowed
        ok &= right
        print(f"  {'ok  ' if right else 'FAIL'}  {name}: {'allowed' if not problems else problems[0]}")
    return ok


def main(argv):
    here = Path(__file__).resolve().parent.parent
    if argv == ["--self-test"]:
        sys.exit(0 if self_test(files_in(here / "checks-seal-1-2026-10-30"), files_in(here / "checks")) else 1)
    old_folder, new_folder = argv
    old, new = files_in(old_folder), files_in(new_folder)
    if sha(old["MANIFEST.sha256"]) != FIRST_SEAL:
        sys.exit(f"{old_folder} is not the checks' first seal: its manifest hashes to {sha(old['MANIFEST.sha256'])}")
    problems = compare(old, new)
    for p in problems:
        print("  FAIL  " + p)
    print("the new seal adds only E's check, its test and its red cases" if not problems
          else f"{len(problems)} changes the ruling does not allow")
    print(f"old seal {FIRST_SEAL}\nnew seal {sha(new['MANIFEST.sha256'])}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
