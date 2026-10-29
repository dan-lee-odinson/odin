"""Phase 3's seal (CONTRACT.md §10.3): before ODIN's instructions freeze, the repository holds only the hashes of
the held-out files, which stay outside it until the held-out runs are complete: the seal in force, and the first
seal kept beside it (the Director's ruling of 28 October 2026 on sealing again for the phase-1 notes)."""

import re

from tests.repo_checks import REPO_ROOT

FOLDER = REPO_ROOT / "phase3"
SEAL = FOLDER / "SEAL.md"
HASH = re.compile(r"\bsha256:[0-9a-f]{64}\b")
IN_FORCE = "sha256:bc8ae4ace8a100486cc9b11bad17a4e818893e9d1363e3fc9eb4db4fabf6350e"   # 29 October 2026
FIRST = "sha256:5d92af90e06031d9f6db889779e27c598766c0074cc1b635692c42431b9ea330"   # 28 October 2026, a20ad3f


def test_the_seal_holds_the_seal_in_force_and_the_first_beside_it():
    assert HASH.findall(SEAL.read_text(encoding="utf-8")) == [IN_FORCE, FIRST]


def test_the_seal_names_no_scenario_and_no_plan():
    assert re.findall(r"\bH\d\d\b|TYR0-H", SEAL.read_text(encoding="utf-8")) == []


def test_nothing_but_the_seal_is_here_until_the_held_out_runs():
    assert sorted(p.name for p in FOLDER.iterdir()) == ["SEAL.md"]
