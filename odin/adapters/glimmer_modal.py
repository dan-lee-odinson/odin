"""glimmer_modal adapter (CONTRACT section 11.1; M5 prep, M16).

Muse Glimmer 30B on Modal, the onboard seat's fallback: the same
weights as glimmer_local, served by llama.cpp behind Modal's proxy
auth. OpenAI-compatible: POST <endpoint>/v1/chat/completions. The
endpoint comes from glimmer_modal's model block in configuration
(config/models.yaml, as approved for after M16; tests use a test
configuration), never from the old endpoint file of M5's prep.

On an ACT turn it answers in format G, Glimmer's own (M16), with a
response_format of type json_schema, and the loop judges it through
the same put-backs and validator as spark and logs CANDIDATE exactly.

Every request carries the Modal-Key and Modal-Secret headers, whose
values are read from the ODIN_MODAL_PROXY_KEY and
ODIN_MODAL_PROXY_SECRET environment variables at call time; they are
never logged, printed or written anywhere, and a missing variable is
refused naming the variable, never its value. The /slots probe of a
timed-out call (see glimmer_common) goes to the same server with the
same headers, and only its processing flag is kept.

Charging is per GPU-second of each call's wall time, at the
per_gpu_second price in config/prices.yaml, against the Modal stop:
the reservation is the call's timeout in GPU-seconds (the worst
case), and the settled charge is the measured wall time in
GPU-seconds.

Server lifecycle is Claude Code's side of the build: this adapter only
ever sends the requests above. It imports no Modal library.

No built-in settings: reasoning level, output cap and timeout come
from configuration, as for every model; given none, it raises.
"""
import os
from pathlib import Path

import yaml

from .glimmer_common import GlimmerAdapter
from .openai_compat import require_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS = REPO_ROOT / "config" / "models.yaml"
PROXY_KEY_VAR = "ODIN_MODAL_PROXY_KEY"
PROXY_SECRET_VAR = "ODIN_MODAL_PROXY_SECRET"


def load_glimmer_endpoint(settings_path=None) -> str:
    """The endpoint in glimmer_modal's model block in a settings file
    (config/models.yaml by default), or a refusal naming what is
    missing. The old M5-prep endpoint file is never read."""
    path = Path(settings_path) if settings_path else DEFAULT_SETTINGS
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise RuntimeError(f"model settings file missing: {path}") from exc
    entry = doc.get("glimmer_modal")
    endpoint = entry.get("endpoint") if isinstance(entry, dict) else None
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise RuntimeError(
            "glimmer_modal endpoint must come from configuration: "
            f"no endpoint in the glimmer_modal model block in {path}")
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


class GlimmerModalAdapter(GlimmerAdapter):
    name = "glimmer_modal"
    provider = "Modal (llama.cpp), proxy auth"
    model_id = "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf"
    env_var = None

    def __init__(self, *, reasoning_effort, max_output_tokens, timeout_s,
                 endpoint=None, model_id=None,
                 http_post=None, http_get=None, monotonic=None):
        require_settings(reasoning_effort, max_output_tokens, timeout_s)
        if not endpoint:
            raise RuntimeError(
                "glimmer_modal endpoint must come from configuration: "
                "no endpoint in its model block")
        resolved = endpoint.rstrip("/")
        super().__init__(reasoning_effort=reasoning_effort,
                         max_output_tokens=max_output_tokens,
                         timeout_s=timeout_s, base_url=resolved,
                         http_post=http_post, http_get=http_get,
                         monotonic=monotonic)
        self.endpoint = resolved
        if model_id:
            self.model_id = model_id

    def _headers(self):
        return proxy_headers()

    def _worst_case_usd(self, meter):
        return meter.gpu_cost(self.name, self.timeout_s)

    def _settle(self, reservation, meter, latency):
        if reservation is None:
            return None
        return reservation.settle(actual_usd=meter.gpu_cost(self.name, latency))
