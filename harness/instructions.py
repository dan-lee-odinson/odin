"""ODIN's frozen instructions and prompt template in RUN_START (CONTRACT.md §10.2, §10.4; the Director's ruling
on U54, 28 October 2026).

Muse Code froze ODIN's instructions in MC-M7-01 and recorded the freeze in
odin/instructions/system_prompt.sha256.json: the instructions' hash, and the hash of the prompt template,
odin/loop/prompt.py. RUN_START carries both, read from that record: instructions_sha256 is §10.2's prompt
hash. The stand-in renders no prompt, so both are null for it (U15). Before anything of a run is written,
both files on disk are checked against the record, and a run whose files differ refuses to start.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "odin" / "instructions" / "system_prompt.sha256.json"
INSTRUCTIONS = ROOT / "odin" / "instructions" / "system_prompt.md"
PROMPT_TEMPLATE = ROOT / "odin" / "loop" / "prompt.py"


class NotFrozen(Exception):
    """The instructions or the prompt template on disk are not the ones Muse Code's record froze."""


def _sha256(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen(model_config):
    """{instructions_sha256, prompt_template_sha256} for RUN_START, from Muse Code's frozen record, once both
    files on disk match it; both null for the stand-in. Raises NotFrozen if either file differs."""
    record = json.loads(RECORD.read_bytes())
    if record.get("frozen") is not True:
        raise NotFrozen(f"{RECORD.name} does not record a freeze")
    hashes = {"instructions_sha256": record["sha256"], "prompt_template_sha256": record["prompt_template_sha256"]}
    for name, path in (("instructions_sha256", INSTRUCTIONS), ("prompt_template_sha256", PROMPT_TEMPLATE)):
        on_disk = _sha256(path)
        if on_disk != hashes[name]:
            raise NotFrozen(f"{path.relative_to(ROOT).as_posix()} is {on_disk}, not the frozen {hashes[name]}")
    if model_config == "stand_in":
        return {name: None for name in hashes}
    return hashes
