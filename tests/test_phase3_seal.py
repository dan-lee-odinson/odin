"""Phase 3's seal (CONTRACT.md §10.3): before ODIN's instructions freeze, the repository holds only the hash of
the held-out files, which stay outside it until the held-out runs are complete."""

import re

from tests.repo_checks import REPO_ROOT

FOLDER = REPO_ROOT / "phase3"
SEAL = FOLDER / "SEAL.md"
HASH = re.compile(r"\bsha256:[0-9a-f]{64}\b")


def test_the_seal_holds_exactly_one_hash():
    assert len(HASH.findall(SEAL.read_text(encoding="utf-8"))) == 1


def test_the_seal_names_no_scenario_and_no_plan():
    assert re.findall(r"\bH\d\d\b|TYR0-H", SEAL.read_text(encoding="utf-8")) == []


def test_nothing_but_the_seal_is_here_until_the_held_out_runs():
    assert sorted(p.name for p in FOLDER.iterdir()) == ["SEAL.md"]
