"""Scripted stand-in adapter (§11.4). Never calls a network."""
import json


class StandInAdapter:
    name = "stand_in"

    def __init__(self, script):
        """script: callable(turn_id, bundle) -> raw answer text, or a list of raw texts."""
        self._script = script

    def complete(self, *, prompt: bytes, bundle: dict, call_index: int = 1) -> dict:
        if callable(self._script):
            raw = self._script(bundle["turn_id"], bundle)
        else:
            raw = self._script[bundle["turn_id"] - 1]
        if not isinstance(raw, str):
            raw = json.dumps(raw)
        return {
            "raw": raw,
            "channel": "CONTENT",
            "status": "OK",
            "input_tokens": max(1, len(prompt) // 4),
            "cached_input_tokens": 0,
            "output_tokens": max(1, len(raw) // 4),
            "reasoning_tokens": None,
            "latency_s": 0.0,
            "provider_usage": None,
            "provider": None,
            "model_id": None,
            "reasoning_effort": None,
            "max_output_tokens": None,
        }
