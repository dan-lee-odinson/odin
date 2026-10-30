"""M16: Glimmer's own answer format G, and the timed-out call flag.

Every test is local: injected stub posts/gets and the in-process
FakeServices. No paid call, no server is run, no GPU is used. Proxy
values are test canaries in the process env only.
"""
import hashlib
import inspect
import json
import threading

import pytest
import yaml

import odin.adapters.glimmer_modal as glimmer_modal_module
from odin.adapters.glimmer_local import GlimmerLocalAdapter
from odin.adapters.glimmer_modal import GlimmerModalAdapter
from odin.adapters.settings import build_adapter
from odin.adapters.spark import SparkAdapter, act_format, act_format_g
from odin.adapters.spark_open import SparkOpenAdapter
from odin.devtools.fake_harness import FakeServices
from odin.loop.loop import TurnLoop, judge_act_text
from odin.loop.validate import dictionary_for_plan, validate_instance
from odin.spend.meter import SpendMeter
from conftest import REPO_ROOT, bundle_bytes, make_bundle

INST_REF = "sha256:1a113f774b043bc3a0939a8285e61475a35d3d268792b71f29fa8c7bae0ab53c"
KEY_CANARY = "canary-modal-key-1601"
SECRET_CANARY = "canary-modal-secret-1602"
SLOTS_CANARY = "canary-slots-payload-1603"
ANSWER = ('{  "kind" : "none" , "command_call" : null , '
          '"escalation" : null , "rationale" : "stub" }')
PRICES = REPO_ROOT / "config" / "prices.yaml"


def _commands(*refs):
    plan = {"plan_id": "P", "references": [{"name": f"r{i}", "sha256": r} for i, r in enumerate(refs)]}
    return dictionary_for_plan(plan)[1]


def _load(name):
    return json.loads((REPO_ROOT / "contract" / "m16" / name).read_text(encoding="utf-8"))


@pytest.fixture()
def proxy_env(monkeypatch):
    monkeypatch.setenv("ODIN_MODAL_PROXY_KEY", KEY_CANARY)
    monkeypatch.setenv("ODIN_MODAL_PROXY_SECRET", SECRET_CANARY)


class PostStub:
    def __init__(self, content=ANSWER, block=None):
        self.records = []
        self.content = content
        self.block = block
        self.returned = threading.Event()

    def __call__(self, url, headers, body, timeout):
        self.records.append({"url": url, "headers": dict(headers), "body": body})
        if self.block is not None:
            self.block.wait(timeout=10)
        self.returned.set()
        return 200, {"choices": [{"finish_reason": "stop",
                                  "message": {"content": self.content}}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def _modal(endpoint, post, **kw):
    kw.setdefault("reasoning_effort", "low")
    kw.setdefault("max_output_tokens", 8192)
    kw.setdefault("timeout_s", 9)
    return GlimmerModalAdapter(endpoint=endpoint, http_post=post, **kw)


def _spark_captured(reply=ANSWER, bundle=None, adapter_cls=SparkAdapter, **kw):
    captured = {}

    def fake_post(url, headers, payload, timeout):
        captured.update(url=url, headers=headers, body=payload)
        msg = {"content": reply}
        if adapter_cls is SparkOpenAdapter:
            msg = {"content": reply, "tool_calls": []}
        return 200, {"choices": [{"finish_reason": "stop", "message": msg}], "usage": {}}

    adapter = adapter_cls(reasoning_effort="low", max_output_tokens=10, timeout_s=5,
                          api_key="test-only", http_post=fake_post, **kw)
    adapter.complete(prompt=b"p", bundle=bundle or make_bundle(1, turn_kind="ACT"))
    return captured


# -- format G, sent only to Glimmer ----------------------------------------------

def test_format_g_equals_huginn_and_inst_files_as_parsed_json():
    assert act_format_g(_commands()) == _load("format-G-HUGINN.json")
    assert act_format_g(_commands(INST_REF)) == _load("format-G-INST.json")


def test_glimmer_modal_sends_format_g_not_r(proxy_env):
    post = PostStub()
    result = _modal("http://127.0.0.1:9", post).complete(
        prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"))
    assert result["raw"] == ANSWER
    sent = post.records[0]["body"]["response_format"]
    assert sent["type"] == "json_schema"
    assert sent["json_schema"]["schema"] == _load("format-G-HUGINN.json")
    assert sent["json_schema"]["schema"] != act_format(_commands())


def test_glimmer_local_sends_format_g(proxy_env):
    post = PostStub()
    adapter = GlimmerLocalAdapter(reasoning_effort="low", max_output_tokens=10,
                                  timeout_s=5, endpoint="http://127.0.0.1:9",
                                  http_post=post)
    adapter.complete(prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"))
    sent = post.records[0]["body"]["response_format"]["json_schema"]["schema"]
    assert sent == _load("format-G-HUGINN.json")


def test_glimmer_modal_inst_dictionary_sends_inst_g(proxy_env):
    bundle = make_bundle(1, turn_kind="ACT")
    bundle["plan"]["references"].append({"name": "INST dictionary", "sha256": INST_REF})
    post = PostStub()
    _modal("http://127.0.0.1:9", post).complete(prompt=b"p", bundle=bundle)
    assert post.records[0]["body"]["response_format"]["json_schema"]["schema"] == \
        _load("format-G-INST.json")


def test_spark_still_sends_format_r_not_g():
    captured = _spark_captured()
    sent = captured["body"]["response_format"]["json_schema"]["schema"]
    expected_r = json.loads(
        (REPO_ROOT / "contract" / "m15" / "format-R-HUGINN.json").read_text(encoding="utf-8"))
    assert sent == expected_r
    assert sent != _load("format-G-HUGINN.json")


def test_spark_open_still_sends_no_format_g():
    captured = _spark_captured(adapter_cls=SparkOpenAdapter)
    body = captured["body"]
    assert "response_format" not in body
    assert json.dumps(body) != json.dumps(_load("format-G-HUGINN.json"))
    names = [t["function"]["name"] for t in body["tools"]]
    assert "answer_command" in names


def test_candidate_is_exact_text_from_glimmer(tmp_path, keypair, proxy_env):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    post = PostStub()
    loop = TurnLoop(harness_url=services.url, baldur_url=services.url, log_url=services.url,
                    adapter=_modal("http://127.0.0.1:9", post), repo_root=tmp_path,
                    transport=services.transport, private_key_path=str(keypair["priv"]),
                    instructions="x")
    results = loop.run(max_turns=3)
    assert results[0]["outcome"] == "none", results
    cand = [r["body"] for r in services.log_records if r["type"] == "CANDIDATE"]
    assert cand and cand[0]["raw"] == ANSWER


# -- the recorded judgements ------------------------------------------------------

def test_answers_g_judged_exactly_as_recorded():
    records = _load("answers-G.json")["answers"]
    assert len(records) == 9
    for rec in records:
        ok, obj, reason, detail = judge_act_text(rec["content"], commands=_commands())
        expected_kind = rec["loop_judged"].split()[-1]
        assert rec["format_G"] == "matches" and rec["finish_reason"] == "stop"
        assert ok, (rec["prompt"], reason, detail)
        assert obj["kind"] == expected_kind, rec["prompt"]


def test_escalations_g_judged_and_admitted_exactly_as_recorded():
    records = _load("escalations-G.json")
    assert len(records) == 10
    fmt_g = act_format_g(_commands())
    for rec in records:
        ok, obj, reason, _ = judge_act_text(json.dumps(rec["answer"]), commands=_commands())
        admitted = validate_instance(rec["answer"], fmt_g, "format-g") == []
        if rec["format_G"] == "matches":
            kind = rec["loop_judged"].split()[-1]
            assert admitted and ok and obj["kind"] == kind, rec["case"]
        else:
            assert not admitted and not ok and reason == "SCHEMA_VIOLATION", rec["case"]


def test_checks_g_judged_and_admitted_exactly_as_recorded():
    records = _load("checks-G.json")
    assert len(records) == 36
    fmt_g, fmt_r = act_format_g(_commands()), act_format(_commands())
    for rec in records:
        ok, obj, reason, _ = judge_act_text(json.dumps(rec["answer"]), commands=_commands())
        assert validate_instance(rec["answer"], fmt_r, "format-r") == []  # R admits all 36
        admitted_g = validate_instance(rec["answer"], fmt_g, "format-g") == []
        if rec["loop_judged"] == "accepted":
            assert ok and admitted_g and rec["format_G"] == "matches", rec["prompt"]
        else:
            assert rec["loop_judged"] == "SCHEMA_VIOLATION"
            assert not ok and reason == "SCHEMA_VIOLATION" and not admitted_g, rec["prompt"]


# -- settings: the model block, not the old endpoint file ---------------------------

def test_endpoint_comes_from_model_block_in_test_configuration(tmp_path, proxy_env):
    post = PostStub()
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({
        "glimmer_modal": {"model": "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf",
                          "reasoning_effort": "low", "max_output_tokens": 8192,
                          "timeout_s": 60, "endpoint": "http://127.0.0.1:9",
                          "gpu": "H100"}}), encoding="utf-8")
    adapter = build_adapter("glimmer_modal", settings_path=path, http_post=post)
    assert adapter.base_url == "http://127.0.0.1:9"  # the block, not the old file
    assert adapter.timeout_s == 60 and adapter.max_output_tokens == 8192
    assert adapter.reasoning_effort == "low"
    adapter.complete(prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"))
    assert post.records[0]["url"] == "http://127.0.0.1:9/v1/chat/completions"


def test_endpoint_is_not_read_from_old_file(proxy_env):
    source = inspect.getsource(glimmer_modal_module)
    assert "glimmer_modal.yaml" not in source
    with pytest.raises(RuntimeError) as excinfo:
        GlimmerModalAdapter(reasoning_effort="low", max_output_tokens=1, timeout_s=1)
    assert "endpoint" in str(excinfo.value)


# -- a timed-out call: TIMEOUT only while the server is processing -------------------

class SlotsStub:
    def __init__(self, payload=None, error=None, post=None):
        self.payload = payload
        self.error = error
        self.post = post
        self.records = []

    def __call__(self, url, headers, timeout):
        self.records.append({"url": url, "headers": dict(headers),
                             "post_still_open": not self.post.returned.is_set()})
        if self.error is not None:
            raise self.error
        return 200, self.payload


def _timed_out_adapter(post, slots, timeout_s=0.3):
    return GlimmerModalAdapter(reasoning_effort="low", max_output_tokens=10,
                               timeout_s=timeout_s, endpoint="http://127.0.0.1:9",
                               http_post=post, http_get=slots)


def test_timeout_while_processing_logs_timeout(proxy_env):
    release = threading.Event()
    post = PostStub(block=release)
    slots = SlotsStub(payload=[{"is_processing": True, "detail": SLOTS_CANARY}], post=post)
    sink = []
    try:
        with pytest.raises((TimeoutError, RuntimeError)):
            _timed_out_adapter(post, slots).complete(
                prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"), model_call_sink=sink)
    finally:
        release.set()
    assert slots.records and slots.records[0]["url"].endswith("/slots")
    assert slots.records[0]["post_still_open"]  # asked while the call was still open
    assert slots.records[0]["headers"].get("Modal-Key") == KEY_CANARY
    assert sink[0]["status"] == "TIMEOUT"
    assert sink[0]["latency_s"] >= 0.3
    assert SLOTS_CANARY not in json.dumps(sink)


@pytest.mark.parametrize("payload,error", [
    ([{"is_processing": False}], None),
    (None, ConnectionError("refused")),
])
def test_timeout_when_not_processing_or_refused_logs_error(proxy_env, payload, error):
    release = threading.Event()
    post = PostStub(block=release)
    slots = SlotsStub(payload=payload, error=error, post=post)
    sink = []
    try:
        with pytest.raises((TimeoutError, RuntimeError)):
            _timed_out_adapter(post, slots).complete(
                prompt=b"p", bundle=make_bundle(1, turn_kind="ACT"), model_call_sink=sink)
    finally:
        release.set()
    assert sink[0]["status"] == "ERROR"


def test_timeout_through_loop_writes_no_key_or_slots_payload(tmp_path, keypair, proxy_env):
    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)], public_key_path=keypair["pub"])
    release = threading.Event()
    post = PostStub(block=release)
    slots = SlotsStub(payload=[{"is_processing": True, "prompt": SLOTS_CANARY}], post=post)
    meter = SpendMeter(ledger_path=tmp_path / "spend.jsonl", prices_path=PRICES)
    adapter = GlimmerModalAdapter(reasoning_effort="low", max_output_tokens=10,
                                  timeout_s=0.3, endpoint="http://127.0.0.1:9",
                                  http_post=post, http_get=slots)
    loop = TurnLoop(harness_url=services.url, baldur_url=services.url, log_url=services.url,
                    adapter=adapter, repo_root=tmp_path, transport=services.transport,
                    private_key_path=str(keypair["priv"]), instructions="x", meter=meter)
    try:
        results = loop.run(max_turns=3)
    finally:
        release.set()
    assert results[0]["outcome"] == "error", results
    calls = [r["body"] for r in services.log_records if r["type"] == "MODEL_CALL"]
    assert calls and calls[0]["status"] == "TIMEOUT"
    blobs = [json.dumps(services.log_records).encode()]
    for path in tmp_path.rglob("*"):
        if path.is_file():
            blobs.append(path.read_bytes())
    for blob in blobs:
        assert KEY_CANARY.encode() not in blob
        assert SECRET_CANARY.encode() not in blob
        assert SLOTS_CANARY.encode() not in blob


def test_frozen_files_six_schemas_and_models_unchanged():
    record = json.loads((REPO_ROOT / "odin" / "instructions" / "system_prompt.sha256.json").read_text(encoding="utf-8"))
    files = {
        record["sha256"]: REPO_ROOT / "odin" / "instructions" / "system_prompt.md",
        record["template_sha256"]: REPO_ROOT / "odin" / "instructions" / "template.md",
        record["prompt_template_sha256"]: REPO_ROOT / "odin" / "loop" / "prompt.py",
    }
    for expected, path in files.items():
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == expected, path
    frozen = json.loads((REPO_ROOT / "config" / "frozen.json").read_text(encoding="utf-8"))
    assert len(frozen["schemas"]) == 6
    for rel, expected in frozen["schemas"].items():
        assert "sha256:" + hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == expected, rel
    # M17: each model's block checked against its frozen.json entry,
    # so a model can be added with its entry without breaking this.
    from freeze_guard import assert_model_blocks_match_frozen
    assert_model_blocks_match_frozen(REPO_ROOT / "config" / "models.yaml",
                                     REPO_ROOT / "config" / "frozen.json")
