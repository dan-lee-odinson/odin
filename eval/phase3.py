"""Phase 3's scoring checks, read where they are sealed (S9, piece 9; the Director's ruling of 28 October 2026 on where
S8's phase-3 checks live). They are built outside the repository, in the held-out folder the caller names, from the
approved phase-3 document and the scoring ruling, and only their seal, the SHA-256 of their MANIFEST.sha256, is in the
repository before the held-out runs: phase3/SEAL.md's scoring checks' seal. Nothing here names a scenario.

The checks are read only after their manifest hashes to that seal, every file it lists matches, and their folder holds
no other file. Then their module's check(label, records, frames, truth_records) scores a phase-3 run.

After the runs they are committed in phase3/ (the Director's selections of 1 November 2026, RULINGS.md item 25):
phase3_checks.py, the module that scores, byte for byte as sealed, and each harness file beside it with the one line
that named the repository's folder changed. So a listed file other than phase3_checks.py may differ from its manifest
only where phase3/SEAL.md, under its own heading, names it with exactly that sealed and that committed SHA-256; then
python -m eval.score --held-out phase3 <run> scores a phase-3 run from the repository.
"""

import hashlib
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEAL = ROOT / "phase3" / "SEAL.md"
CHECKS_SECTION = "## The scoring checks' seal"
HASH = re.compile(r"\bsha256:[0-9a-f]{64}\b")
MODULE = "phase3_checks.py"
COMMITTED_SECTION = "## Committed after the held-out runs"
# A row of that section's table: | `<folder>/<file>` | <line> | `<sealed SHA-256>` | `<committed SHA-256>` | ...
COMMITTED_ROW = re.compile(r"^\| `(?:[^`]*/)?([^`/]+)` \| \d+ \| `([0-9a-f]{64})` \| `([0-9a-f]{64})` \|", re.MULTILINE)


class ChecksSealBroken(Exception):
    pass


def checks_seal(seal_path=SEAL):
    """The scoring checks' seal: the first hash after its own heading in phase3/SEAL.md."""
    text = Path(seal_path).read_text(encoding="utf-8")
    at = text.find(CHECKS_SECTION)
    found = HASH.findall(text[at:]) if at >= 0 else []
    if not found:
        raise ChecksSealBroken(f"{seal_path} names no scoring checks' seal")
    return found[0]


def committed_copies(seal_path=SEAL):
    """The harness files committed with one line changed after the held-out runs, as phase3/SEAL.md names them under
    their own heading: {(file name, sealed SHA-256, committed SHA-256)}. None before the runs."""
    text = Path(seal_path).read_text(encoding="utf-8")
    at = text.find(COMMITTED_SECTION)
    return set() if at < 0 else {m.groups() for m in COMMITTED_ROW.finditer(text[at:])}


def load_checks(folder, seal=None, seal_path=SEAL):
    """The sealed checks' module, from folder, once the folder checks against the seal: phase3_checks.py byte for byte,
    and every other file the manifest lists byte for byte or as a committed copy phase3/SEAL.md names."""
    folder = Path(folder)
    manifest = (folder / "MANIFEST.sha256").read_bytes()
    expected = seal or checks_seal(seal_path)
    found = "sha256:" + hashlib.sha256(manifest).hexdigest()
    if found != expected:
        raise ChecksSealBroken(f"the checks' manifest hashes to {found}, not their seal {expected}")
    committed = committed_copies(seal_path)
    listed = {}
    for line in manifest.decode("utf-8").splitlines():
        digest, name = line.split("  ")
        listed[name] = digest
        actual = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        if actual == digest:
            continue
        if name == MODULE:
            raise ChecksSealBroken(f"{name} does not match the checks' manifest: the module that scores is read only "
                                   f"as sealed")
        if (name, digest, actual) not in committed:
            raise ChecksSealBroken(f"{name} does not match the checks' manifest, and phase3/SEAL.md names no committed "
                                   f"copy of it with SHA-256 {actual}")
    extra = sorted(p.name for p in folder.iterdir() if p.is_file() and p.name not in listed
                   and p.name != "MANIFEST.sha256")
    if extra:
        raise ChecksSealBroken(f"in the checks' folder but not in their manifest: {extra}")
    spec = importlib.util.spec_from_file_location("phase3_checks", folder / MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
