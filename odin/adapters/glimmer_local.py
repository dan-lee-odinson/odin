"""glimmer_local adapter (CONTRACT §11.1). Onboard test is M5.

No built-in settings, like the other adapters: reasoning level, output
cap and timeout must come from configuration; given none, it raises.
"""
from .openai_compat import require_settings


class GlimmerLocalAdapter:
    name = "glimmer_local"
    model_id = "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf"

    def __init__(self, *, reasoning_effort, max_output_tokens, timeout_s):
        require_settings(reasoning_effort, max_output_tokens, timeout_s)
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.timeout_s = timeout_s

    def complete(self, *, prompt: bytes, bundle: dict, call_index: int = 1, **kwargs) -> dict:
        raise RuntimeError("glimmer_local runs at M5 with the Director present")
