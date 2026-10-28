"""spark_open adapter (CONTRACT §11.1): Baseten, answers by tool calling.

One answer tool per §7.1 form plus the §7.5 report. Conversion of recorded
tool calls is pure (no network). `reasoning_content` is never the answer.
No built-in settings: reasoning level (set explicitly on every call,
never Baseten's xhigh default unless configured), output cap and timeout
come from configuration; given none, the adapter raises.
"""
import json

from odin.loop.validate import validate_against_schema, validate_act_text, validate_report_text
from .openai_compat import ChatAdapter, READONLY_TOOLS

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


def convert_tool_calls(tool_calls, turn_kind="ACT", report_kind=None, reasoning_content=None,
                       commands=None):
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
    # Same validator as spark (§11.1): dictionary first, then schema (U58).
    ok, validated, reason, detail = validate_act_text(json.dumps(obj), commands=commands)
    if not ok:
        return ok, validated, reason, detail
    errors = validate_against_schema("answer.schema.json", obj)
    if errors:
        return False, None, "SCHEMA_VIOLATION", "; ".join(errors[:5])
    return ok, validated, reason, detail


class SparkOpenAdapter(ChatAdapter):
    name = "spark_open"
    provider = "Baseten Model API"
    model_id = MODEL_ID
    endpoint = ENDPOINT
    env_var = "BASETEN_API_KEY"

    def complete(self, *, prompt: bytes, bundle: dict, call_index: int = 1,
                 meter=None, turn_id=None, model_call_sink=None, tool_handler=None) -> dict:
        turn_id = turn_id if turn_id is not None else bundle.get("turn_id", 1)
        tools = list(ANSWER_TOOLS) + (list(READONLY_TOOLS) if tool_handler else [])
        messages = [{"role": "user", "content": prompt.decode("utf-8")}]
        sink = model_call_sink if model_call_sink is not None else []
        collected, index, total_latency, last_usage, cut_off = [], call_index, 0.0, {}, False
        while True:
            payload, usage, latency = self._one_call(
                messages, tools=tools, meter=meter, turn_id=turn_id,
                call_index=index, sink=sink)
            index += 1
            total_latency += latency
            last_usage = usage
            choice = (payload.get("choices") or [{}])[0]
            cut_off = choice.get("finish_reason") == "length"
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            collected.extend(tool_calls)
            readonly = [c for c in tool_calls
                        if (c.get("function") or {}).get("name") in READONLY_TOOL_NAMES]
            if readonly and tool_handler:
                messages.append({"role": "assistant", "content": message.get("content"),
                                 "tool_calls": tool_calls})
                for call in readonly:
                    fn = call["function"]
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except Exception:
                        args = {}
                    messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                     "content": str(tool_handler(fn["name"], args))})
                continue
            break
        return {
            "raw": json.dumps(collected), "channel": "TOOL_CALLS", "status": "OK",
            "input_tokens": last_usage.get("prompt_tokens"),
            "cached_input_tokens": (last_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            "output_tokens": last_usage.get("completion_tokens"),
            "reasoning_tokens": (last_usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "latency_s": total_latency, "provider_usage": last_usage,
            "provider": self.provider, "model_id": self.model_id,
            "reasoning_effort": self.reasoning_effort,
            "max_output_tokens": self.max_output_tokens,
            "cut_off": cut_off, "model_calls": sink,
        }
