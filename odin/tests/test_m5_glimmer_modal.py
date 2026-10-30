"""M5 prep: the glimmer_modal adapter (Modal, onboard fallback).

Every test talks only to a local stub: an HTTP stub server on this
machine, or an injected http_post double. No Modal server is started,
warmed or stopped, no GPU is used, and no paid call is made. The two
proxy values are test canaries set only in the test process env.
"""
import ast
import inspect
import json

import pytest
import yaml

from odin.adapters.glimmer_modal import GlimmerModalAdapter, load_glimmer_endpoint
from odin.adapters.settings import build_adapter
from odin.adapters.spark import act_format
from odin.devtools.fake_harness import FakeServices
from odin.loop.loop import TurnLoop
from odin.loop.validate import dictionary_for_plan
from odin.run_odin import main as run_main
from odin.spend.meter import CONFIG_BUCKET, CONFIG_STOP, STOPS, SpendMeter, SpendStop
from conftest import REPO_ROOT, bundle_bytes, make_bundle

KEY_CANARY = "canary-modal-key-0001"
SECRET_CANARY = "canary-modal-secret-0002"
ANSWER = ('{  "kind" : "none" , "command_call" : null , '
          '"escalation" : null , "rationale" : "stub" }')
PRICES = REPO_ROOT / "config" / "prices.yaml"


def _price():
    return yaml.safe_load(PRICES.read_text(encoding="utf-8"))["glimmer_modal"]["per_gpu_second"]


class StubServer:
    """A local OpenAI-compatible stub server double. This sandbox
    forbids listening sockets, so the stub is injected as the adapter's
    http_post: it records url, headers and body exactly as a server
    would see them, and answers locally. Nothing leaves this machine."""

    def __init__(self, content=ANSWER):
        self.records = []
        self.content = content
        self.url = "http://127.0.0.1:9"

    def post(self, url, headers, body, timeout):
        self.records.append({"url": url, "headers": dict(headers), "body": body})
        return 200, {"choices": [{"finish_reason": "stop",
                                  "message": {"content": self.content}}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


@pytest.fixture()
def proxy_env(monkeypatch):
    monkeypatch.setenv("ODIN_MODAL_PROXY_KEY", KEY_CANARY)
    monkeypatch.setenv("ODIN_MODAL_PROXY_SECRET", SECRET_CANARY)


def _adapter(endpoint, **kw):
    kw.setdefault("reasoning_effort", "low")
    kw.setdefault("max_output_tokens", 123)
    kw.setdefault("timeout_s", 9)
    return GlimmerModalAdapter(endpoint=endpoint, **kw)


def _commands():
    return dictionary_for_plan({})[1]


# -- the request that goes out -------------------------------------------------

def test_request_to_configured_endpoint_with_headers_and_json_schema(proxy_env):
    stub = StubServer()
    result = _adapter(stub.url, http_post=stub.post).complete(
        prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"))
    assert result["raw"] == ANSWER and result["channel"] == "CONTENT"
    assert len(stub.records) == 1
    rec = stub.records[0]
    assert rec["url"] == stub.url + "/v1/chat/completions"
    assert rec["headers"].get("Modal-Key") == KEY_CANARY
    assert rec["headers"].get("Modal-Secret") == SECRET_CANARY
    body = rec["body"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == act_format(_commands())
    assert body["max_tokens"] == 123 and body["reasoning_effort"] == "low"


def test_report_turn_uses_report_json_schema(proxy_env):
    stub = StubServer(content='{"timeline":[]}')
    _adapter(stub.url, http_post=stub.post).complete(
        prompt=b"p", bundle=make_bundle(1, turn_kind="REPORT", report_kind="PASS_START"))
    fmt = stub.records[0]["body"]["response_format"]
    assert fmt["type"] == "json_schema" and "timeline" in fmt["json_schema"]["schema"]["properties"]


def test_endpoint_defaults_to_config_glimmer_modal_yaml(proxy_env):
    expected = yaml.safe_load(
        (REPO_ROOT / "config" / "glimmer_modal.yaml").read_text(encoding="utf-8"))["endpoint"]
    assert load_glimmer_endpoint() == expected
    assert _adapter(None).base_url == expected


def test_adapter_given_no_settings_raises():
    with pytest.raises((ValueError, TypeError)):
        GlimmerModalAdapter()
    with pytest.raises(ValueError):
        GlimmerModalAdapter(reasoning_effort=None, max_output_tokens=1, timeout_s=1,
                            endpoint="http://127.0.0.1:9")


def test_build_adapter_from_test_configuration(tmp_path, proxy_env):
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({
        "glimmer_modal": {"model": "test-glimmer", "reasoning_effort": "medium",
                          "max_output_tokens": 77, "timeout_s": 3}}), encoding="utf-8")
    stub = StubServer()
    adapter = build_adapter("glimmer_modal", settings_path=path,
                            endpoint=stub.url, http_post=stub.post)
    assert isinstance(adapter, GlimmerModalAdapter)
    assert (adapter.reasoning_effort, adapter.max_output_tokens, adapter.timeout_s) == \
        ("medium", 77, 3)
    adapter.complete(prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"))
    assert stub.records[0]["body"]["model"] == "test-glimmer"
    assert stub.records[0]["body"]["max_tokens"] == 77


# -- the proxy values never leak, and missing ones refuse -----------------------

def test_key_values_never_in_log_ledger_or_files(tmp_path, keypair, proxy_env):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    services.start()
    meter = SpendMeter(ledger_path=tmp_path / "spend.jsonl", prices_path=PRICES)
    stub = StubServer()
    loop = TurnLoop(harness_url=services.url, baldur_url=services.url,
                    log_url=services.url, adapter=_adapter(stub.url, http_post=stub.post),
                    repo_root=tmp_path, transport=services.transport,
                    private_key_path=str(keypair["priv"]), instructions="x", meter=meter)
    try:
        results = loop.run(max_turns=3)
    finally:
        services.stop()
    assert results[0]["outcome"] == "none", results
    cand = [r["body"] for r in services.log_records if r["type"] == "CANDIDATE"]
    assert cand and cand[0]["raw"] == ANSWER  # CANDIDATE is the exact text
    written = []
    for path in tmp_path.rglob("*"):
        if path.is_file():
            written.append(path.read_bytes())
    written.append(json.dumps(services.log_records).encode())
    written.append((tmp_path / "spend.jsonl").read_bytes())
    for blob in written:
        assert KEY_CANARY.encode() not in blob
        assert SECRET_CANARY.encode() not in blob


@pytest.mark.parametrize("missing", ["ODIN_MODAL_PROXY_KEY", "ODIN_MODAL_PROXY_SECRET"])
def test_missing_proxy_variable_refuses_before_any_request(missing, monkeypatch):
    monkeypatch.setenv("ODIN_MODAL_PROXY_KEY", KEY_CANARY)
    monkeypatch.setenv("ODIN_MODAL_PROXY_SECRET", SECRET_CANARY)
    monkeypatch.delenv(missing)
    stub = StubServer()
    with pytest.raises(RuntimeError) as excinfo:
        _adapter(stub.url, http_post=stub.post).complete(
            prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"))
    assert missing in str(excinfo.value)
    assert KEY_CANARY not in str(excinfo.value) and SECRET_CANARY not in str(excinfo.value)
    assert stub.records == []


@pytest.mark.parametrize("missing", ["ODIN_MODAL_PROXY_KEY", "ODIN_MODAL_PROXY_SECRET"])
def test_missing_proxy_variable_refuses_at_start(missing, tmp_path, keypair,
                                                 monkeypatch, capsys):
    monkeypatch.setenv("ODIN_MODAL_PROXY_KEY", KEY_CANARY)
    monkeypatch.setenv("ODIN_MODAL_PROXY_SECRET", SECRET_CANARY)
    monkeypatch.delenv(missing)
    monkeypatch.setenv("ODIN_KEY_PATH", str(keypair["priv"]))

    def factory(model):
        raise AssertionError("adapter must not be built after a start refusal")

    code = run_main(["glimmer_modal"], repo_root=REPO_ROOT,
                    transport=None, urls=("http://127.0.0.1:9",) * 3,
                    adapter_factory=factory)
    out = capsys.readouterr().out
    assert code == 2 and missing in out
    assert KEY_CANARY not in out and SECRET_CANARY not in out


def test_run_odin_glimmer_modal_completes_a_run(tmp_path, keypair, proxy_env, monkeypatch):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    services.start()
    monkeypatch.setenv("ODIN_KEY_PATH", str(keypair["priv"]))

    class Stub:
        name = "glimmer_modal"
        def complete(self, *, prompt, bundle, **kw):
            return {"raw": ANSWER, "channel": "CONTENT", "status": "OK"}

    try:
        code = run_main(["glimmer_modal"], transport=services.transport, repo_root=REPO_ROOT,
                        private_key_path=str(keypair["priv"]),
                        urls=(services.url,) * 3, adapter_factory=lambda model: Stub())
    finally:
        services.stop()
    assert code == 0
    cand = [r["body"] for r in services.log_records if r["type"] == "CANDIDATE"]
    assert cand and cand[0]["raw"] == ANSWER


# -- the meter: GPU-seconds, and the $125 Modal stop ------------------------------

class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_charge_is_gpu_seconds_times_price(tmp_path, proxy_env):
    clock = _Clock()
    captured = {}

    def fake_post(url, headers, payload, timeout):
        captured.update(url=url, headers=headers, payload=payload)
        clock.now += 4.0
        return 200, {"choices": [{"finish_reason": "stop", "message": {"content": ANSWER}}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    meter = SpendMeter(ledger_path=tmp_path / "spend.jsonl", prices_path=PRICES)
    sink = []
    adapter = _adapter("http://127.0.0.1:9", http_post=fake_post, monotonic=clock)
    result = adapter.complete(prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"),
                              meter=meter, model_call_sink=sink)
    expected = 4.0 * _price()
    assert result["raw"] == ANSWER
    assert sink[0]["actual_cost_usd"] == pytest.approx(expected)
    assert sink[0]["pays_from"] == "MODAL_CREDIT"
    assert meter.totals()["MODAL_CREDIT"] == pytest.approx(expected)
    ledger = (tmp_path / "spend.jsonl").read_text(encoding="utf-8")
    assert KEY_CANARY not in ledger and SECRET_CANARY not in ledger


def test_modal_stop_is_125_and_glimmer_modal_maps_to_it(tmp_path):
    assert STOPS["MODAL"] == 125.0
    assert CONFIG_STOP["glimmer_modal"] == "MODAL"
    assert CONFIG_BUCKET["glimmer_modal"] == "MODAL_CREDIT"


def test_call_that_would_pass_125_is_refused(tmp_path, proxy_env):
    meter = SpendMeter(ledger_path=tmp_path / "spend.jsonl", prices_path=PRICES)
    reservation = meter.reserve(config="glimmer_modal", input_tokens=0, max_output_tokens=1,
                                turn_id=1, call_index=1, reserved_usd=124.0)
    assert reservation is not None
    reservation.settle(actual_usd=124.0)
    calls = []

    def fake_post(url, headers, payload, timeout):
        calls.append(url)
        return 200, {"choices": [{"message": {"content": ANSWER}}], "usage": {}}

    sink = []
    # Worst case for one call is its timeout in GPU-seconds: 2000 s of
    # them costs more than the $1 left under the stop.
    adapter = _adapter("http://127.0.0.1:9", http_post=fake_post, timeout_s=2000)
    with pytest.raises(SpendStop):
        adapter.complete(prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"),
                         meter=meter, model_call_sink=sink)
    assert calls == []  # refused before anything was sent
    assert sink and sink[0]["status"] == "SPEND_STOP"


# -- no server lifecycle in the adapter ------------------------------------------

def test_adapter_has_no_code_path_that_starts_warms_or_stops_a_server():
    import odin.adapters.glimmer_modal as module

    tree = ast.parse(inspect.getsource(module))
    imported = set()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    assert "modal" not in imported and "subprocess" not in imported
    assert not (called & {"start", "warm", "stop", "deploy", "serve", "spawn", "Popen", "system"})
    assert module.GlimmerModalAdapter.name == "glimmer_modal"
