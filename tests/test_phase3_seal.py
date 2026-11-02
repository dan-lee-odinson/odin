"""Phase 3's seal (CONTRACT.md §10.3): before ODIN's instructions freeze, the repository holds only the hashes of
the held-out files, which stay outside it until the held-out runs are complete: the seal in force, and the first
seal kept beside it (the Director's ruling of 28 October 2026 on sealing again for the phase-1 notes); then S8's
phase-3 checks' seal in force, and their first kept beside it (his ruling of 30 October 2026 on E's check).

After the runs the files are committed here (his selections of 1 November 2026, RULINGS.md item 25), and each folder
is checked against its seal: the scenarios and the scoring checks byte for byte, and each checks folder's two harness
files in the one line he chose to change, which named the repository's folder under the Windows user profile and now
finds it from the file's own place."""

import hashlib
import re

import pytest

from eval.phase3 import load_checks
from tests.repo_checks import REPO_ROOT

FOLDER = REPO_ROOT / "phase3"
SEAL = FOLDER / "SEAL.md"
HASH = re.compile(r"\bsha256:[0-9a-f]{64}\b")
IN_FORCE = "sha256:bc8ae4ace8a100486cc9b11bad17a4e818893e9d1363e3fc9eb4db4fabf6350e"   # 29 October 2026
FIRST = "sha256:5d92af90e06031d9f6db889779e27c598766c0074cc1b635692c42431b9ea330"   # 28 October 2026, 447c4c3
CHECKS = "sha256:6edb98286aac5fdd7687d84a0d2cf1a1188fc46dee05f8ae02b9797ec6eaa32d"   # S8's phase-3 checks, with E's, 30 October 2026
CHECKS_FIRST = "sha256:fe3af633dae31c5304d932317806c0b45043e5588d0e8c575d22432ce996d901"   # their first seal, 30 October 2026
COMMITTED = ["ODIN_PHASE3_2026-10-28.md", "RULINGS.md", "SEAL.md", "SIGN-PHASE3.md", "acts", "build", "checks",
             "checks-seal-1-2026-10-30", "plans-to-sign", "results", "seal-1-2026-10-28", "sealed", "space-weather",
             "standin-check", "warmup"]
NEW_LINE = b"REPO = Path(__file__).resolve().parents[2]"
# Each harness file changed by his selection: its folder, name and line; its sealed SHA-256, as its manifest lists it;
# its committed SHA-256; and the SHA-256 of the file without that line, the same for the sealed bytes and the committed.
CHANGED = [
    ("checks", "show_red_phase3.py", 14, "68710a7233d3ad732d44955b0f7d5bfa92222c7142a85dc29d2b3fc58e348c9c",
     "0dec33ca306255d317fc84743388deeea879961cf257e06e1746778397858701",
     "d9987ae551d833df4cd0c93bccf067d6b71c0e53056591e28bd8de2d15fcf9bd"),
    ("checks", "test_phase3_checks.py", 10, "184aa0fbfb09aaa5afa3b1657b9042a063d99bf026811aff722d4b117f18fcc8",
     "c9ab6da4caebeada061a20d0bec66341b33d7a04a0515428500852577363a46a",
     "8dd423bb64a0355326ab57b4687003c0caae7a801b2cfe9bdde32b24962b0986"),
    ("checks-seal-1-2026-10-30", "show_red_phase3.py", 14,
     "2963eb933a212c371c6808d8adcd27bc14f519e83d4fddd8f59d02bb5a9fe852",
     "2e21797f908f400f9167db4be7a591dded7e9b491b2b5ab795be8b2fceca4c07",
     "8d9a09cf33f490e36147edf9c009d30ab602eaf6692d8df77422c16d1e89bfd5"),
    ("checks-seal-1-2026-10-30", "test_phase3_checks.py", 10,
     "b4b844cb47d0e20fe705670312992bb561c3b75528a705d33569c617c2528d6c",
     "d76a00dc926691c8c304dcb0b22315b2c78cbea4dc6389b0bb87860c7e173c13",
     "7f1881eef5f809d1fcbc301c43cd3c0a080ca921a384b9453fc516225ba8f11a"),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest(folder):
    """A sealed folder's manifest as {file: SHA-256}, with its own bytes."""
    data = (FOLDER / folder / "MANIFEST.sha256").read_bytes()
    return dict(reversed(line.split("  ")) for line in data.decode("utf-8").splitlines()), data


def files_in(folder):
    return sorted(p.name for p in (FOLDER / folder).iterdir() if p.is_file())


def test_the_seal_holds_the_seal_in_force_the_first_beside_it_and_the_checks_seal():
    assert HASH.findall(SEAL.read_text(encoding="utf-8")) == [IN_FORCE, FIRST, CHECKS, CHECKS_FIRST]


def test_the_seal_names_no_scenario_and_no_plan():
    assert re.findall(r"\bH\d\d\b|TYR0-H", SEAL.read_text(encoding="utf-8")) == []


def test_phase3_holds_the_held_out_files_committed_after_the_runs():
    assert sorted(p.name for p in FOLDER.iterdir()) == COMMITTED


@pytest.mark.parametrize("folder, seal", [("sealed", IN_FORCE), ("seal-1-2026-10-28", FIRST)],
                         ids=["in force", "first"])
def test_the_sealed_scenarios_are_byte_for_byte_as_sealed(folder, seal):
    listed, data = manifest(folder)
    assert "sha256:" + sha(data) == seal
    assert {name: sha((FOLDER / folder / name).read_bytes()) for name in listed} == listed
    assert files_in(folder) == sorted([*listed, "MANIFEST.sha256"])


@pytest.mark.parametrize("folder, seal", [("checks", CHECKS), ("checks-seal-1-2026-10-30", CHECKS_FIRST)],
                         ids=["in force", "first"])
def test_the_scoring_checks_are_as_sealed_but_the_one_line_in_each_harness_file(folder, seal):
    listed, data = manifest(folder)
    assert "sha256:" + sha(data) == seal
    assert sha((FOLDER / folder / "phase3_checks.py").read_bytes()) == listed["phase3_checks.py"]
    changed = [row for row in CHANGED if row[0] == folder]
    assert sorted(listed) == sorted(["phase3_checks.py", *(row[1] for row in changed)])
    record = SEAL.read_text(encoding="utf-8")
    for _, name, number, sealed, committed, without in changed:
        lines = (FOLDER / folder / name).read_bytes().split(b"\n")
        assert listed[name] == sealed
        assert sha(b"\n".join(lines)) == committed
        assert lines[number - 1] == NEW_LINE
        assert sha(b"\n".join(lines[:number - 1] + lines[number:])) == without
        assert all(digest in record for digest in (sealed, committed, without))
    assert files_in(folder) == sorted([*listed, "MANIFEST.sha256"])


@pytest.mark.parametrize("folder, seal", [("checks", CHECKS), ("checks-seal-1-2026-10-30", CHECKS_FIRST)],
                         ids=["in force", "first"])
def test_s8_reads_the_committed_checks_as_this_seal_names_them(folder, seal):
    assert callable(load_checks(FOLDER / folder, seal=seal).check)
