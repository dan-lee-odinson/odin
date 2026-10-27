"""HUGINN runs unchanged (CONTRACT.md §2.2; 00_HANDOFF.md §3.2, S4): the submodule stays at b4dbe61 with
nothing added, and the wrapper's spacecraft is HUGINN's, frame for frame."""

import os
import subprocess
import sys

from tests.repo_checks import REPO_ROOT
from wrapper.huginn import HUGINN, build, load_scenario
from wrapper.simulator import Simulator

PIN = "b4dbe61"


def git(*args):
    return subprocess.run(["git", "-C", str(HUGINN), *args], capture_output=True, text=True, check=True).stdout


def test_huginn_is_at_its_pin_with_nothing_changed_or_added():
    assert git("rev-parse", "HEAD").startswith(PIN)
    assert git("status", "--porcelain", "--ignored") == ""


def test_loading_huginn_writes_no_bytecode_into_its_folders():
    environment = {k: v for k, v in os.environ.items() if k not in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")}
    subprocess.run([sys.executable, "-c", "from wrapper.huginn import build, load_scenario\n"
                    "craft = build(load_scenario('P1_nominal_orbit'))\nfor _ in range(3): craft.step()\n"],
                   cwd=REPO_ROOT, env=environment, check=True)
    assert git("status", "--porcelain", "--ignored") == ""


def test_red_a_cache_file_git_ignores_is_still_seen(tmp_path):
    # The check above lists ignored files too, so a bytecode cache in HUGINN's folders would show.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
                   check=True)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "orbit.cpython-314.pyc").write_bytes(b"\x00")
    status = subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain", "--ignored"],
                            capture_output=True, text=True, check=True).stdout
    assert "__pycache__" in status


def test_the_wrapper_steps_the_same_spacecraft_huginn_runs():
    # With no contact window, no scripted command is dropped and the run is HUGINN's own.
    scenario = load_scenario("P4_hk_generation_halt")
    expected = build(scenario).run(1400)
    simulator = Simulator(scenario, windows=[])
    frames = [simulator.step() for _ in range(1400)]
    assert [f for f in frames if f is not None] == expected
    assert frames[1199] is not None and frames[1200] is None   # the halt latches at 1200


def test_starting_later_steps_huginn_there_first_and_changes_nothing():
    scenario = load_scenario("P3_stuck_load")
    whole = build(scenario).run(900)
    simulator = Simulator(scenario, windows=[], start_at=800)
    assert simulator.met_s == 800
    assert [simulator.step() for _ in range(100)] == whole[800:]
