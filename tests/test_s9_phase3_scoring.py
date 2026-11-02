"""S9, piece 9: S8's phase-3 checks are read where they are sealed (eval/phase3.py), outside the repository, only
after their manifest hashes to the scoring checks' seal in phase3/SEAL.md, every file it lists matches, and their
folder holds nothing else; then they score a phase-3 run (eval/results.py). Committed in phase3/ after the runs, a
harness file beside them may differ from its manifest only as phase3/SEAL.md names it (RULINGS.md item 25). On made-up
checks; tests/test_phase3_seal.py reads the committed ones."""

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


# After the runs the checks are committed in phase3/ with one line of each harness file changed, which phase3/SEAL.md
# names with its sealed and committed SHA-256 (the Director's selections of 1 November 2026). Made up here too.
HARNESS = b'"""A made-up harness beside the checks."""\nREPO = "where the checks were built"\nCASES = []\n'
COMMITTED_HARNESS = HARNESS.replace(b'"where the checks were built"', b'"found from the file\'s own place"')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def committed_checks(tmp_path, rows=("show_red_phase3.py",), module=MADE_UP.encode("utf-8")):
    """Made-up checks and a harness file, sealed, then committed with the harness's one line changed and the module as
    given, beside a made-up phase3/SEAL.md whose committed table names the files in rows: returns (folder, SEAL.md)."""
    folder = tmp_path / "checks"
    folder.mkdir(parents=True)
    sealed = {"phase3_checks.py": MADE_UP.encode("utf-8"), "show_red_phase3.py": HARNESS}
    committed = {"phase3_checks.py": module, "show_red_phase3.py": COMMITTED_HARNESS}
    manifest = "".join(f"{sha(sealed[name])}  {name}\n" for name in sorted(sealed)).encode("utf-8")
    (folder / "MANIFEST.sha256").write_bytes(manifest)
    for name, data in committed.items():
        (folder / name).write_bytes(data)
    table = "".join(f"| `checks/{name}` | 2 | `{sha(sealed[name])}` | `{sha(committed[name])}` | `{'0' * 64}` |\n"
                    for name in rows)
    seal_md = tmp_path / "SEAL.md"
    seal_md.write_bytes((f"# Phase 3's seal\n\n## The scoring checks' seal\n\n```\nsha256:{sha(manifest)}\n```\n\n"
                         f"## Committed after the held-out runs\n\n| File | Line | Sealed | Committed | Without it |\n"
                         f"|---|---|---|---|---|\n{table}").encode("utf-8"))
    return folder, seal_md


def test_red_committed_checks_with_a_harness_line_seal_md_names_are_read(tmp_path):
    folder, seal_md = committed_checks(tmp_path)
    assert load_checks(folder, seal_path=seal_md).check("P3", [], {}, [])["success"]


def test_red_committed_checks_whose_manifest_is_not_their_seal_are_refused(tmp_path):
    folder, seal_md = committed_checks(tmp_path)
    with pytest.raises(ChecksSealBroken, match="not their seal"):
        load_checks(folder, seal="sha256:" + "00" * 32, seal_path=seal_md)


def test_red_committed_checks_whose_scoring_module_changed_by_one_byte_are_refused_even_if_seal_md_names_it(tmp_path):
    folder, seal_md = committed_checks(tmp_path, rows=("phase3_checks.py", "show_red_phase3.py"),
                                       module=MADE_UP.replace('"Z"', '"Y"').encode("utf-8"))
    with pytest.raises(ChecksSealBroken, match="the module that scores is read only as sealed"):
        load_checks(folder, seal_path=seal_md)


def test_red_a_harness_file_that_differs_from_the_hash_seal_md_gives_is_refused(tmp_path):
    folder, seal_md = committed_checks(tmp_path)
    (folder / "show_red_phase3.py").write_bytes(COMMITTED_HARNESS + b"CASES.append(None)\n")
    with pytest.raises(ChecksSealBroken, match="names no committed copy"):
        load_checks(folder, seal_path=seal_md)


def test_red_a_changed_harness_file_seal_md_does_not_name_is_refused(tmp_path):
    folder, seal_md = committed_checks(tmp_path, rows=())
    with pytest.raises(ChecksSealBroken, match="names no committed copy"):
        load_checks(folder, seal_path=seal_md)


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
