"""M10: tool-request encoding/errors, and $ref-free schemas for Meta.

Two defects from PH1-SHAKEDOWN-SPARK-R1: tool URLs built by hand raised
InvalidURL on any space and killed the turn; the spark adapter sent the
answer schemas with cross-file $refs Meta cannot follow."""
import hashlib
import json
import urllib.parse
from pathlib import Path

import pytest

from odin.loop.loop import TurnLoop
from odin.loop.validate import resolved_schema, validate_against_schema, validate_instance
from conftest import REPO_ROOT, bundle_bytes, make_bundle

SCHEMAS = REPO_ROOT / "contract" / "schemas"
SIX_SCHEMAS = ["answer.schema.json", "report_body.schema.json", "report.schema.json",
               "turn_bundle.schema.json", "observation.schema.json", "common.schema.json"]
FROZEN_SIX = {
    "answer.schema.json": "sha256:d027563de2e6d2dc6c8e5ef260a183050c10324d3f22d070e3b3f4a300ac2e7e",
    "report_body.schema.json": "sha256:f77c34533d5c5dc4363ce89bf5515930b2503ae78f6007c4834bb84dd811f6c3",
    "report.schema.json": "sha256:47f5d96a217ea1c710a086aef7a7d015691041151e198ad17685c0600dbde1ec",
    "turn_bundle.schema.json": "sha256:5fd78e3c8863f185226662d1b39b2da90b1b059d99a9abb28cb7220d2db5cc62",
    "observation.schema.json": "sha256:922da49688278ad0db9c3376b0006e21f993513dd355bfac5dc4926373cbfabf",
    "common.schema.json": "sha256:5d2cbe916cee8c68a73d89fe4dab29654cfe9085561b620f3e13d378716eb9dc",
}


def _loop(captured, body=b"ok"):
    def transport(method, url, data=None):
        captured.append(url)
        return 200, body

    return TurnLoop(harness_url="http://harness", baldur_url="http://b",
                    log_url="http://l", adapter=None, repo_root=REPO_ROOT,
                    transport=transport)


def _query(url):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)


# -- tool requests --------------------------------------------------------------

def test_docs_query_with_space_reaches_the_harness():
    captured = []
    result = _loop(captured)._tool_handler("docs_lookup", {"q": "EPS battery voltage"})
    assert result == "ok"
    assert captured and _query(captured[0])["q"] == ["EPS battery voltage"]
    assert " " not in captured[0]


def test_points_with_spaces_after_commas_are_normalized():
    captured = []
    _loop(captured)._tool_handler(
        "history", {"points": "EPS_BATT_V, EPS_BATT_SOC", "window_s": 300})
    query = _query(captured[0])
    assert query["points"] == ["EPS_BATT_V,EPS_BATT_SOC"]
    assert query["window_s"] == ["300"]
    assert " " not in captured[0]


def test_points_given_as_a_list_are_joined_not_repr():
    captured = []
    _loop(captured)._tool_handler(
        "history", {"points": ["EPS_BATT_V", "EPS_BATT_SOC"], "window_s": 60})
    assert _query(captured[0])["points"] == ["EPS_BATT_V,EPS_BATT_SOC"]


def test_tool_error_goes_back_as_result_and_to_stderr(capsys):
    def dead(method, url, data=None):
        raise ConnectionError("harness unreachable")

    loop = TurnLoop(harness_url="http://harness", baldur_url="http://b",
                    log_url="http://l", adapter=None, repo_root=REPO_ROOT,
                    transport=dead)
    result = loop._tool_handler("docs_lookup", {"q": "EPS battery"})
    assert "docs_lookup" in result and "harness unreachable" in result
    assert "docs_lookup" in capsys.readouterr().err


def test_tool_error_does_not_end_the_turn(tmp_path, keypair, capsys):
    from odin.devtools.fake_harness import FakeServices

    bundle = make_bundle(1, turn_kind="ACT")
    services = FakeServices(bundles=[bundle_bytes(bundle)],
                            public_key_path=keypair["pub"])
    seen = {}

    class ToolThenNone:
        name = "stand_in"

        def complete(self, *, prompt, bundle, tool_handler=None, **kw):
            seen["result"] = tool_handler("docs_lookup", {"q": "a space here"})
            return {"raw": '{"kind":"none"}', "channel": "CONTENT", "status": "OK"}

    def flaky(method, url, data=None):
        if "/docs/lookup" in url:
            raise ConnectionError("docs service down")
        return services.transport(method, url, data)

    loop = TurnLoop(harness_url=services.url, baldur_url=services.url,
                    log_url=services.url, adapter=ToolThenNone(),
                    repo_root=tmp_path, transport=flaky,
                    private_key_path=str(keypair["priv"]), instructions="x")
    results = loop.run(max_turns=5)
    assert results[0]["outcome"] == "none"  # the turn went on
    assert "docs service down" in seen["result"]
    assert "docs_lookup" in capsys.readouterr().err


def test_harness_refusal_still_goes_back_as_the_result():
    loop = _loop([], body=b'{"problems": ["bad query"]}')
    # A 4xx body is already returned to the model as the tool result.
    def refusing(method, url, data=None):
        return 400, b'{"problems": ["bad query"]}'

    loop.transport = refusing
    assert "bad query" in loop._tool_handler("docs_lookup", {"q": "x"})


# -- structured output schemas ----------------------------------------------------

def _no_refs(node):
    if isinstance(node, dict):
        return "$ref" not in node and all(_no_refs(v) for v in node.values())
    if isinstance(node, list):
        return all(_no_refs(v) for v in node)
    return True


@pytest.mark.parametrize("schema_file", ["answer.schema.json", "report_body.schema.json"])
def test_derived_schema_has_no_ref_left(schema_file):
    assert _no_refs(resolved_schema(schema_file))


@pytest.mark.parametrize("schema_file, examples", [
    ("answer.schema.json", "answer"),
    ("report_body.schema.json", "report_body"),
])
def test_derived_schema_accepts_the_same_examples(schema_file, examples):
    derived = resolved_schema(schema_file)
    files = sorted((SCHEMAS / "examples" / examples).glob("*.json"))
    assert files
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert validate_against_schema(schema_file, doc) == [], path
        assert validate_instance(doc, derived, schema_file) == [], path


@pytest.mark.parametrize("schema_file, bad", [
    ("report_body.schema.json",
     {"timeline": "not-a-list", "actions": [], "condition": {"summary": "x", "evidence": []},
      "deferred": [], "open_issues": []}),
    ("report_body.schema.json",
     {"timeline": [], "actions": "not-a-list", "condition": {"summary": "x", "evidence": []},
      "deferred": [], "open_issues": []}),
    ("report_body.schema.json",
     {"timeline": [], "actions": [], "deferred": [], "open_issues": []}),
    ("report_body.schema.json",
     {"timeline": [], "actions": [], "condition": {"summary": "x", "evidence": []},
      "deferred": [], "open_issues": [], "extra": 1}),
    ("answer.schema.json", {"kind": "none", "extra": 1}),
    ("answer.schema.json", {"kind": "mystery"}),
    ("answer.schema.json", {"kind": "command", "command": "CMD_SAFE_ENTER"}),
    ("answer.schema.json",
     {"kind": "escalation", "escalation_kind": "MALFUNCTION", "refs": [],
      "proposed": None, "urgency": "WHENEVER"}),
])
def test_derived_schema_rejects_the_same_documents(schema_file, bad):
    derived = resolved_schema(schema_file)
    assert validate_against_schema(schema_file, bad) != []
    assert validate_instance(bad, derived, schema_file) != []


def test_derived_and_frozen_agree_on_canonical_vectors():
    vectors = json.loads((SCHEMAS / "canonical_vectors.json")
                         .read_text(encoding="utf-8"))["vectors"]
    assert vectors
    for schema_file in ("answer.schema.json", "report_body.schema.json"):
        derived = resolved_schema(schema_file)
        for vector in vectors:
            value = vector["value"]
            frozen_ok = validate_against_schema(schema_file, value) == []
            derived_ok = validate_instance(value, derived, schema_file) == []
            assert frozen_ok == derived_ok, (schema_file, vector["name"])


def test_spark_sends_the_derived_schema_to_meta():
    from odin.adapters.spark import SparkAdapter

    sent = {}

    def fake_post(url, headers, payload, timeout):
        sent.update(payload)
        return 200, {"choices": [{"finish_reason": "stop",
                                  "message": {"content": '{"kind":"none"}'}}],
                     "usage": {}}

    adapter = SparkAdapter(reasoning_effort="low", max_output_tokens=10,
                           timeout_s=5, api_key="test-only", http_post=fake_post)
    adapter.complete(prompt=b"p", bundle={"turn_id": 1, "turn_kind": "ACT"})
    schema = sent["response_format"]["json_schema"]["schema"]
    assert _no_refs(schema)
    bundle = {"turn_id": 1, "turn_kind": "REPORT", "report_kind": "PASS_START"}
    adapter.complete(prompt=b"p", bundle=bundle)
    schema = sent["response_format"]["json_schema"]["schema"]
    assert _no_refs(schema) and "timeline" in schema["properties"]


def test_spark_open_answer_tools_carry_no_ref():
    from odin.adapters.spark_open import ANSWER_TOOLS

    assert "$ref" not in json.dumps(ANSWER_TOOLS)


def test_six_schemas_and_models_yaml_unchanged():
    for name in SIX_SCHEMAS:
        digest = "sha256:" + hashlib.sha256((SCHEMAS / name).read_bytes()).hexdigest()
        assert digest == FROZEN_SIX[name], name
    models = hashlib.sha256((REPO_ROOT / "config" / "models.yaml").read_bytes()).hexdigest()
    assert models == "dc7464c58c196698b62a9d05d5ed4511e406b79a54ec755120d0305eeb651dc9"
