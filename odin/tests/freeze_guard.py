"""Freeze guard for model settings (M17): every model's block in
config/models.yaml, as canonical JSON (contract section 4, dates as
their ISO 8601 text), must hash to that model's entry in
config/frozen.json -- the way the harness's freeze check does it.
A model with no frozen entry, a changed block, or a changed entry
are all mismatches. The six schemas are checked separately, as
whole files, in the tests that use this guard.
"""
import datetime
import hashlib
import json
from pathlib import Path

import yaml

from odin.loop.canonical import canonical_json


def _as_json(value):
    if isinstance(value, dict):
        return {k: _as_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_as_json(v) for v in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def model_block_sha256(block) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(_as_json(block))).hexdigest()


def model_block_errors(models_path, frozen_path) -> list:
    """One error string per model whose block and frozen entry differ."""
    models = yaml.safe_load(Path(models_path).read_text(encoding="utf-8")) or {}
    frozen = json.loads(Path(frozen_path).read_text(encoding="utf-8"))
    entries = frozen.get("models") or {}
    errors = []
    for name in sorted(set(models) | set(entries)):
        if name not in entries:
            errors.append(f"model {name!r} has no entry in frozen.json")
        elif name not in models:
            errors.append(f"frozen.json names model {name!r} with no block in models.yaml")
        elif model_block_sha256(models[name]) != entries[name]:
            errors.append(f"model {name!r} block does not match its frozen.json entry")
    return errors


def assert_model_blocks_match_frozen(models_path, frozen_path) -> None:
    errors = model_block_errors(models_path, frozen_path)
    assert not errors, "; ".join(errors)
