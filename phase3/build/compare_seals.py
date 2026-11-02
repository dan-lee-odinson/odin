"""Show that a new phase-3 seal changes nothing but the phase-1 notes' hash in the plans (the Director's
ruling of 28 October 2026). Held out; writes nothing.

    python compare_seals.py OLD_FOLDER NEW_FOLDER     compare two sealed folders
    python compare_seals.py --self-test               the rule on planted changes, in memory

The first seal's files are kept, read-only, in ../seal-1-2026-10-28/. The old folder must still match
the seal committed then. Every file must be in both folders, byte for byte, except that in each plan the
one line holding the phase-1 notes' hash may change, from the placeholder of zeros to a real hash.
The manifest itself differs only by the plans' hashes.
"""

import hashlib
import re
import sys
from pathlib import Path

FIRST_SEAL = "sha256:5d92af90e06031d9f6db889779e27c598766c0074cc1b635692c42431b9ea330"
NOTES = '  - name: "ODIN\'s phase-1 console notes (frozen after phase 1)"'
ZEROS = "sha256:" + "0" * 64
HASH_LINE = re.compile(r"^    sha256: sha256:[0-9a-f]{64}$")


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def files_in(folder):
    return {p.name: p.read_bytes() for p in sorted(Path(folder).iterdir()) if p.is_file()}


def plan_change(old, new):
    """None if the only change is the notes' hash, from zeros to a real hash; else what else changed."""
    a, b = old.decode("utf-8").split("\n"), new.decode("utf-8").split("\n")
    if len(a) != len(b):
        return f"{len(a)} lines became {len(b)}"
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if not changed:
        return "the notes' hash is unchanged"
    if len(changed) > 1 or changed[0] == 0 or a[changed[0] - 1] != NOTES:
        return "lines changed: " + ", ".join(str(i + 1) for i in changed)
    i = changed[0]
    if a[i] != f"    sha256: {ZEROS}" or not HASH_LINE.match(b[i]) or b[i].endswith(ZEROS):
        return f"line {i + 1} is not the placeholder becoming a real hash"
    return None


def compare(old, new):
    """[problems]; empty when the new seal differs from the old only as the ruling allows."""
    problems = []
    if sorted(old) != sorted(new):
        problems.append(f"files differ: only old {sorted(set(old) - set(new))}, only new {sorted(set(new) - set(old))}")
    plans = sorted(n for n in old if n.startswith("TYR0-") and n.endswith(".yaml"))
    for name in sorted(set(old) & set(new)):
        if name == "MANIFEST.sha256":
            continue
        if name in plans:
            why = plan_change(old[name], new[name])
            if why:
                problems.append(f"{name}: {why}")
        elif old[name] != new[name]:
            problems.append(f"{name}: changed")
    if "MANIFEST.sha256" in old and "MANIFEST.sha256" in new:
        expected = {line.split("  ")[1]: line.split("  ")[0] for line in old["MANIFEST.sha256"].decode().splitlines()}
        listed = {line.split("  ")[1]: line.split("  ")[0] for line in new["MANIFEST.sha256"].decode().splitlines()}
        for name, data in new.items():
            if name != "MANIFEST.sha256" and listed.get(name) != hashlib.sha256(data).hexdigest():
                problems.append(f"the new manifest's hash for {name} is not the file's")
        moved = sorted(n for n in listed if listed[n] != expected.get(n))
        if moved != plans:
            problems.append(f"the manifest's changed entries are {moved}, not the plans")
    return problems


def self_test(folder):
    old = files_in(folder)
    plans = [n for n in old if n.startswith("TYR0-")]
    real = "sha256:" + "ab" * 32

    def resealed(edit=None):
        new = {n: (d.replace(f"    sha256: {ZEROS}".encode(), f"    sha256: {real}".encode()) if n in plans else d)
               for n, d in old.items()}
        if edit:
            edit(new)
        new["MANIFEST.sha256"] = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n"
                                         for n, d in sorted(new.items()) if n != "MANIFEST.sha256").encode()
        return compare(old, new)

    cases = {
        "only the notes' hash filled in every plan": (resealed(), True),
        "a scenario file changed too": (resealed(lambda n: n.update(
            {"H01.scenario.yaml": n["H01.scenario.yaml"].replace(b"seed:", b"seed: ", 1)})), False),
        "a plan's contact window moved too": (resealed(lambda n: n.update(
            {plans[0]: n[plans[0]].replace(b"  los_met_s: ", b"  los_met_s: 1", 1)})), False),
        "a plan's notes hash left at zeros": (resealed(lambda n: n.update({plans[0]: old[plans[0]]})), False),
        "a file added": (resealed(lambda n: n.update({"extra.yaml": b"x\n"})), False),
    }
    ok = True
    for name, (problems, allowed) in cases.items():
        right = (problems == []) == allowed
        ok &= right
        print(f"  {'ok  ' if right else 'FAIL'}  {name}: {'allowed' if not problems else problems[0]}")
    return ok


def main(argv):
    if argv == ["--self-test"]:
        kept = Path(__file__).resolve().parent.parent / "seal-1-2026-10-28"
        sys.exit(0 if self_test(kept) else 1)
    old_folder, new_folder = argv
    old, new = files_in(old_folder), files_in(new_folder)
    if sha(old["MANIFEST.sha256"]) != FIRST_SEAL:
        sys.exit(f"{old_folder} is not the first seal: its manifest hashes to {sha(old['MANIFEST.sha256'])}")
    problems = compare(old, new)
    for p in problems:
        print("  FAIL  " + p)
    print("the new seal changes only the phase-1 notes' hash in the plans" if not problems
          else f"{len(problems)} changes the ruling does not allow")
    print(f"old seal {FIRST_SEAL}\nnew seal {sha(new['MANIFEST.sha256'])}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
