"""S9, piece 9: S8's phase-3 checks are read where they are sealed (eval/phase3.py), outside the repository, only
after their manifest hashes to the scoring checks' seal in phase3/SEAL.md, every file it lists matches, and their
folder holds nothing else; then they score a phase-3 run (eval/results.py). On made-up checks: none of the held-out
checks, labels or values is in the repository."""

import hashlib
import threading

import pytest

from eval.phase3 import ChecksSealBroken, checks_seal, load_checks
from eval.results import score_run
from harness.phase3 import seal_in_force
from tests.harness_world import HarnessWorld
from tests.test_phase3_seal import CHECKS

MADE_UP = '''def check(label, records, frames, truth_records):
    return {"scenario": "Z", "exercised": True, "success": label == "P3", "measured": {"records": len(records)},
            "wrong_actions": [], "system_checks": None}
'''


def made_up_checks(folder):
    """A folder of made-up sealed checks; returns (folder, its seal)."""
    folder.mkdir(parents=True)
    (folder / "phase3_checks.py").write_bytes(MADE_UP.encode("utf-8"))
    manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(folder.iterdir()))
    (folder / "MANIFEST.sha256").write_bytes(manifest.encode("utf-8"))
    return folder, "sha256:" + hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def test_the_checks_seal_is_its_own_entry_in_seal_md_apart_from_the_scenarios():
    assert checks_seal() == CHECKS != seal_in_force()


def test_red_checks_that_match_their_seal_are_read_and_others_are_refused(tmp_path):
    folder, seal = made_up_checks(tmp_path / "checks")
    assert load_checks(folder, seal=seal).check("P3", [], {}, [])["success"]
    with pytest.raises(ChecksSealBroken, match="not their seal"):
        load_checks(folder, seal="sha256:" + "00" * 32)


def test_red_a_checks_file_changed_by_one_byte_is_refused(tmp_path):
    folder, seal = made_up_checks(tmp_path / "checks")
    (folder / "phase3_checks.py").write_bytes(MADE_UP.replace('"Z"', '"Y"').encode("utf-8"))
    with pytest.raises(ChecksSealBroken, match="does not match"):
        load_checks(folder, seal=seal)


def test_red_a_file_the_checks_manifest_does_not_list_is_refused(tmp_path):
    folder, seal = made_up_checks(tmp_path / "checks")
    (folder / "another.py").write_bytes(b"x = 1\n")
    with pytest.raises(ChecksSealBroken, match="another.py"):
        load_checks(folder, seal=seal)


def flown_phase_3(tmp_path, monkeypatch):
    """P3's pass as a phase-3 run, flown by ODIN's own loop with its stand-in, as tests/test_s6_run.py flies it."""
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop
    from tests.test_s6_run import stand_in
    harness = HarnessWorld(tmp_path)
    run = harness.run(phase=3)
    monkeypatch.setattr(signing, "load_private_key", lambda private_key_path=None: harness.world.odin)
    assert run.start()
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(stand_in([])), repo_root=tmp_path)
    odin = threading.Thread(target=lambda: loop.run(max_turns=500), daemon=True)
    odin.start()
    odin.join(120)
    run.stop()
    return run


def test_red_a_phase_3_run_is_scored_by_the_sealed_checks_and_only_with_them(tmp_path, monkeypatch):
    (tmp_path / "world").mkdir()
    run = flown_phase_3(tmp_path / "world", monkeypatch)
    folder, seal = made_up_checks(tmp_path / "checks")
    scored = score_run(run.final, checks=load_checks(folder, seal=seal))
    assert scored["pass"] == "P3" and scored["success"] is True and scored["exercised"] is True
    assert scored["measured"]["records"] > 0 and "wrong_actions" in scored and "system_checks" in scored
    with pytest.raises(ValueError, match="sealed phase-3 checks"):
        score_run(run.final)
