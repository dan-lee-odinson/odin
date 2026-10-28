"""M4 follow-ups: U39 long poll, config/models.yaml settings, U43 prompt."""
import hashlib
import json

import pytest
import yaml

from odin.adapters.settings import build_adapter, load_model_settings
from odin.adapters.spark import SparkAdapter
from odin.adapters.spark_open import SparkOpenAdapter
from odin.devtools.fake_harness import FakeServices
from odin.loop import signing
from odin.loop.loop import TurnLoop
from conftest import REPO_ROOT, bundle_bytes, make_bundle

MODELS = REPO_ROOT / "config" / "models.yaml"


# -- follow-up 2: settings from config/models.yaml ---------------------------

def test_settings_come_from_models_yaml():
    settings = load_model_settings(MODELS)
    assert settings["spark"]["reasoning_effort"] == "high"
    assert settings["spark_open"]["reasoning_effort"] == "xhigh"
    assert settings["spark"]["max_output_tokens"] == 32000
    assert settings["spark"]["timeout_s"] == 120


def test_settings_values_are_read_not_hardcoded(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({
        "spark": {"model": "muse-spark-1.3", "reasoning_effort": "low",
                  "max_output_tokens": 111, "timeout_s": 7},
        "spark_open": {"model": "meta-models/muse-spark-open-1026",
                       "reasoning_effort": "medium", "max_output_tokens": 222,
                       "timeout_s": 9},
    }), encoding="utf-8")
    adapter = build_adapter("spark", settings_path=path, api_key="test-only")
    assert isinstance(adapter, SparkAdapter)
    assert (adapter.reasoning_effort, adapter.max_output_tokens, adapter.timeout_s) == ("low", 111, 7)
    adapter2 = build_adapter("spark_open", settings_path=path, api_key="test-only")
    assert isinstance(adapter2, SparkOpenAdapter)
    assert adapter2.reasoning_effort == "medium"


def test_missing_or_incomplete_settings_stop_before_any_call(tmp_path):
    with pytest.raises(RuntimeError):
        load_model_settings(tmp_path / "absent.yaml")
    bad = tmp_path / "models.yaml"
    bad.write_text(yaml.safe_dump({
        "spark": {"model": "muse-spark-1.3", "reasoning_effort": "high",
                  "max_output_tokens": 32000},  # no timeout_s
        "spark_open": {"model": "meta-models/muse-spark-open-1026",
                       "reasoning_effort": "xhigh", "max_output_tokens": 32000,
                       "timeout_s": 120},
    }), encoding="utf-8")
    with pytest.raises(RuntimeError):
        load_model_settings(bad)


# -- follow-up 1: U39 long poll ----------------------------------------------

def test_turn_next_timeout_asks_again_never_crashes(tmp_path, keypair):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    calls = {"n": 0}
    base = services.transport

    def flaky(method, url, data=None):
        if method == "GET" and url.endswith("/turn/next"):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise TimeoutError("long poll timed out")
        return base(method, url, data)

    from odin.adapters.stand_in import StandInAdapter

    loop = TurnLoop(
        harness_url=services.url, baldur_url=services.url, log_url=services.url,
        adapter=StandInAdapter(script=lambda t, b: '{"kind":"none"}'),
        repo_root=tmp_path, transport=flaky, private_key_path=str(keypair["priv"]),
        instructions="x")
    results = loop.run(max_turns=5)
    assert calls["n"] >= 3
    assert results[0]["outcome"] == "none"


# -- follow-up 3: U43 bundle-only prompt + attachment hashes -------------------

def _bundle_with_attachment(text="Frozen COSMOS reference (test)."):
    bundle = make_bundle(1, turn_kind="ACT")
    digest = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    bundle["procedures"][0]["attachments"] = [
        {"name": "COSMOS operations reference (frozen)", "sha256": digest, "text": text}]
    bundle["plan"]["references"] = [
        {"name": "COSMOS operations reference (frozen)", "sha256": digest}]
    return bundle


def _loop(tmp_path, keypair, services, raw='{"kind":"none"}'):
    from odin.adapters.stand_in import StandInAdapter

    return TurnLoop(
        harness_url=services.url, baldur_url=services.url, log_url=services.url,
        adapter=StandInAdapter(script=lambda t, b: raw),
        repo_root=tmp_path, transport=services.transport,
        private_key_path=str(keypair["priv"]), instructions="INSTR-MARKER")


def test_prompt_built_from_bundle_alone_in_order(tmp_path, keypair):
    bundle = _bundle_with_attachment()
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    loop = _loop(tmp_path, keypair, services)
    results = loop.run(max_turns=5)
    assert results[0]["outcome"] == "none"
    body = [r["body"] for r in services.log_records if r["type"] == "AGENT_INPUT"][0]
    prompt = (tmp_path / "runs" / bundle["run_id"] / "inputs"
              / body["prompt_sha256"].split(":")[1]).read_text("utf-8")
    assert prompt.index("INSTR-MARKER") < prompt.index("TYR0-DEV-PASS1-v1")
    assert prompt.index("TYR0-DEV-PASS1-v1") < prompt.index("Frozen COSMOS reference (test).")
    assert prompt.index("Frozen COSMOS reference (test).") < prompt.index("EPS_BATT_V")


def test_attachment_hash_mismatch_ends_turn_no_model_call(tmp_path, keypair):
    bundle = _bundle_with_attachment()
    bundle["procedures"][0]["attachments"][0]["text"] = "tampered reference"
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    loop = _loop(tmp_path, keypair, services)
    results = loop.run(max_turns=5)
    assert results[0]["outcome"] == "attachment_mismatch"
    types = [r["type"] for r in services.log_records]
    assert "CANDIDATE" not in types and "MODEL_CALL" not in types
    assert "MALFORMED" in types  # the mismatch is logged
