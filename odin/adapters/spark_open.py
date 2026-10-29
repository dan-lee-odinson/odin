"""spark_open adapter (CONTRACT §11.1): Baseten, answers by tool calling.

One answer tool per §7.1 form plus the §7.5 report. Conversion of recorded
tool calls is pure (no network). `reasoning_content` is never the answer.
No built-in settings: reasoning level (set explicitly on every call,
never Baseten's xhigh default unless configured), output cap and timeout
come from configuration; given none, the adapter raises.
"""
import copy
import json

from odin.loop.validate import (resolved_schema, validate_against_schema,
                                validate_act_text, validate_report_text)
from .openai_compat import ChatAdapter, READONLY_TOOLS

ANSWER_TOOL_NAMES = {"answer_command", "answer_escalation", "answer_none", "answer_report"}
READONLY_TOOL_NAMES = {"docs_lookup", "history"}


def _build_answer_tools():
    """Answer tools typed from the frozen forms (M14): the §7.1 answer
    schema's definitions and the §7.5 report body, $refs resolved from
    the frozen files at load. No field list is kept a second time."""
    answer = resolved_schema("answer.schema.json")
    definitions = answer.get("definitions") or {}
    command_enum = (resolved_schema("common.schema.json")
                    .get("definitions", {}).get("command", {}).get("enum"))

    def form_params(form_name, drop=()):
        form = definitions[form_name]
        props = {k: copy.deepcopy(v) for k, v in (form.get("properties") or {}).items()
                 if k != "kind" and k not in drop}
        required = [k for k in (form.get("required") or []) if k != "kind" and k not in drop]
        return {"type": "object", "required": required, "additionalProperties": False,
                "properties": props}

    command_params = form_params("command")
    if command_enum:
        command_params["properties"]["command"] = {"type": "string", "enum": list(command_enum)}
    command_params["properties"]["parameters"] = {"type": "object"}

    escalation_params = form_params("escalation")
    if command_enum:
        proposed = escalation_params["properties"].get("proposed") or {}
        for branch in proposed.get("anyOf", []):
            if isinstance(branch, dict) and branch.get("type") == "object":
                props = branch.setdefault("properties", {})
                props["command"] = {"type": "string", "enum": list(command_enum)}
                props["parameters"] = {"type": "object"}

    none_params = form_params("none")

    report = resolved_schema("report_body.schema.json")
    report_params = {"type": "object", "required": list(report.get("required") or []),
                     "additionalProperties": False,
                     "properties": copy.deepcopy(report.get("properties") or {})}

    def tool(name, params):
        return {"type": "function", "function": {"name": name, "parameters": params}}

    return [tool("answer_command", command_params),
            tool("answer_escalation", escalation_params),
            tool("answer_none", none_params),
            tool("answer_report", report_params)]


ANSWER_TOOLS = _build_answer_tools()

ENDPOINT = "https://inference.baseten.co/v1"
MODEL_ID = "meta-models/muse-spark-open-1026"


def _parse_args(call) -> dict:
    fn = call.get("function", {}) if isinstance(call, dict) else {}
    args = fn.get("arguments", {})
    if isinstance(args, str):
        return json.loads(args)
    return dict(args)


def convert_tool_calls(tool_calls, turn_kind="ACT", report_kind=None, reasoning_content=None,
                       commands=None, content=None):
    """(ok, obj, reason, detail). Exactly one answer-tool call required.

    reasoning_content is accepted only to prove it is ignored. When
    `content` is given, the amended §11.1 rule applies (see
    `convert_message`)."""
    if content is not None:
        return convert_message(content, tool_calls, turn_kind=turn_kind,
                               report_kind=report_kind, reasoning_content=reasoning_content,
                               commands=commands)
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


def convert_message(content, tool_calls, turn_kind="ACT", report_kind=None,
                    reasoning_content=None, commands=None):
    """(ok, obj, reason, detail): §11.1 as amended 29 October 2026.

    Exactly one answer-tool call makes that call the answer. With no
    answer-tool call, `content` trimmed must parse as exactly one JSON
    object, and that object is the answer. Anything else is MALFORMED.
    `reasoning_content` is never the answer."""
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
    if len(answers) > 1:
        return False, None, "ANSWER_TOOL_CALL_COUNT", f"expected 1 answer-tool call, got {len(answers)}"
    if len(answers) == 1:
        return convert_tool_calls(answers, turn_kind=turn_kind, report_kind=report_kind,
                                  commands=commands)
    if not isinstance(content, str) or not content.strip():
        return False, None, "NOT_ONE_JSON_OBJECT", "empty or non-text answer"
    trimmed = content.strip()
    try:
        obj = json.loads(trimmed)
    except Exception as exc:
        return False, None, "NOT_ONE_JSON_OBJECT", f"not exactly one JSON value: {exc}"
    if not isinstance(obj, dict):
        return False, None, "NOT_ONE_JSON_OBJECT", "answer is not a JSON object"
    if turn_kind == "REPORT":
        return validate_report_text(trimmed, report_kind or "PASS_START")
    return validate_act_text(trimmed, commands=commands)


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
        final_message, index, total_latency, last_usage, cut_off = {}, call_index, 0.0, {}, False
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
            final_message = message
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
        # M14 (§16.5): CANDIDATE channel MESSAGE holds the message that
        # ends the turn: its content and tool calls exactly as returned
        # (content null when the message has none). reasoning_content
        # is never part of it.
        raw = json.dumps({"content": final_message.get("content"),
                          "tool_calls": final_message.get("tool_calls") or []})
        return {
            "raw": raw, "channel": "MESSAGE", "status": "OK",
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
