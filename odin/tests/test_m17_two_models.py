"""M17: one run, two models, picked by the turn's seat.

Local stubs only: recording adapter doubles, injected http stubs and
the in-process FakeServices. No paid call, no server, no GPU.
"""
import hashlib
import json

import pytest
import yaml

from odin.adapters.glimmer_modal import GlimmerModalAdapter
from odin.adapters.spark import SparkAdapter, act_format, act_format_g
from odin.devtools.fake_harness import FakeServices
from odin.loop.loop import TurnLoop
from odin.run_odin import main as run_main
from odin.spend.meter import SpendMeter
from conftest import REPO_ROOT, bundle_bytes, make_bundle
from freeze_guard import assert_model_blocks_match_frozen, model_block_errors

ANSWER = '{"kind":"none","command_call":null,"escalation":null,"rationale":"stub"}'
PRICES = REPO_ROOT / "config" / "prices.yaml"
KEY_CANARY = "canary-modal-key-1701"
SECRET_CANARY = "canary-modal-secret-1702"


class RecordingAdapter:
    """An adapter double: records the turns it was given, answers none."""

    def __init__(self, name):
        self.name = name
        self.calls = []

    def complete(self, *, prompt, bundle, **kw):
        self.calls.append(bundle["turn_id"])
        return {"raw": ANSWER, "channel": "CONTENT", "status": "OK",
                "provider": "stub", "model_id": "stub-model", "reasoning_effort": "low",
                "max_output_tokens": 10, "latency_s": 0.0, "provider_usage": None,
                "input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1,
                "reasoning_tokens": None}


def _bundle(turn_id, seat):
    bundle = make_bundle(turn_id, turn_kind="ACT")
    bundle["seat"] = seat
    return bundle_bytes(bundle)


def _loop(tmp_path, keypair, services, ground, onboard=None, meter=None):
    return TurnLoop(harness_url=services.url, baldur_url=services.url,
                    log_url=services.url, adapter=ground,
                    onboard_adapter=onboard, repo_root=tmp_path,
                    transport=services.transport,
                    private_key_path=str(keypair["priv"]), instructions="x",
                    meter=meter)


def _run(tmp_path, keypair, seats, ground, onboard=None, meter=None):
    bundles = [_bundle(i + 1, seat) for i, seat in enumerate(seats)]
    services = FakeServices(bundles=bundles, public_key_path=keypair["pub"])
    loop = _loop(tmp_path, keypair, services, ground, onboard, meter)
    results = loop.run(max_turns=10)
    return services, results


def _model_call_configs(services):
    return [r["body"]["config"] for r in services.log_records if r["type"] == "MODEL_CALL"]


# -- the seat picks the adapter --------------------------------------------------

def test_onboard_turn_goes_to_onboard_and_ground_to_run_model(tmp_path, keypair):
    ground, onboard = RecordingAdapter("spark"), RecordingAdapter("glimmer_modal")
    services, results = _run(tmp_path, keypair, ["GROUND", "ONBOARD"], ground, onboard)
    assert [r["outcome"] for r in results] == ["none", "none"]
    assert ground.calls == [1] and onboard.calls == [2]
    assert _model_call_configs(services) == ["spark", "glimmer_modal"]


def test_onboard_turn_without_onboard_adapter_uses_run_model(tmp_path, keypair):
    ground = RecordingAdapter("spark")
    services, results = _run(tmp_path, keypair, ["ONBOARD"], ground, None)
    assert results[0]["outcome"] == "none" and ground.calls == [1]
    assert _model_call_configs(services) == ["spark"]


def test_any_other_seat_uses_run_model(tmp_path, keypair):
    ground, onboard = RecordingAdapter("spark"), RecordingAdapter("glimmer_modal")
    services, _ = _run(tmp_path, keypair, ["GROUND", "SIDEWAYS"], ground, onboard)
    assert ground.calls == [1, 2] and onboard.calls == []


def test_seat_change_between_turns_switches_adapter_each_turn(tmp_path, keypair):
    ground, onboard = RecordingAdapter("spark"), RecordingAdapter("glimmer_modal")
    seats = ["GROUND", "ONBOARD", "ONBOARD", "GROUND", "ONBOARD"]
    services, results = _run(tmp_path, keypair, seats, ground, onboard)
    assert ground.calls == [1, 4] and onboard.calls == [2, 3, 5]
    assert _model_call_configs(services) == [
        "spark", "glimmer_modal", "glimmer_modal", "spark", "glimmer_modal"]


def test_each_adapter_keeps_its_own_format_and_spend_bucket(tmp_path, keypair, monkeypatch):
    monkeypatch.setenv("ODIN_MODAL_PROXY_KEY", KEY_CANARY)
    monkeypatch.setenv("ODIN_MODAL_PROXY_SECRET", SECRET_CANARY)
    captured = {}

    def spark_post(url, headers, body, timeout):
        captured["spark"] = body
        return 200, {"choices": [{"finish_reason": "stop", "message": {"content": ANSWER}}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    def glimmer_post(url, headers, body, timeout):
        captured["glimmer"] = body
        return 200, {"choices": [{"finish_reason": "stop", "message": {"content": ANSWER}}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    ground = SparkAdapter(reasoning_effort="low", max_output_tokens=10, timeout_s=5,
                          api_key="test-only", http_post=spark_post)
    onboard = GlimmerModalAdapter(reasoning_effort="low", max_output_tokens=10,
                                  timeout_s=5, endpoint="http://127.0.0.1:9",
                                  http_post=glimmer_post)
    meter = SpendMeter(ledger_path=tmp_path / "spend.jsonl", prices_path=PRICES)
    services, results = _run(tmp_path, keypair, ["GROUND", "ONBOARD"],
                             ground, onboard, meter)
    assert [r["outcome"] for r in results] == ["none", "none"], results
    from odin.loop.validate import dictionary_for_plan
    commands = dictionary_for_plan({})[1]
    assert captured["spark"]["response_format"]["json_schema"]["schema"] == act_format(commands)
    assert captured["glimmer"]["response_format"]["json_schema"]["schema"] == act_format_g(commands)
    totals = meter.totals()
    assert totals["META_CREDIT"] > 0 and totals["MODAL_CREDIT"] > 0
    assert _model_call_configs(services) == ["spark", "glimmer_modal"]


def test_spend_stop_on_onboard_model_stops_the_run(tmp_path, keypair, monkeypatch):
    monkeypatch.setenv("ODIN_MODAL_PROXY_KEY", KEY_CANARY)
    monkeypatch.setenv("ODIN_MODAL_PROXY_SECRET", SECRET_CANARY)
    meter = SpendMeter(ledger_path=tmp_path / "spend.jsonl", prices_path=PRICES)
    reservation = meter.reserve(config="glimmer_modal", input_tokens=0,
                                max_output_tokens=1, turn_id=0, call_index=1,
                                reserved_usd=124.0)
    reservation.settle(actual_usd=124.0)
    ground = RecordingAdapter("spark")

    def glimmer_post(url, headers, body, timeout):  # never reached: refused first
        raise AssertionError("a refused call must not be sent")

    onboard = GlimmerModalAdapter(reasoning_effort="low", max_output_tokens=10,
                                  timeout_s=2000, endpoint="http://127.0.0.1:9",
                                  http_post=glimmer_post)
    services, results = _run(tmp_path, keypair, ["ONBOARD", "GROUND"],
                             ground, onboard, meter)
    assert results[0]["outcome"] == "spend_stop" and len(results) == 1
    assert ground.calls == []


# -- starting with --onboard --------------------------------------------------------

def _start_env(monkeypatch, keypair):
    monkeypatch.setenv("ODIN_KEY_PATH", str(keypair["priv"]))
    monkeypatch.setenv("META_API_KEY", "test-only")
    monkeypatch.setenv("ODIN_MODAL_PROXY_KEY", KEY_CANARY)
    monkeypatch.setenv("ODIN_MODAL_PROXY_SECRET", SECRET_CANARY)


def test_start_with_onboard_builds_both_and_picks_by_seat(tmp_path, keypair, monkeypatch):
    _start_env(monkeypatch, keypair)
    bundles = [_bundle(1, "GROUND"), _bundle(2, "ONBOARD")]
    services = FakeServices(bundles=bundles, public_key_path=keypair["pub"])
    built = []

    def factory(model):
        built.append(model)
        return RecordingAdapter(model)

    code = run_main(["spark", "--onboard", "glimmer_modal"],
                    transport=services.transport, repo_root=REPO_ROOT,
                    private_key_path=str(keypair["priv"]), urls=(services.url,) * 3,
                    adapter_factory=factory)
    assert code == 0
    assert built == ["spark", "glimmer_modal"]
    assert _model_call_configs(services) == ["spark", "glimmer_modal"]


@pytest.mark.parametrize("missing", ["ODIN_MODAL_PROXY_KEY", "ODIN_MODAL_PROXY_SECRET"])
def test_start_without_onboard_models_key_refused(tmp_path, keypair, monkeypatch, capsys, missing):
    _start_env(monkeypatch, keypair)
    monkeypatch.delenv(missing)

    def factory(model):
        raise AssertionError("no adapter may be built after a start refusal")

    code = run_main(["spark", "--onboard", "glimmer_modal"], repo_root=REPO_ROOT,
                    adapter_factory=factory)
    out = capsys.readouterr().out
    assert code == 2 and missing in out
    assert KEY_CANARY not in out and SECRET_CANARY not in out


def test_start_without_run_models_key_refused_with_onboard(tmp_path, keypair, monkeypatch, capsys):
    _start_env(monkeypatch, keypair)
    monkeypatch.delenv("META_API_KEY")
    code = run_main(["spark", "--onboard", "stand_in"], repo_root=REPO_ROOT,
                    adapter_factory=lambda model: RecordingAdapter(model))
    assert code == 2 and "META_API_KEY" in capsys.readouterr().out


def test_start_onboard_argument_shape(tmp_path, keypair, monkeypatch):
    _start_env(monkeypatch, keypair)
    factory = lambda model: RecordingAdapter(model)
    assert run_main(["spark", "--onboard"], repo_root=REPO_ROOT, adapter_factory=factory) == 2
    assert run_main(["spark", "--onboard", "spark"], repo_root=REPO_ROOT, adapter_factory=factory) == 2
    assert run_main(["spark", "glimmer_modal"], repo_root=REPO_ROOT, adapter_factory=factory) == 2


def test_start_without_onboard_is_unchanged(tmp_path, keypair, monkeypatch):
    _start_env(monkeypatch, keypair)
    monkeypatch.delenv("ODIN_MODAL_PROXY_KEY")
    monkeypatch.delenv("ODIN_MODAL_PROXY_SECRET")
    services = FakeServices(bundles=[_bundle(1, "ONBOARD")], public_key_path=keypair["pub"])
    code = run_main(["stand_in"], transport=services.transport, repo_root=REPO_ROOT,
                    private_key_path=str(keypair["priv"]), urls=(services.url,) * 3)
    assert code == 0  # no onboard model: the run's model flies every seat


# -- freeze guards, against config/frozen.json ---------------------------------------

def test_freeze_guard_passes_on_todays_config():
    assert_model_blocks_match_frozen(
        REPO_ROOT / "config" / "models.yaml", REPO_ROOT / "config" / "frozen.json")


def test_freeze_guard_passes_with_one_more_model_and_its_entry(tmp_path):
    models = yaml.safe_load((REPO_ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
    frozen = json.loads((REPO_ROOT / "config" / "frozen.json").read_text(encoding="utf-8"))
    block = {"model": "test-glimmer", "reasoning_effort": "low",
             "max_output_tokens": 8192, "timeout_s": 60,
             "endpoint": "http://127.0.0.1:9", "date": "2026-10-30"}
    models["glimmer_modal"] = block
    from freeze_guard import model_block_sha256
    frozen["models"]["glimmer_modal"] = model_block_sha256(block)
    models_path, frozen_path = tmp_path / "models.yaml", tmp_path / "frozen.json"
    models_path.write_text(yaml.safe_dump(models), encoding="utf-8")
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    assert model_block_errors(models_path, frozen_path) == []


def test_freeze_guard_names_a_changed_settings_block(tmp_path):
    models = yaml.safe_load((REPO_ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
    frozen = json.loads((REPO_ROOT / "config" / "frozen.json").read_text(encoding="utf-8"))
    models["spark"]["reasoning_effort"] = "low"
    models_path, frozen_path = tmp_path / "models.yaml", tmp_path / "frozen.json"
    models_path.write_text(yaml.safe_dump(models), encoding="utf-8")
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    assert any("spark" in e for e in model_block_errors(models_path, frozen_path))
