"""Phase 3's seal (CONTRACT.md §10.3): before ODIN's instructions freeze, the repository holds only the hashes of
the held-out files, which stay outside it until the held-out runs are complete: the seal in force, and the first
seal kept beside it (the Director's ruling of 28 October 2026 on sealing again for the phase-1 notes); then S8's
phase-3 checks' seal in force, and their first kept beside it (his ruling of 30 October 2026 on E's check)."""

import re

from tests.repo_checks import REPO_ROOT

FOLDER = REPO_ROOT / "phase3"
SEAL = FOLDER / "SEAL.md"
HASH = re.compile(r"\bsha256:[0-9a-f]{64}\b")
IN_FORCE = "sha256:bc8ae4ace8a100486cc9b11bad17a4e818893e9d1363e3fc9eb4db4fabf6350e"   # 29 October 2026
FIRST = "sha256:5d92af90e06031d9f6db889779e27c598766c0074cc1b635692c42431b9ea330"   # 28 October 2026, a20ad3f
CHECKS = "sha256:6edb98286aac5fdd7687d84a0d2cf1a1188fc46dee05f8ae02b9797ec6eaa32d"   # S8's phase-3 checks, with E's, 30 October 2026
CHECKS_FIRST = "sha256:fe3af633dae31c5304d932317806c0b45043e5588d0e8c575d22432ce996d901"   # their first seal, 30 October 2026


def test_the_seal_holds_the_seal_in_force_the_first_beside_it_and_the_checks_seal():
    assert HASH.findall(SEAL.read_text(encoding="utf-8")) == [IN_FORCE, FIRST, CHECKS, CHECKS_FIRST]


def test_the_seal_names_no_scenario_and_no_plan():
    assert re.findall(r"\bH\d\d\b|TYR0-H", SEAL.read_text(encoding="utf-8")) == []


def test_nothing_but_the_seal_is_here_until_the_held_out_runs():
    assert sorted(p.name for p in FOLDER.iterdir()) == ["SEAL.md"]
