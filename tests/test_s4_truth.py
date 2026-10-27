"""The truth file (CONTRACT.md §12; the Director's rulings on U35 and U36): each record checked against
log/truth_record.schema.json, and a scored run's file committed gzip-compressed while a development
run's stays plain."""

import gzip
import json

import pytest

from log.chain import LogError, head_file
from log.event_log import TruthLog, check_truth_record, compress_truth, verify_truth
from tests.huginn_scenarios import FLOWN
from wrapper.huginn import load_scenario
from wrapper.simulator import Simulator


def a_run(folder, ticks=30, name="P4_hk_generation_halt", start_at=1330):
    """A run's truth file with every record type in it: P4 from 1330 is past its onset at 1200 and its
    dropped reset at 1320, so its first tick writes all three types."""
    run = {}
    folder.mkdir(parents=True, exist_ok=True)
    truth = TruthLog.create(folder / "truth.jsonl", met_clock=lambda: run["simulator"].met_s,
                            utc_clock=lambda: "2026-10-27T18:00:00.000Z")
    run["simulator"] = Simulator(load_scenario(name), windows=FLOWN[name], truth=truth, start_at=start_at)
    for _ in range(ticks):
        run["simulator"].step()
    return truth.path


def records(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def test_a_development_runs_truth_file_stays_plain_and_verifies(tmp_path):
    path = a_run(tmp_path)
    assert {r["type"] for r in records(path)} == {"FAULT_ONSET", "SCRIPTED_COMMAND_DROPPED", "TRUE_STATE"}
    assert verify_truth(path) == []


def test_a_scored_runs_truth_file_is_committed_compressed_and_still_verifies(tmp_path):
    path = a_run(tmp_path)
    plain, head = path.read_bytes(), head_file(path).read_bytes()
    packed = compress_truth(path)
    assert packed.name == "truth.jsonl.gz" and not path.exists()
    assert gzip.decompress(packed.read_bytes()) == plain
    assert head_file(path).read_bytes() == head   # truth.head stays beside it, unchanged
    assert verify_truth(packed) == []
    assert len(packed.read_bytes()) < len(plain) / 5


def test_the_same_truth_file_always_compresses_to_the_same_bytes(tmp_path):
    packed = [compress_truth(a_run(tmp_path / run)).read_bytes() for run in ("a", "b")]
    assert packed[0] == packed[1]
    assert packed[0][3] & 0x08 == 0 and packed[0][4:8] == b"\x00\x00\x00\x00"   # no file name, no time


def test_red_a_record_changed_inside_a_compressed_truth_file_is_caught(tmp_path):
    packed = compress_truth(a_run(tmp_path))
    data = bytearray(gzip.decompress(packed.read_bytes()))
    data[data.index(b'"soc_pct":') + 11] ^= 0x01
    packed.write_bytes(gzip.compress(bytes(data)))
    assert verify_truth(packed) != []


def test_red_a_compressed_file_already_there_is_never_overwritten(tmp_path):
    path = a_run(tmp_path)
    (tmp_path / "truth.jsonl.gz").write_bytes(b"kept")
    with pytest.raises(FileExistsError):
        compress_truth(path)
    assert path.exists() and (tmp_path / "truth.jsonl.gz").read_bytes() == b"kept"


def test_red_only_a_truth_file_is_compressed(tmp_path):
    (tmp_path / "events.jsonl").write_bytes(b"")
    with pytest.raises(LogError):
        compress_truth(tmp_path / "events.jsonl")


# -- the schema ------------------------------------------------------------------------------

def written(tmp_path):
    return {r["type"]: r for r in records(a_run(tmp_path, ticks=1))}


def without(record, *keys):
    record = json.loads(json.dumps(record))
    inner = record
    for key in keys[:-1]:
        inner = inner[key]
    del inner[keys[-1]]
    return record


@pytest.mark.parametrize("change", [
    pytest.param(lambda r: without(r["TRUE_STATE"], "body", "eps"), id="a TRUE_STATE with no eps"),
    pytest.param(lambda r: without(r["TRUE_STATE"], "body", "cdh", "hk_halted"), id="a TRUE_STATE with no hk_halted"),
    pytest.param(lambda r: dict(r["TRUE_STATE"], type="NOTE"), id="a type the truth file does not have"),
    pytest.param(lambda r: {**r["FAULT_ONSET"], "body": {**r["FAULT_ONSET"]["body"], "source": "ODIN"}},
                 id="a fault onset not from the scenario"),
    pytest.param(lambda r: without(r["SCRIPTED_COMMAND_DROPPED"], "body", "contact_window"),
                 id="a dropped command with no window"),
    pytest.param(lambda r: {**r["SCRIPTED_COMMAND_DROPPED"], "body": {**r["SCRIPTED_COMMAND_DROPPED"]["body"],
                                                                        "reason": "x"}},
                 id="a dropped command with a field the schema does not list"),
])
def test_red_a_record_the_schema_does_not_describe_is_refused(tmp_path, change):
    good = written(tmp_path)
    assert all(check_truth_record(record) == [] for record in good.values())
    assert check_truth_record(change(good)) != []


def test_red_the_truth_log_refuses_a_body_the_schema_does_not_describe(tmp_path):
    truth = TruthLog.create(tmp_path / "truth.jsonl", met_clock=lambda: 0)
    with pytest.raises(LogError):
        truth.append("FAULT_ONSET", {"fault": "made up for this test"})
    assert (tmp_path / "truth.jsonl").read_bytes() == b""
