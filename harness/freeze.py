"""The freeze record of the contract schemas ODIN's instructions are rendered from and of the model settings
for scored runs (CONTRACT.md §10.4; the Director's ruling on U55, 28 October 2026), so that phases 1, 2 and 3
fly the same settings.

config/frozen.json holds the SHA-256 of each of the six schemas, as a whole file, and each model's settings
as its own entry: the SHA-256 of the canonical JSON (§4) of the model's block in config/models.yaml. A model
added later then gets an entry of its own and leaves the others untouched. Before anything of a run is
written, the six schemas and the run's model's block are checked against the record, and a run whose schemas
or settings differ refuses to start. The stand-in has no settings, so only its schemas are checked. ODIN's
instructions and prompt template have their own record, Muse Code's (harness/instructions.py, U54).
"""

import datetime
import json
from pathlib import Path

from gateway.signed import load_yaml
from harness.instructions import NotFrozen
from log.canonical import canonical_json, sha256_tag

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "config" / "frozen.json"
MODELS = ROOT / "config" / "models.yaml"
SCHEMAS = tuple(f"contract/schemas/{name}.schema.json"
                for name in ("answer", "report_body", "report", "turn_bundle", "observation", "common"))


def model_blocks():
    """{model: its block} from config/models.yaml, read by BALDUR-0's loader, which refuses a key written twice."""
    document, problems = load_yaml(MODELS.read_bytes())
    if problems or not isinstance(document, dict):
        raise NotFrozen(f"config/models.yaml cannot be read: {problems}")
    return document


def settings_sha256(block):
    """The SHA-256 of a model block's canonical JSON. JSON has no date, so a date is written as its ISO 8601
    text, as it stands in the file."""
    return sha256_tag(canonical_json({key: value.isoformat() if isinstance(value, datetime.date) else value
                                      for key, value in block.items()}))


def on_disk():
    """What the record would hold for the files on disk now: {schemas: {path: hash}, models: {name: hash}}."""
    return {"schemas": {path: sha256_tag((ROOT / path).read_bytes()) for path in SCHEMAS},
            "models": {name: settings_sha256(block) for name, block in model_blocks().items()}}


def check(model_config):
    """The run's model's frozen block, or None for the stand-in. Raises NotFrozen unless the six schemas, and
    the run's model's settings, are the ones the record froze."""
    record = json.loads(RECORD.read_bytes())
    for path in SCHEMAS:
        found = sha256_tag((ROOT / path).read_bytes())
        if found != record["schemas"].get(path):
            raise NotFrozen(f"{path} is {found}, not the frozen {record['schemas'].get(path)}")
    return frozen_block(model_config)


def frozen_block(model_config):
    """A model's block in config/models.yaml, the settings its loop reads, once its hash is the one the record
    froze; None for the stand-in, which has no settings. Raises NotFrozen for a model with no entry of its own
    in the record, or whose block differs from it. RUN_START's model ID and reasoning level come from this
    block, and S8 checks each MODEL_CALL against it (the Director's ruling on U56, 28 October 2026)."""
    if model_config == "stand_in":
        return None
    record = json.loads(RECORD.read_bytes())
    if model_config not in record["models"]:
        raise NotFrozen(f"{model_config} has no frozen settings in {RECORD.name}")
    block = model_blocks().get(model_config)
    if not isinstance(block, dict):
        raise NotFrozen(f"config/models.yaml holds no settings for {model_config}")
    found = settings_sha256(block)
    if found != record["models"][model_config]:
        raise NotFrozen(f"{model_config}'s settings in config/models.yaml are {found}, "
                        f"not the frozen {record['models'][model_config]}")
    return block
