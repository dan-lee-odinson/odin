"""ODIN's frozen instructions in RUN_START (the Director's ruling on U54, 28 October 2026): instructions_sha256,
contract §10.2's prompt hash, and prompt_template_sha256, both read from Muse Code's frozen record and null for
the stand-in; a run whose instructions or prompt template on disk differ from the record refuses to start."""

import json
import shutil

import pytest

from harness import instructions
from harness.instructions import NotFrozen, frozen
from tests.harness_world import HarnessWorld

# The hashes the Director checked on disk in Muse Code's workspace and accepted as frozen (MC-M7-01).
INSTRUCTIONS = "sha256:3a91b23fd4a533c04a8821fa01743c7d6e0062b6956a02eae703864220cf9f8c"
PROMPT_TEMPLATE = "sha256:63286e9bfd310af6ee5b7e34df867f78a3d483e7e4c192d375bf5c552fd5a282"


def test_the_files_on_disk_are_the_frozen_ones_the_director_accepted():
    assert frozen("spark") == {"instructions_sha256": INSTRUCTIONS, "prompt_template_sha256": PROMPT_TEMPLATE}
    assert frozen("spark_open") == frozen("spark")


def test_the_stand_in_carries_null_for_both():
    assert frozen("stand_in") == {"instructions_sha256": None, "prompt_template_sha256": None}


@pytest.fixture
def copies(tmp_path, monkeypatch):
    """The record and both files copied to a scratch folder, which frozen() then reads."""
    for name in ("RECORD", "INSTRUCTIONS", "PROMPT_TEMPLATE"):
        copy = tmp_path / getattr(instructions, name).name
        shutil.copyfile(getattr(instructions, name), copy)
        monkeypatch.setattr(instructions, name, copy)
    monkeypatch.setattr(instructions, "ROOT", tmp_path)
    return tmp_path


@pytest.mark.parametrize("name", ["system_prompt.md", "prompt.py"])
def test_red_one_changed_byte_in_either_file_refuses_every_run(copies, name):
    data = bytearray((copies / name).read_bytes())
    data[0] ^= 0x01
    (copies / name).write_bytes(bytes(data))
    for model_config in ("spark", "stand_in"):
        with pytest.raises(NotFrozen, match=name):
            frozen(model_config)


def test_red_a_record_that_does_not_say_frozen_is_refused(copies):
    record = json.loads((copies / "system_prompt.sha256.json").read_bytes())
    (copies / "system_prompt.sha256.json").write_text(json.dumps(dict(record, frozen=False)), encoding="utf-8")
    with pytest.raises(NotFrozen):
        frozen("spark")


def test_a_run_records_both_in_run_start(tmp_path):
    harness = HarnessWorld(tmp_path)
    run = harness.run()
    assert run.start()
    run.stop()
    [start] = [json.loads(line) for line in run.final.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines()
               if json.loads(line)["type"] == "RUN_START"]
    assert (start["body"]["instructions_sha256"], start["body"]["prompt_template_sha256"]) == (None, None)


def test_red_a_run_whose_instructions_changed_refuses_to_start_and_writes_nothing(tmp_path, copies):
    (copies / "system_prompt.md").write_bytes((copies / "system_prompt.md").read_bytes() + b" ")
    (tmp_path / "world").mkdir()
    harness = HarnessWorld(tmp_path / "world")
    run = harness.run()
    with pytest.raises(NotFrozen, match="system_prompt.md"):
        run.start()
    assert not run.folder.exists() and not run.final.exists()
