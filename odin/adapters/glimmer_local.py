"""glimmer_local adapter (CONTRACT section 11.1; M16).

Muse Glimmer 30B on the Director's laptop, served by llama.cpp (or
Ollama): the same weights as glimmer_modal, the same format G on an
ACT turn, the same put-backs and judging in the loop, and the same
/slots flag for a timed-out call. Its endpoint comes from
configuration (its model block, or the constructor in tests); the
local serve address below is only the llama.cpp default a test
configuration may replace.

No built-in model settings, like the other adapters: reasoning level,
output cap and timeout must come from configuration; given none, it
raises. No key is needed for a local server.
"""
from .glimmer_common import GlimmerAdapter
from .openai_compat import require_settings

DEFAULT_ENDPOINT = "http://127.0.0.1:8080"


class GlimmerLocalAdapter(GlimmerAdapter):
    name = "glimmer_local"
    provider = "llama.cpp (local)"
    model_id = "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf"
    env_var = None

    def __init__(self, *, reasoning_effort, max_output_tokens, timeout_s,
                 endpoint=None, base_url=None, model_id=None,
                 http_post=None, http_get=None, monotonic=None):
        require_settings(reasoning_effort, max_output_tokens, timeout_s)
        resolved = (endpoint or base_url or DEFAULT_ENDPOINT).rstrip("/")
        super().__init__(reasoning_effort=reasoning_effort,
                         max_output_tokens=max_output_tokens,
                         timeout_s=timeout_s, base_url=resolved,
                         http_post=http_post, http_get=http_get,
                         monotonic=monotonic)
        self.endpoint = resolved
        if model_id:
            self.model_id = model_id
