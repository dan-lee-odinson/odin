"""spark adapter (CONTRACT §11.1): Meta Model API, structured output.

No built-in settings: reasoning level, output cap and timeout come from
configuration (M3: odin/devtools/m3_settings.yaml); given none, it raises.
Read-only tools (docs lookup, history) may be used via `tool_handler`;
no tool sends a command.
"""
import copy
import json

from odin.loop.validate import dictionary_for_plan, resolved_schema
from .openai_compat import ChatAdapter, READONLY_TOOLS

_FORMS = {
    "command": {"kind", "command", "parameters", "rationale"},
    "escalation": {"kind", "escalation_kind", "refs", "proposed", "urgency", "rationale"},
    "none": {"kind", "rationale"},
}
_FIELDS = ["kind", "command", "parameters", "escalation_kind", "refs", "proposed", "urgency", "rationale"]


def _arg_schema(arg):
    kind = arg.get("type")
    if kind == "enum":
        return {"type": "string", "enum": list(arg.get("enum_values") or [])}
    schema = {"type": "integer" if str(kind).startswith(("uint", "int")) else "number"}
    if "min" in arg:
        schema["minimum"] = arg["min"]
    if "max" in arg:
        schema["maximum"] = arg["max"]
    return schema


def _nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def _command_call_schema(commands):
    branches = []
    for name, cmd in (commands or {}).items():
        args = list(cmd.get("args") or [])
        branches.append({
            "type": "object", "additionalProperties": False,
            "required": ["command", "parameters"],
            "properties": {
                "command": {"type": "string", "enum": [name]},
                "parameters": {"type": "object", "additionalProperties": False,
                               "required": [a["name"] for a in args],
                               "properties": {a["name"]: _arg_schema(a) for a in args}},
            },
        })
    return {"anyOf": [{"anyOf": branches}, {"type": "null"}]}


def act_format(commands):
    """Format B (M14), derived at call time from the dictionary in force.

    One plain object; no oneOf/allOf/if/then/$ref. `command`/`parameters`
    give way to `command_call`: an anyOf with one closed branch per
    command, each holding only that command's own arguments. An
    escalation's `proposed` is the same anyOf. Every other field is as
    in M11's format."""
    command_call = _command_call_schema(commands)
    return {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "command_call", "escalation_kind", "refs",
                     "urgency", "rationale", "proposed"],
        "properties": {
            "kind": {"type": "string", "enum": ["command", "escalation", "none"]},
            "command_call": copy.deepcopy(command_call),
            "escalation_kind": _nullable({"type": "string", "enum": [
                "OFF_COURSE", "MALFUNCTION", "DECISION_NEEDED",
                "LEASE_NEEDED", "AUTHORITY_NEEDED", "CONFLICT"]}),
            "refs": _nullable({"type": "array", "items": {"type": "string"}}),
            "urgency": _nullable({"type": "string", "enum": ["ROUTINE", "URGENT"]}),
            "rationale": _nullable({"type": "string"}),
            "proposed": copy.deepcopy(command_call),
        },
    }


# Back-compatible aliases for callers using the longer names.
build_act_format = act_format
act_response_format = act_format


def _holds_only_nulls(value):
    if value is None:
        return True
    if isinstance(value, dict):
        return all(_holds_only_nulls(v) for v in value.values())
    return False


def drop_nulls(answer):
    """Drop nulls by the Director's M11 rule, in order. Returns a new dict."""
    if not isinstance(answer, dict):
        return answer
    result = dict(answer)
    if isinstance(result.get("parameters"), dict):
        result["parameters"] = {k: v for k, v in result["parameters"].items() if v is not None}
    if isinstance(result.get("proposed"), dict):
        proposed = dict(result["proposed"])
        if isinstance(proposed.get("parameters"), dict):
            proposed["parameters"] = {k: v for k, v in proposed["parameters"].items() if v is not None}
        # M12: a proposed that holds only nulls becomes null, so the
        # frozen schema accepts an escalation that proposes nothing.
        result["proposed"] = None if _holds_only_nulls(proposed) else proposed
    belonging = _FORMS.get(result.get("kind"))
    if belonging is None:
        return result
    for field in list(result):
        if field == "kind" or field not in _FIELDS:
            continue
        value = result[field]
        if field in belonging:
            if field == "rationale" and value is None:
                del result[field]
        elif value is None or _holds_only_nulls(value):
            del result[field]
    return result


normalize_answer = drop_nulls
drop_null_fields = drop_nulls


class SparkAdapter(ChatAdapter):
    name = "spark"
    provider = "Meta Model API, Standard mode"
    model_id = "muse-spark-1.3"
    endpoint = "https://api.meta.ai/v1"
    env_var = "META_API_KEY"

    def complete(self, *, prompt: bytes, bundle: dict, call_index: int = 1,
                 meter=None, turn_id=None, model_call_sink=None, tool_handler=None,
                 plain_text: bool = False) -> dict:
        turn_id = turn_id if turn_id is not None else bundle.get("turn_id", 1)
        if plain_text:
            # Study call (M4 fix 1): plain text — no answer schema, no tools.
            response_format = None
            tools = None
        elif bundle.get("turn_kind") == "REPORT":
            # Report turns are unchanged (M11): the M10 $ref-free schema.
            response_format = {"type": "json_schema", "json_schema": {
                "name": "odin_answer", "schema": resolved_schema("report_body.schema.json")}}
            tools = READONLY_TOOLS if tool_handler else None
        else:
            # M11 ACT turns: one plain object derived at call time from
            # the dictionary in force, read through the registry exactly
            # as the checker reads it. No strict flag.
            _entry, commands = dictionary_for_plan(bundle.get("plan") or {})
            response_format = {"type": "json_schema", "json_schema": {
                "name": "odin_answer", "schema": act_format(commands)}}
            tools = READONLY_TOOLS if tool_handler else None
        messages = [{"role": "user", "content": prompt.decode("utf-8")}]
        sink = model_call_sink if model_call_sink is not None else []
        index, total_latency, last_usage, cut_off = call_index, 0.0, {}, False
        while True:
            payload, usage, latency = self._one_call(
                messages, tools=tools, meter=meter, turn_id=turn_id,
                call_index=index, sink=sink, response_format=response_format)
            index += 1
            total_latency += latency
            last_usage = usage
            choice = (payload.get("choices") or [{}])[0]
            cut_off = choice.get("finish_reason") == "length"
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            readonly = [c for c in tool_calls
                        if (c.get("function") or {}).get("name") in ("docs_lookup", "history")]
            if readonly and tool_handler:
                messages.append({"role": "assistant", "content": message.get("content"),
                                 "tool_calls": tool_calls})
                for call in readonly:
                    fn = call["function"]
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except Exception:
                        args = {}
                    result = tool_handler(fn["name"], args)
                    messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                     "content": str(result)})
                continue
            # M14 (§16.5): hand the loop the model's text exactly as
            # returned, never re-serialized. Put-back and the null drop
            # happen in the loop's parse.
            raw = message.get("content") or ""
            return {
                "raw": raw, "channel": "CONTENT", "status": "OK",
                "input_tokens": last_usage.get("prompt_tokens"),
                "cached_input_tokens": (last_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
                "output_tokens": last_usage.get("completion_tokens"),
                "reasoning_tokens": (last_usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "latency_s": total_latency, "provider_usage": last_usage,
                "provider": self.provider, "model_id": self.model_id,
                "reasoning_effort": self.reasoning_effort,
                "max_output_tokens": self.max_output_tokens,
                "cut_off": cut_off, "finish_reason": choice.get("finish_reason"),
                "model_calls": sink,
            }
