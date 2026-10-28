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
CONFIGS = ("spark", "spark_open", "glimmer_local")


def load_model_settings(path=None) -> dict:
    settings_path = Path(path or DEFAULT_PATH)
    if not settings_path.exists():
        raise RuntimeError(f"model settings file missing: {settings_path}")
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    for config in ("spark", "spark_open"):
        entry = data.get(config)
        if not isinstance(entry, dict):
            raise RuntimeError(f"model settings incomplete: no {config} entry")
        missing = [key for key in REQUIRED_KEYS if entry.get(key) is None]
        if missing:
            raise RuntimeError(
                f"model settings incomplete: {config} missing {', '.join(missing)}")
    return data


def build_adapter(config, settings_path=None, **kwargs):
    """Construct an adapter entirely from the settings file."""
    from .glimmer_local import GlimmerLocalAdapter
    from .spark import SparkAdapter
    from .spark_open import SparkOpenAdapter

    classes = {"spark": SparkAdapter, "spark_open": SparkOpenAdapter,
               "glimmer_local": GlimmerLocalAdapter}
    if config not in classes:
        raise ValueError(f"unknown model config {config!r}")
    entry = load_model_settings(settings_path).get(config)
    if not isinstance(entry, dict):
        raise RuntimeError(f"model settings incomplete: no {config} entry")
    missing = [key for key in REQUIRED_KEYS if entry.get(key) is None]
    if missing:
        raise RuntimeError(
            f"model settings incomplete: {config} missing {', '.join(missing)}")
    return classes[config](
        reasoning_effort=entry["reasoning_effort"],
        max_output_tokens=entry["max_output_tokens"],
        timeout_s=entry["timeout_s"], **kwargs)
