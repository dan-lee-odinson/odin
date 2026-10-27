"""glimmer_local adapter stub for M1 (CONTRACT §11.1). Onboard test is M5."""


class GlimmerLocalAdapter:
    name = "glimmer_local"
    model_id = "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf"

    def __init__(self, reasoning_effort=None, max_output_tokens=4096, timeout_s=300):
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.timeout_s = timeout_s

    def complete(self, *, prompt: bytes, bundle: dict, call_index: int = 1) -> dict:
        raise RuntimeError("glimmer_local runs at M5 with the Director present")
