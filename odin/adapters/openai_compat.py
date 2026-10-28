"""Shared OpenAI-compatible chat plumbing for spark / spark_open (§11.1).

No built-in model settings live here or in the adapters: reasoning level,
output cap and timeout always come from configuration, and an adapter
given none raises instead of choosing. `http_post` is injectable so M3
tests run against a local fake provider; the default is urllib.
Every API call goes through the spend meter when one is supplied.
"""
import json
import time
import urllib.error
import urllib.request

from odin.spend.meter import CONFIG_BUCKET, SpendStop

READONLY_TOOLS = [
    {"type": "function", "function": {"name": "docs_lookup", "parameters": {
        "type": "object", "properties": {"q": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "history", "parameters": {
        "type": "object", "properties": {"points": {"type": "string"},
                                         "window_s": {"type": "integer"}}}}},
]


class ProviderError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def require_settings(reasoning_effort, max_output_tokens, timeout_s):
    missing = [name for name, value in (
        ("reasoning_effort", reasoning_effort),
        ("max_output_tokens", max_output_tokens),
        ("timeout_s", timeout_s),
    ) if value is None]
    if missing:
        raise ValueError(
            "model settings must come from configuration; missing: " + ", ".join(missing))


def estimate_tokens(data) -> int:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return max(1, (len(data) + 3) // 4)


def http_post_json(url, headers, body, timeout):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:
            return exc.code, {}


def model_call_body(*, config, provider, model_id, reasoning_effort, max_output_tokens,
                    turn_id, call_index, status, usage, reserved, actual, latency):
    usage = usage or {}
    return {
        "run_id": None,  # filled by the caller, which owns run/turn context
        "turn_id": turn_id, "call_index": call_index, "config": config,
        "provider": provider, "model_id": model_id,
        "reasoning_effort": reasoning_effort, "max_output_tokens": max_output_tokens,
        "status": status,
        "input_tokens": usage.get("prompt_tokens"),
        "cached_input_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        if usage else None,
        "output_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if usage else None,
        "reserved_cost_usd": reserved, "actual_cost_usd": actual,
        "pays_from": CONFIG_BUCKET.get(config), "latency_s": latency,
        "provider_usage": usage or None,
    }


class ChatAdapter:
    """One metered OpenAI-compatible call sequence ending in a final message."""

    env_var = None

    def __init__(self, *, reasoning_effort, max_output_tokens, timeout_s,
                 base_url=None, api_key=None, http_post=None):
        require_settings(reasoning_effort, max_output_tokens, timeout_s)
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.timeout_s = timeout_s
        self.base_url = (base_url or self.endpoint).rstrip("/")
        self._api_key = api_key
        self.http_post = http_post or http_post_json

    def _key(self):
        import os

        key = self._api_key or os.environ.get(self.env_var or "")
        if not key:
            raise RuntimeError(f"{self.env_var} not set")
        return key

    def _one_call(self, messages, *, tools, meter, turn_id, call_index, sink,
                  response_format=None):
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model_id, "messages": messages,
            "max_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
        }
        if tools:
            body["tools"] = tools
        if response_format is not None:
            body["response_format"] = response_format
        reservation = None
        if meter is not None:
            reservation = meter.reserve(
                config=self.name,
                input_tokens=sum(estimate_tokens(m.get("content") or "") for m in messages),
                max_output_tokens=self.max_output_tokens,
                turn_id=turn_id, call_index=call_index)
            if reservation is None:
                if sink is not None:
                    sink.append(model_call_body(
                        config=self.name, provider=self.provider, model_id=self.model_id,
                        reasoning_effort=self.reasoning_effort,
                        max_output_tokens=self.max_output_tokens, turn_id=turn_id,
                        call_index=call_index, status="SPEND_STOP", usage=None,
                        reserved=0.0, actual=None, latency=None))
                raise SpendStop("spend meter refused the call")
        started = time.monotonic()
        status, payload = self.http_post(
            url, {"Authorization": f"Bearer {self._key()}"}, body, self.timeout_s)
        latency = time.monotonic() - started
        if status >= 400:
            message = ""
            if isinstance(payload, dict):
                message = str((payload.get("error") or {}).get("message") or payload)
            if sink is not None:
                sink.append(model_call_body(
                    config=self.name, provider=self.provider, model_id=self.model_id,
                    reasoning_effort=self.reasoning_effort,
                    max_output_tokens=self.max_output_tokens, turn_id=turn_id,
                    call_index=call_index, status="ERROR", usage=None,
                    reserved=reservation.reserved_usd if reservation else 0.0,
                    actual=None, latency=latency))
            raise ProviderError(status, message or f"provider returned {status}")
        usage = payload.get("usage") or {}
        actual = None
        if reservation is not None:
            actual = reservation.settle(
                input_tokens=usage.get("prompt_tokens") or 0,
                cached_input_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
                output_tokens=usage.get("completion_tokens") or 0)
        if sink is not None:
            sink.append(model_call_body(
                config=self.name, provider=self.provider, model_id=self.model_id,
                reasoning_effort=self.reasoning_effort,
                max_output_tokens=self.max_output_tokens, turn_id=turn_id,
                call_index=call_index, status="OK", usage=usage,
                reserved=reservation.reserved_usd if reservation else 0.0,
                actual=actual, latency=latency))
        return payload, usage, latency
