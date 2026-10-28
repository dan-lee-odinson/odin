"""Local fake model provider for M3 tests: an OpenAI-compatible endpoint
double. It records every call (URL, body, timeout — never headers, so key
canaries cannot leak through it) and answers deterministically:
spark gets a JSON answer as content; spark_open gets one answer-tool call.
Usage numbers are fixed so cost arithmetic can be checked exactly.
"""
import json

USAGE = {
    "prompt_tokens": 1000,
    "completion_tokens": 100,
    "prompt_tokens_details": {"cached_tokens": 200},
    "completion_tokens_details": {"reasoning_tokens": 40},
    "total_tokens": 1100,
}


class FakeProvider:
    def __init__(self, answer_text='{"kind":"none","rationale":"Fake provider answer."}',
                 cut_off=(), reject_levels=()):
        self.calls = []
        self.answer_text = answer_text
        self.cut_off = set(cut_off)          # {(config, reasoning_effort)}
        self.reject_levels = set(reject_levels)

    def post(self, url, headers, body, timeout):
        model = body.get("model", "")
        config = "spark_open" if "spark-open" in model else "spark"
        level = body.get("reasoning_effort")
        self.calls.append({"url": url, "body": body, "timeout": timeout,
                           "model_kind": config})
        if (config, level) in self.reject_levels:
            return 400, {"error": {"message": f"reasoning_effort {level} not offered"}}
        if (config, level) in self.cut_off:
            message = {"role": "assistant", "content": '{"kind":"comm'}
            return 200, {"choices": [{"message": message, "finish_reason": "length"}],
                         "usage": dict(USAGE)}
        if config == "spark_open":
            message = {"role": "assistant", "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "answer_none",
                             "arguments": json.dumps({"rationale": "Fake provider answer."})},
            }]}
        else:
            message = {"role": "assistant", "content": self.answer_text}
        return 200, {"choices": [{"message": message, "finish_reason": "stop"}],
                     "usage": dict(USAGE)}
