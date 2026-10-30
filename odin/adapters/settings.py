"""Scored-run model settings from config/models.yaml (Director's ruling).

Nothing here hard-codes a level, cap or timeout: every value is read from
the file Claude Code maintains. A missing or incomplete file stops a run
before any call (RuntimeError) instead of falling back to a default.
"""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO_ROOT / "config" / "models.yaml"
REQUIRED_KEYS = ("model", "reasoning_effort", "max_output_tokens", "timeout_s")
CONFIGS = ("spark", "spark_open", "glimmer_local", "glimmer_modal")


def load_model_settings(path=None) -> dict:
    settings_path = Path(path or DEFAULT_PATH)
    if not settings_path.exists():
        raise RuntimeError(f"model settings file missing: {settings_path}")
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    # Every entry the file carries must be complete; a test file holding
    # only glimmer_modal (its frozen block comes after M5) is complete
    # on those terms, and build_adapter refuses a missing entry itself.
    for config in CONFIGS:
        entry = data.get(config)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise RuntimeError(f"model settings incomplete: no {config} entry")
        required = REQUIRED_KEYS if config != "glimmer_modal" else \
            tuple(k for k in REQUIRED_KEYS if k != "model")
        missing = [key for key in required if entry.get(key) is None]
        if missing:
            raise RuntimeError(
                f"model settings incomplete: {config} missing {', '.join(missing)}")
    if not any(config in data for config in CONFIGS):
        raise RuntimeError("model settings incomplete: no known model entry")
    return data


def build_adapter(config, settings_path=None, **kwargs):
    """Construct an adapter entirely from the settings file."""
    from .glimmer_local import GlimmerLocalAdapter
    from .glimmer_modal import GlimmerModalAdapter
    from .spark import SparkAdapter
    from .spark_open import SparkOpenAdapter

    classes = {"spark": SparkAdapter, "spark_open": SparkOpenAdapter,
               "glimmer_local": GlimmerLocalAdapter,
               "glimmer_modal": GlimmerModalAdapter}
    if config not in classes:
        raise ValueError(f"unknown model config {config!r}")
    entry = load_model_settings(settings_path).get(config)
    if not isinstance(entry, dict):
        raise RuntimeError(f"model settings incomplete: no {config} entry")
    required = REQUIRED_KEYS if config != "glimmer_modal" else \
        tuple(k for k in REQUIRED_KEYS if k != "model")
    missing = [key for key in required if entry.get(key) is None]
    if missing:
        raise RuntimeError(
            f"model settings incomplete: {config} missing {', '.join(missing)}")
    if config == "glimmer_modal" and entry.get("model") and "model_id" not in kwargs:
        kwargs["model_id"] = entry["model"]
    return classes[config](
        reasoning_effort=entry["reasoning_effort"],
        max_output_tokens=entry["max_output_tokens"],
        timeout_s=entry["timeout_s"], **kwargs)
