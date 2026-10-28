"""M3: m3_check against a local fake provider only. Never a paid call."""
import json
from pathlib import Path

import pytest
import yaml

from odin.devtools.fake_provider import FakeProvider
from odin.devtools.m3_check import main, planned_calls, run_check

REPO_ROOT = Path(__file__).resolve().parents[2]
PRICES = yaml.safe_load((REPO_ROOT / "config" / "prices.yaml").read_text(encoding="utf-8"))
_MK = "".join(["META", "_API", "_KEY"])
_BK = "".join(["BASETEN", "_API", "_KEY"])
FAKE_ENV = {_MK: "".join(["CANARY", "-META-", "123"]), _BK: "".join(["CANARY", "-BASETEN-", "456"]),
            "ODIN_KEY_PATH": None}  # filled per-test with a throwaway key


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from odin.loop import signing

    priv = tmp_path / "odin_test_key"
    pub = tmp_path / "odin.pub"
    signing.generate_keypair_files(priv, pub)
    values = dict(FAKE_ENV, ODIN_KEY_PATH=str(priv))
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return {**values, "_pub": str(pub)}


def _run(tmp_path, env, provider, **kwargs):
    return run_check(repo_root=tmp_path, env=dict(env), http_post=provider.post,
                     odin_public_key_path=env["_pub"], **kwargs)


def test_exactly_the_planned_calls_once_each(env, tmp_path):
    provider = FakeProvider()
    result = _run(tmp_path, env, provider)
    planned = planned_calls()
    assert len(provider.calls) == len(planned) == 8
    seen = [(c["model_kind"], c["body"]["reasoning_effort"]) for c in provider.calls]
    expected = [(p["config"], p["reasoning_effort"]) for p in planned]
    assert seen == expected
    for call in provider.calls:
        assert call["body"]["max_tokens"] == 32000
        assert call["timeout"] == 600
    assert len(result["rows"]) == 8
    assert all(row["well_formed"] for row in result["rows"])


def test_canary_keys_appear_nowhere(env, tmp_path, capsys):
    provider = FakeProvider()
    _run(tmp_path, env, provider)
    out_text = capsys.readouterr().out
    files_text = "".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in tmp_path.rglob("*") if p.is_file() and "odin_test_key" not in p.name
    )
    for secret in ("CANARY-META-123", "CANARY-BASETEN-456"):
        assert secret not in out_text
        assert secret not in files_text


def test_missing_key_stops_before_any_call(env, tmp_path, monkeypatch):
    monkeypatch.delenv("META_API_KEY")
    provider = FakeProvider()
    env2 = dict(env)
    del env2["META_API_KEY"]
    with pytest.raises((SystemExit, RuntimeError)) as excinfo:
        _run(tmp_path, env2, provider)
    assert provider.calls == []
    assert "CANARY" not in str(excinfo.value)


def test_dry_run_makes_no_network_call(env, tmp_path, capsys):
    def forbidden(url, headers, body, timeout):
        raise AssertionError("network call during dry run")

    result = run_check(repo_root=tmp_path, env=dict(env), http_post=forbidden,
                       odin_public_key_path=env["_pub"], dry_run=True)
    planned = result["planned"]
    assert len(planned) == 8
    assert result["total_reserved_usd"] == pytest.approx(
        sum(p["reserved_usd"] for p in planned))
    for entry in planned:
        assert entry["max_output_tokens"] == 32000


def test_dry_run_cli_reports_presence_only(env, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code = main(["--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "META_API_KEY: present" in out and "BASETEN_API_KEY: present" in out
    assert "ODIN_KEY_PATH: present" in out
    assert "CANARY" not in out


def test_answer_cut_off_by_cap_recorded(env, tmp_path):
    provider = FakeProvider(cut_off={("spark", "medium")})
    result = _run(tmp_path, env, provider)
    row = [r for r in result["rows"] if r["config"] == "spark" and r["reasoning_effort"] == "medium"][0]
    assert row["cut_off"] is True
    assert row["well_formed"] is False


def test_row_cost_equals_tokens_times_prices(env, tmp_path):
    provider = FakeProvider()
    result = _run(tmp_path, env, provider)
    for row in result["rows"]:
        prices = PRICES[row["config"]]
        expected = (
            (row["input_tokens"] - row["cached_input_tokens"]) * prices["input_per_mtok"]
            + row["cached_input_tokens"] * prices["cached_input_per_mtok"]
            + row["output_tokens"] * prices["output_per_mtok"]
        ) / 1_000_000
        assert row["cost_usd"] == pytest.approx(expected)


def test_not_offered_level_recorded_not_substituted(env, tmp_path):
    provider = FakeProvider(reject_levels={("spark_open", "xhigh")})
    result = _run(tmp_path, env, provider)
    row = [r for r in result["rows"]
           if r["config"] == "spark_open" and r["reasoning_effort"] == "xhigh"][0]
    assert row["well_formed"] is False
    assert "not offered" in row["detail"]
    assert len(provider.calls) == 8  # still exactly one attempt each
