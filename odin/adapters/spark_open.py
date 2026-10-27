"""spark_open adapter (CONTRACT §11.1): Baseten, answers by tool calling.

One answer tool per §7.1 form plus the §7.5 report. Conversion of recorded
tool calls is pure (no network) so M1 tests it offline. `reasoning_content`
is never the answer. The live `complete` path needs BASETEN_API_KEY and is
not exercised in M1.
"""
import json
import os

from odin.loop.validate import validate_against_schema, validate_act_text, validate_report_text

ANSWER_TOOL_NAMES = {"answer_command", "answer_escalation", "answer_none", "answer_report"}
READONLY_TOOL_NAMES = {"docs_lookup", "history"}

# Tool parameter shapes mirror the model-written fields of each answer form.
ANSWER_TOOLS = [
    {"type": "function", "function": {"name": "answer_command", "parameters": {
        "type": "object", "required": ["command", "parameters"], "additionalProperties": False,
        "properties": {"command": {"type": "string"}, "parameters": {"type": "object"},
                       "rationale": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "answer_escalation", "parameters": {
        "type": "object", "required": ["escalation_kind", "refs", "proposed", "urgency"],
        "additionalProperties": False,
        "properties": {"escalation_kind": {"type": "string"}, "refs": {"type": "array"},
                       "proposed": {}, "urgency": {"type": "string"}, "rationale": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "answer_none", "parameters": {
        "type": "object", "additionalProperties": False,
        "properties": {"rationale": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "answer_report", "parameters": {
        "type": "object", "required": ["timeline", "actions", "condition", "deferred", "open_issues"],
        "additionalProperties": False,
        "properties": {"timeline": {"type": "array"}, "actions": {"type": "array"},
                       "condition": {"type": "object"}, "deferred": {"type": "array"},
                       "open_issues": {"type": "array"}, "answer": {"type": "string"}}}}},
]

ENDPOINT = "https://inference.baseten.co/v1"
MODEL_ID = "meta-models/muse-spark-open-1026"


def _parse_args(call) -> dict:
    fn = call.get("function", {}) if isinstance(call, dict) else {}
    args = fn.get("arguments", {})
    if isinstance(args, str):
        return json.loads(args)
    return dict(args)


def convert_tool_calls(tool_calls, turn_kind="ACT", report_kind=None, reasoning_content=None):
    """(ok, obj, reason, detail). Exactly one answer-tool call required.

    reasoning_content is accepted only to prove it is ignored.
    """
    del reasoning_content  # never the answer (§11.1)
    calls = list(tool_calls or [])
    answers = []
    for call in calls:
        name = (call.get("function", {}) or {}).get("name") if isinstance(call, dict) else None
        if name in ANSWER_TOOL_NAMES:
            answers.append(call)
        elif name in READONLY_TOOL_NAMES:
            continue
        else:
            return False, None, "SCHEMA_VIOLATION", f"unknown tool call {name!r}"
    if len(answers) != 1:
        return False, None, "ANSWER_TOOL_CALL_COUNT", f"expected 1 answer-tool call, got {len(answers)}"
    call = answers[0]
    name = call["function"]["name"]
    try:
        args = _parse_args(call)
    except Exception as exc:
        return False, None, "SCHEMA_VIOLATION", f"bad tool arguments: {exc}"
    if turn_kind == "REPORT":
        if name != "answer_report":
            return False, None, "WRONG_FORM_FOR_TURN", "ACT answer tool on a REPORT turn"
        raw = json.dumps(args)
        ok, obj, reason, detail = validate_report_text(raw, report_kind or "PASS_START")
        return ok, obj, reason, detail
    if name == "answer_report":
        return False, None, "WRONG_FORM_FOR_TURN", "report answer tool on an ACT turn"
    if name == "answer_command":
        obj = {"kind": "command", **args}
    elif name == "answer_escalation":
        obj = {"kind": "escalation", **args}
    else:
        obj = {"kind": "none", **args}
    # Same validator as spark (§11.1): schema + dictionary.
    errors = validate_against_schema("answer.schema.json", obj)
    if errors:
        return False, None, "SCHEMA_VIOLATION", "; ".join(errors[:5])
    ok, validated, reason, detail = validate_act_text(json.dumps(obj))
    return ok, validated, reason, detail


class SparkOpenAdapter:
    name = "spark_open"
    provider = "Baseten Model API"
    model_id = MODEL_ID
    endpoint = ENDPOINT

    def __init__(self, reasoning_effort="medium", max_output_tokens=4096, timeout_s=120):
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.timeout_s = timeout_s

    def complete(self, *, prompt: bytes, bundle: dict, call_index: int = 1) -> dict:
        if not os.environ.get("BASETEN_API_KEY"):
            raise RuntimeError("BASETEN_API_KEY not set; spark_open live calls are out of scope for M1")
        raise RuntimeError("spark_open live call not exercised in M1; conversion tested on recorded responses")
