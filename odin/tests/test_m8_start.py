"""M8: ODIN's start command (one process, frozen instructions, no overrides)."""
import os
from pathlib import Path

import pytest

from odin.devtools.fake_harness import FakeServices
from odin.loop import signing
from odin.run_odin import build_run_adapter, main, verify_frozen
from conftest import bundle_bytes, make_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]


def _services(tmp_path, n=3):
    priv = tmp_path / "k"
    pub = tmp_path / "k.pub"
    signing.generate_keypair_files(priv, pub)
    bundles = [bundle_bytes(make_bundle(i, turn_kind="ACT")) for i in range(1, n + 1)]
    return FakeServices(bundles=bundles, public_key_path=pub), priv


def _run(tmp_path, services, priv, model="stand_in", **kw):
    return main([model], transport=services.transport, repo_root=REPO_ROOT,
                private_key_path=str(priv), urls=("inprocess://fake",) * 3, **kw)


def test_command_runs_until_harness_says_complete(tmp_path, monkeypatch):
    services, priv = _services(tmp_path, 3)
    monkeypatch.setenv("ODIN_KEY_PATH", str(priv))
    code = _run(tmp_path, services, priv)
    assert code == 0
    agent_inputs = [r for r in services.log_records if r["type"] == "AGENT_INPUT"]
    assert len(agent_inputs) == 3  # every turn, not just the first


def test_no_model_call_before_first_turn(tmp_path, monkeypatch):
    services, priv = _services(tmp_path, 0)
    monkeypatch.setenv("ODIN_KEY_PATH", str(priv))
    assert _run(tmp_path, services, priv) == 0
    assert services.log_records == []


def test_endpoint_cannot_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-only")
    for var in ("SPARK_BASE_URL", "OPENAI_BASE_URL", "ODIN_ENDPOINT"):
        monkeypatch.setenv(var, "https://evil.example/v1")
    adapter = build_run_adapter("spark")
    assert adapter.base_url == "https://api.meta.ai/v1"
    services, priv = _services(tmp_path, 1)
    monkeypatch.setenv("ODIN_KEY_PATH", str(priv))
    code = main(["spark", "--base-url", "https://evil.example/v1"],
                transport=services.transport, repo_root=REPO_ROOT,
                private_key_path=str(priv), urls=("inprocess://fake",) * 3)
    assert code != 0


def test_changed_byte_in_instructions_refused(tmp_path):
    base = tmp_path / "odin" / "instructions"
    base.mkdir(parents=True)
    src = REPO_ROOT / "odin" / "instructions"
    (base / "system_prompt.md").write_bytes(
        (src / "system_prompt.md").read_bytes() + b"x")
    (base / "system_prompt.sha256.json").write_bytes(
        (src / "system_prompt.sha256.json").read_bytes())
    (tmp_path / "odin" / "loop").mkdir(parents=True)
    (tmp_path / "odin" / "loop" / "prompt.py").write_bytes(
        (REPO_ROOT / "odin" / "loop" / "prompt.py").read_bytes())
    assert verify_frozen(tmp_path) is False
    assert verify_frozen(REPO_ROOT) is True


def test_cosmos_env_vars_stripped_first(tmp_path, monkeypatch):
    monkeypatch.setenv("ODIN_COSMOS_PASSWORD", "canary-value")
    monkeypatch.setenv("ODIN_COSMOS_USER", "canary-user")
    code = main(["no_such_model"], repo_root=REPO_ROOT)
    assert code != 0  # unknown model, but stripping happened before anything
    assert "ODIN_COSMOS_PASSWORD" not in os.environ
    assert "ODIN_COSMOS_USER" not in os.environ


def test_unknown_model_and_missing_key_exit_nonzero(tmp_path, monkeypatch):
    assert main(["no_such_model"], repo_root=REPO_ROOT) != 0
    monkeypatch.delenv("META_API_KEY", raising=False)
    services, priv = _services(tmp_path, 1)
    code = main(["spark"], transport=services.transport, repo_root=REPO_ROOT,
                private_key_path=str(priv), urls=("inprocess://fake",) * 3)
    assert code != 0
    assert services.log_records == []  # stopped before the first turn


class _SpendStopAdapter:
    name = "spark"

    def complete(self, **kwargs):
        from odin.spend.meter import SpendStop

        raise SpendStop("planted stop for test")


def test_spend_stop_exits_4_and_sends_nothing_more(tmp_path, monkeypatch, capsys):
    services, priv = _services(tmp_path, 3)
    monkeypatch.setenv("META_API_KEY", "test-only")
    monkeypatch.setenv("ODIN_KEY_PATH", str(priv))
    code = main(["spark"], transport=services.transport, repo_root=REPO_ROOT,
                private_key_path=str(priv), urls=("inprocess://fake",) * 3,
                adapter_factory=lambda model: _SpendStopAdapter())
    assert code == 4
    assert "spend stop" in capsys.readouterr().out
    agent_inputs = [r for r in services.log_records if r["type"] == "AGENT_INPUT"]
    assert len(agent_inputs) == 1  # no next turn was asked for


def test_capped_run_exits_5_not_0(tmp_path, monkeypatch, capsys):
    services, priv = _services(tmp_path, 3)
    monkeypatch.setenv("ODIN_KEY_PATH", str(priv))
    code = main(["stand_in"], transport=services.transport, repo_root=REPO_ROOT,
                private_key_path=str(priv), urls=("inprocess://fake",) * 3,
                max_turns=1)
    assert code == 5
    assert "before run_complete" in capsys.readouterr().out


def test_harness_unreachable_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-only")
    priv = tmp_path / "k"
    pub = tmp_path / "k.pub"
    signing.generate_keypair_files(priv, pub)
    monkeypatch.setenv("ODIN_KEY_PATH", str(priv))

    def dead(method, url, data=None):
        raise ConnectionRefusedError("nothing listening")

    code = main(["spark"], transport=dead, repo_root=REPO_ROOT,
                private_key_path=str(priv), urls=("inprocess://fake",) * 3)
    assert code != 0
