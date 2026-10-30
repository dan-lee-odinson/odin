"""ODIN flown as its own process (M8, MC-M8-01): the harness starts Muse Code's start command,
python -m odin.run_odin <model>, with the run's model and an environment without COSMOS's credentials (U38),
waits for it to exit, and ends the run by its exit code. 0 comes only once ODIN was told run_complete, so the
run has ended COMPLETE; 4, after a spend stop, ends it as SPEND_STOP; 2, 3 and 5 end it as ERROR, with ODIN's
exit as RUN_END's detail."""

import json
import os
import secrets
import shutil
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import serialization

from harness import launch
from harness.launch import fly, odin_command
from tests.harness_world import HarnessWorld, records
from tests.repo_checks import REPO_ROOT

LEDGER = REPO_ROOT / "runs" / "spend.jsonl"


def test_the_command_is_muse_codes_with_the_runs_model():
    assert odin_command("spark") == [sys.executable, "-m", "odin.run_odin", "spark"]


def test_red_a_run_with_an_onboard_model_starts_odin_with_both(tmp_path, monkeypatch):
    # M17: run_odin <model> --onboard <model>. The run's onboard model reaches ODIN's start command.
    assert odin_command("spark", "glimmer_modal") == [sys.executable, "-m", "odin.run_odin", "spark",
                                                      "--onboard", "glimmer_modal"]
    started = []

    def launched(command, **_):
        started.append(command)
        raise RuntimeError("not launched in this test")
    monkeypatch.setattr(launch, "launch_odin", launched)
    run = HarnessWorld(tmp_path).run(onboard="stand_in")
    try:
        with pytest.raises(RuntimeError, match="not launched"):
            fly(run)
    finally:
        run.stop()
    assert started == [[sys.executable, "-m", "odin.run_odin", "stand_in", "--onboard", "stand_in"]]


@pytest.fixture
def at_the_repository_root(tmp_path):
    """A stand-in run whose folder is under the repository's runs/, where ODIN's start command keeps its inputs,
    served on config/ports.yaml's addresses, which the command reads. Its folder is removed afterwards."""
    run_id = f"dev-m8-{secrets.token_hex(4)}"
    harness = HarnessWorld(tmp_path)
    plans = harness.world.plans([harness.plan()], signer="dev")
    act = harness.world.act(plans, runs=[run_id], signer="dev")
    run = harness.run(run_id=run_id, plans=plans, act=act, root=REPO_ROOT, addresses={})
    key = tmp_path / "odin-test-key"
    key.write_bytes(harness.world.odin.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                                     serialization.NoEncryption()))
    environ = {**os.environ, "ODIN_KEY_PATH": str(key), "ODIN_COSMOS_" + "PLANTED": "made-up"}
    ledger = LEDGER.read_bytes() if LEDGER.exists() else None
    yield run, environ
    shutil.rmtree(REPO_ROOT / "runs" / "dev" / run_id, ignore_errors=True)
    shutil.rmtree(REPO_ROOT / "runs" / run_id, ignore_errors=True)
    assert (LEDGER.read_bytes() if LEDGER.exists() else None) == ledger, "the stand-in run touched the spend ledger"


def test_a_stand_in_run_flies_odin_as_its_own_process(at_the_repository_root):
    run, environ = at_the_repository_root
    assert fly(run, environ=environ, timeout_s=120) == 0
    [end] = records(run, "RUN_END")
    assert end["body"] == {"reason": "COMPLETE", "turns": run.turn_id, "detail": None}
    served = {r["body"]["turn_id"]: r["body"]["bundle_sha256"] for r in records(run, "TRIGGER")}
    saved = {r["body"]["turn_id"]: r["body"]["bundle_sha256"] for r in records(run, "AGENT_INPUT")}
    assert served and served == saved
    for digest in served.values():   # ODIN's process kept each bundle it was served in the run's folder
        assert (run.folder / "inputs" / digest.split(":")[1]).exists()
    assert {r["body"]["config"] for r in records(run, "MODEL_CALL")} == {"stand_in"}
    assert run.folder == REPO_ROOT / "runs" / "dev" / run.run_id


@pytest.mark.parametrize("code, reason", [(2, "ERROR"), (3, "ERROR"), (4, "SPEND_STOP"), (5, "ERROR")])
def test_odins_exit_ends_the_run(tmp_path, code, reason):
    run = HarnessWorld(tmp_path).run()
    command = [sys.executable, "-c", f"print('stand-in for ODIN'); raise SystemExit({code})"]
    assert fly(run, command=command, timeout_s=30) == code
    [end] = records(run, "RUN_END")
    assert end["body"]["reason"] == reason
    if reason == "ERROR":
        assert end["body"]["detail"] == f"ODIN exited {code} ({launch.EXITS[code]}): stand-in for ODIN"
    else:
        assert end["body"]["detail"] is None


SPEAKS = "import sys; print('to standard output'); print('to standard error', file=sys.stderr); "


@pytest.mark.parametrize("code", [0, 4, 5])
def test_red_odins_standard_output_and_error_are_kept_whatever_its_exit(tmp_path, code):
    # The Director's ruling of 29 October 2026: kept for every run, beside the run folder.
    run = HarnessWorld(tmp_path).run()
    kept = tmp_path / "odin-output" / run.run_id
    assert fly(run, command=[sys.executable, "-c", SPEAKS + f"raise SystemExit({code})"], timeout_s=30,
               output_dir=kept) == code
    assert (kept / "stdout.txt").read_bytes().decode().splitlines() == ["to standard output"]
    assert (kept / "stderr.txt").read_bytes().decode().splitlines() == ["to standard error"]


def test_red_odins_output_is_kept_when_its_time_is_up(tmp_path):
    run = HarnessWorld(tmp_path).run()
    kept = tmp_path / "odin-output" / run.run_id
    fly(run, command=[sys.executable, "-c", SPEAKS + "sys.stdout.flush(); import time; time.sleep(30)"], timeout_s=2,
        output_dir=kept)
    assert (kept / "stdout.txt").read_bytes().decode().splitlines() == ["to standard output"]
    assert (kept / "stderr.txt").read_bytes().decode().splitlines() == ["to standard error"]


def test_red_git_ignores_odins_output_beside_the_run_folders():
    ignored = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "-q",
                              "runs/odin-output/PH1-SHAKEDOWN-SPARK-R2/stderr.txt"])
    assert ignored.returncode == 0


def test_red_odin_still_running_when_its_time_is_up_ends_the_run_as_error(tmp_path):
    run = HarnessWorld(tmp_path).run()
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    fly(run, command=command, timeout_s=1)
    [end] = records(run, "RUN_END")
    assert (end["body"]["reason"], end["body"]["detail"]) == ("ERROR", "ODIN did not exit within 1 s")


def test_a_run_that_does_not_start_launches_no_odin(tmp_path, monkeypatch):
    harness = HarnessWorld(tmp_path)
    run = harness.run(act=harness.world.act(harness.world.plans([harness.plan()], signer="dev"), runs=["another-run"],
                                            signer="dev"))
    monkeypatch.setattr(launch, "launch_odin", lambda *a, **k: pytest.fail("ODIN was launched"))
    assert fly(run, timeout_s=5) is None
    assert json.loads(json.dumps([r["body"]["reason"] for r in records(run, "RUN_END")])) == ["NOT_ARMED"]
