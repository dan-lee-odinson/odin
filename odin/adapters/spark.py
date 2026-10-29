"""spark adapter (CONTRACT §11.1): Meta Model API, structured output.

No built-in settings: reasoning level, output cap and timeout come from
configuration (M3: odin/devtools/m3_settings.yaml); given none, it raises.
Read-only tools (docs lookup, history) may be used via `tool_handler`;
no tool sends a command.
"""
import json

from odin.loop.validate import resolved_schema
from .openai_compat import ChatAdapter, READONLY_TOOLS


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
        else:
            schema_file = "answer.schema.json" if bundle.get("turn_kind") != "REPORT" else "report_body.schema.json"
            # M10: Meta cannot follow cross-file $refs, so send the same
            # schema with every $ref resolved inline, derived at call time.
            response_format = {"type": "json_schema", "json_schema": {
                "name": "odin_answer", "schema": resolved_schema(schema_file)}}
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
