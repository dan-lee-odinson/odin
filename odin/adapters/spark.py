"""spark adapter stub for M1 (CONTRACT §11.1). Live calls need META_API_KEY
and the Director present (M3); M1 builds/tests against stand_in only."""
import os


class SparkAdapter:
    name = "spark"
    provider = "Meta Model API, Standard mode"
    model_id = "muse-spark-1.3"
    endpoint = "https://api.meta.ai/v1"

    def __init__(self, reasoning_effort=None, max_output_tokens=4096, timeout_s=120):
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.timeout_s = timeout_s

    def complete(self, *, prompt: bytes, bundle: dict, call_index: int = 1) -> dict:
        if not os.environ.get("META_API_KEY"):
            raise RuntimeError("META_API_KEY not set; spark live calls run only at M3 / scored runs")
        raise RuntimeError("spark live call not exercised in M1")
