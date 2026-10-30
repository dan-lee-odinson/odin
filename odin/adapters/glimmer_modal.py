"""glimmer_modal adapter (CONTRACT section 11.1; M5 prep).

Muse Glimmer 30B on Modal, the onboard seat's fallback: the same
weights as glimmer_local, served by llama.cpp behind Modal's proxy
auth. OpenAI-compatible: POST <endpoint>/v1/chat/completions, where
<endpoint> comes from config/glimmer_modal.yaml. Every request carries
the Modal-Key and Modal-Secret headers, whose values are read from the
ODIN_MODAL_PROXY_KEY and ODIN_MODAL_PROXY_SECRET environment variables
at call time; they are never logged, printed or written anywhere, and
a missing variable is refused naming the variable, never its value.

Answers with structured output (a response_format of type json_schema),
as spark does: this adapter is spark's call sequence with Modal's
headers, endpoint and charging. The loop judges the answer through the
same validator and logs CANDIDATE exactly as for spark.

Charging is per GPU-second of each call's wall time, at the
per_gpu_second price in config/prices.yaml, against the Modal stop:
the reservation is the call's timeout in GPU-seconds (the worst case),
and the settled charge is the measured wall time in GPU-seconds.

Server lifecycle is Claude Code's side of the build: this adapter only
ever sends the chat request above. It imports no Modal library.

No built-in settings: reasoning level, output cap and timeout come
from configuration, as for every model; given none, it raises.
"""
import os
import time
from pathlib import Path

import yaml

from odin.spend.meter import SpendStop

from .openai_compat import ProviderError, model_call_body, require_settings
from .spark import SparkAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "glimmer_modal.yaml"
PROXY_KEY_VAR = "ODIN_MODAL_PROXY_KEY"
PROXY_SECRET_VAR = "ODIN_MODAL_PROXY_SECRET"


def load_glimmer_endpoint(config_path=None) -> str:
    """The endpoint in config/glimmer_modal.yaml, or a refusal."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise RuntimeError(f"glimmer_modal config missing: {path}") from exc
    endpoint = doc.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise RuntimeError(f"glimmer_modal config {path} has no endpoint")
    return endpoint.rstrip("/")


def proxy_headers(env=None) -> dict:
    """The two proxy headers, read from the environment at call time.

    A missing variable raises naming the variable only."""
    env = os.environ if env is None else env
    key = env.get(PROXY_KEY_VAR)
    if not key:
        raise RuntimeError(f"{PROXY_KEY_VAR} not set")
    secret = env.get(PROXY_SECRET_VAR)
    if not secret:
        raise RuntimeError(f"{PROXY_SECRET_VAR} not set")
    return {"Modal-Key": key, "Modal-Secret": secret}


class GlimmerModalAdapter(SparkAdapter):
    name = "glimmer_modal"
    provider = "Modal (llama.cpp), proxy auth"
    model_id = "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf"
    env_var = None

    def __init__(self, *, reasoning_effort, max_output_tokens, timeout_s,
                 endpoint=None, config_path=None, model_id=None,
                 http_post=None, monotonic=None):
        require_settings(reasoning_effort, max_output_tokens, timeout_s)
        resolved = (endpoint.rstrip("/") if endpoint
                    else load_glimmer_endpoint(config_path))
        super().__init__(reasoning_effort=reasoning_effort,
                         max_output_tokens=max_output_tokens,
                         timeout_s=timeout_s, base_url=resolved,
                         http_post=http_post)
        self.endpoint = resolved
        if model_id:
            self.model_id = model_id
        self._monotonic = monotonic or time.monotonic

    def _url(self) -> str:
        base = self.base_url
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _one_call(self, messages, *, tools, meter, turn_id, call_index, sink,
                  response_format=None):
        body = {
            "model": self.model_id, "messages": messages,
            "max_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
        }
        if tools:
            body["tools"] = tools
        if response_format is not None:
            body["response_format"] = response_format
        headers = proxy_headers()
        reservation = None
        if meter is not None:
            # Worst case: the whole timeout, in GPU-seconds.
            reserved_usd = meter.gpu_cost(self.name, self.timeout_s)
            reservation = meter.reserve(
                config=self.name, input_tokens=0,
                max_output_tokens=self.max_output_tokens,
                turn_id=turn_id, call_index=call_index,
                reserved_usd=reserved_usd)
            if reservation is None:
                if sink is not None:
                    sink.append(model_call_body(
                        config=self.name, provider=self.provider,
                        model_id=self.model_id,
                        reasoning_effort=self.reasoning_effort,
                        max_output_tokens=self.max_output_tokens,
                        turn_id=turn_id, call_index=call_index,
                        status="SPEND_STOP", usage=None,
                        reserved=0.0, actual=None, latency=None))
                raise SpendStop("spend meter refused the call")
        t0 = self._monotonic()
        status, payload = self.http_post(self._url(), headers, body, self.timeout_s)
        latency = self._monotonic() - t0
        if status >= 400:
            message = ""
            if isinstance(payload, dict):
                message = str((payload.get("error") or {}).get("message") or payload)
            if sink is not None:
                sink.append(model_call_body(
                    config=self.name, provider=self.provider,
                    model_id=self.model_id,
                    reasoning_effort=self.reasoning_effort,
                    max_output_tokens=self.max_output_tokens,
                    turn_id=turn_id, call_index=call_index, status="ERROR",
                    usage=None,
                    reserved=reservation.reserved_usd if reservation else 0.0,
                    actual=None, latency=latency))
            raise ProviderError(status, message or f"provider returned {status}")
        usage = payload.get("usage") or {}
        actual = None
        if reservation is not None:
            actual = reservation.settle(
                actual_usd=meter.gpu_cost(self.name, latency))
        if sink is not None:
            sink.append(model_call_body(
                config=self.name, provider=self.provider,
                model_id=self.model_id,
                reasoning_effort=self.reasoning_effort,
                max_output_tokens=self.max_output_tokens,
                turn_id=turn_id, call_index=call_index, status="OK",
                usage=usage,
                reserved=reservation.reserved_usd if reservation else 0.0,
                actual=actual, latency=latency))
        return payload, usage, latency
