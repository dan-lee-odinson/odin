"""ODIN flown as its own process (M8, MC-M8-01): the harness starts Muse Code's start command,
python -m odin.run_odin <model>, with the run's model and an environment without COSMOS's credentials (U38),
waits for it to exit, and ends the run by its exit code. 0 comes only once ODIN was told run_complete, so the
run has ended COMPLETE; 4, after a spend stop, ends it as SPEND_STOP; 2, 3 and 5 end it as ERROR, with ODIN's
exit as RUN_END's detail."""

import json
import os
import secrets
import shutil
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
