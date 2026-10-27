"""The event log (00_HANDOFF.md §4, S2; CONTRACT.md §8.3, §12): what its writer stamps, accepts and
refuses, its head file, who may write which record, the truth file kept apart, and the example log of
one turn."""

import json
import threading

import pytest

from contract.validate import SCHEMA_DIR
from log.canonical import canonical_json, sha256_tag
from log.chain import LogError, head_file, verify_chain
from log.event_log import ODIN_TYPES, EventLog, TruthLog, check_truth_record, verify_event_log
from tests.repo_checks import REPO_ROOT

EXAMPLE_DIR = REPO_ROOT / "log" / "examples"
EXAMPLE_LOG = EXAMPLE_DIR / "events.jsonl"
EXAMPLE_HEAD = EXAMPLE_DIR / "events.head"
SCHEMA_EXAMPLES = SCHEMA_DIR / "examples"


def example(rel):
    return json.loads((SCHEMA_EXAMPLES / rel).read_text(encoding="utf-8"))


def write_example_log(path):
    """Write log/examples/turn.json's entries through an EventLog at path, each by the route its
    writer uses, and return the log."""
    entries = json.loads((EXAMPLE_DIR / "turn.json").read_text(encoding="utf-8"))["entries"]
    utc = iter(entry["utc"] for entry in entries)
    met = iter(entry["met_s"] for entry in entries)
    log = EventLog.create(path, met_clock=lambda: next(met), utc_clock=lambda: next(utc))
    for entry in entries:
        body = example(entry["body_from"]) if "body_from" in entry else entry["body"]
        if entry["type"] == "REPORT":
            log.submit_report(body)
        elif entry["type"] in ODIN_TYPES:
            log.submit_agent({"type": entry["type"], "body": body})
        else:
            log.append(entry["type"], body)
    return log


class Clock:
    """Fake clocks: simulation time steps one second per record."""

    def __init__(self):
        self.met = 600

    def met_s(self):
        self.met += 1
        return self.met

    @staticmethod
    def utc():
        return "2026-10-28T14:10:00.000Z"


def new_log(tmp_path, name="events.jsonl", kind=EventLog):
    clock = Clock()
    return kind.create(tmp_path / "dev-run-0001" / name, met_clock=clock.met_s, utc_clock=clock.utc)


AOS = {"state": "AOS"}
INPUT = example("agent_input/good-input.json")


# The example log

def test_example_log_verifies():
    assert EXAMPLE_HEAD.exists()
    assert verify_event_log(EXAMPLE_LOG) == []


def test_example_log_is_what_the_writer_writes(tmp_path):
    written = write_example_log(tmp_path / "events.jsonl")
    assert written.path.read_bytes() == EXAMPLE_LOG.read_bytes()
    assert head_file(written.path).read_bytes() == EXAMPLE_HEAD.read_bytes()


def test_example_requests_match_the_bundle_their_turn_served():
    records = [json.loads(line) for line in EXAMPLE_LOG.read_bytes().splitlines()]
    served = {r["body"]["turn_id"]: r["body"]["bundle_sha256"] for r in records if r["type"] == "TRIGGER"}
    requests = [r["body"] for r in records if r["type"] == "REQUEST"]
    assert requests
    for request in requests:
        assert request["agent_input_hash"] == served[request["turn_id"]]


# The writer

def test_the_writer_stamps_id_time_and_link(tmp_path):
    log = new_log(tmp_path)
    first = log.append("CONTACT", AOS)
    second = log.append("CONTACT", {"state": "LOS"})
    assert (first["record_id"], first["met_s"], first["utc"], first["prev_hash"]) == (1, 601, Clock.utc(), None)
    lines = log.path.read_bytes().split(b"\n")
    assert lines[0] == canonical_json(first) and lines[1] == canonical_json(second) and lines[2] == b""
    assert second["record_id"] == 2 and second["prev_hash"] == sha256_tag(lines[0])
    assert log.head == sha256_tag(lines[1])
    assert verify_event_log(log.path) == []


def test_the_head_file_holds_the_last_records_hash_after_every_record(tmp_path):
    log = new_log(tmp_path)
    assert not head_file(log.path).exists()
    for _ in range(3):
        log.append("CONTACT", AOS)
        last = log.path.read_bytes().split(b"\n")[-2]
        assert head_file(log.path).read_bytes() == sha256_tag(last).encode("ascii") + b"\n"
    assert head_file(log.path).name == "events.head"


def test_appending_never_changes_earlier_bytes(tmp_path):
    log = new_log(tmp_path)
    before = b""
    for _ in range(5):
        log.append("CONTACT", AOS)
        now = log.path.read_bytes()
        assert now.startswith(before) and len(now) > len(before)
        before = now


def test_records_from_many_threads_form_one_chain(tmp_path):
    log = new_log(tmp_path)
    workers = [threading.Thread(target=lambda: [log.append("CONTACT", AOS) for _ in range(25)])
               for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert verify_event_log(log.path) == []
    assert log.path.read_bytes().count(b"\n") == 100


def test_resume_carries_on_the_chain(tmp_path):
    log = new_log(tmp_path)
    for _ in range(3):
        log.append("CONTACT", AOS)
    resumed = EventLog.resume(log.path, met_clock=lambda: 700, utc_clock=Clock.utc)
    assert resumed.head == log.head
    assert resumed.append("CONTACT", AOS)["record_id"] == 4
    assert verify_event_log(log.path) == []


def _refused(log, call):
    before = log.path.read_bytes()
    head_before = head_file(log.path).read_bytes() if head_file(log.path).exists() else None
    with pytest.raises(LogError):
        call()
    assert log.path.read_bytes() == before, "a refused record must write nothing"
    assert (head_file(log.path).read_bytes() if head_file(log.path).exists() else None) == head_before


def test_red_a_type_s12_does_not_list_is_refused(tmp_path):
    log = new_log(tmp_path)
    _refused(log, lambda: log.append("FAULT_ONSET", {"fault": "made up"}))


def test_red_a_body_that_does_not_fit_its_type_is_refused(tmp_path):
    log = new_log(tmp_path)
    _refused(log, lambda: log.append("DECISION", AOS))


@pytest.mark.parametrize("type_", ODIN_TYPES)
def test_red_the_harness_and_baldur0_cannot_write_odins_records(tmp_path, type_):
    log = new_log(tmp_path)
    _refused(log, lambda: log.append(type_, INPUT))


def test_red_a_log_is_never_started_twice(tmp_path):
    log = new_log(tmp_path)
    log.append("CONTACT", AOS)
    with pytest.raises(LogError):
        EventLog.create(log.path, met_clock=lambda: 0)


def test_red_a_log_whose_head_file_is_left_over_is_not_started(tmp_path):
    folder = tmp_path / "dev-run-0001"
    folder.mkdir()
    (folder / "events.head").write_bytes(sha256_tag(b"").encode("ascii") + b"\n")
    with pytest.raises(LogError):
        EventLog.create(folder / "events.jsonl", met_clock=lambda: 0)


def test_red_an_event_log_not_named_events_jsonl_is_refused(tmp_path):
    with pytest.raises(LogError):
        new_log(tmp_path, name="truth.jsonl")


def test_red_resume_refuses_a_broken_chain(tmp_path):
    copy = tmp_path / "events.jsonl"
    data = bytearray(EXAMPLE_LOG.read_bytes())
    data[len(data) // 2] ^= 0x01
    copy.write_bytes(bytes(data))
    with pytest.raises(LogError):
        EventLog.resume(copy, met_clock=lambda: 0)


def test_red_resume_refuses_a_head_one_record_behind(tmp_path):
    log = new_log(tmp_path)
    log.append("CONTACT", AOS)
    behind = head_file(log.path).read_bytes()
    log.append("CONTACT", AOS)
    head_file(log.path).write_bytes(behind)
    with pytest.raises(LogError):
        EventLog.resume(log.path, met_clock=lambda: 0)


def test_red_resume_refuses_a_log_without_its_head(tmp_path):
    log = new_log(tmp_path)
    log.append("CONTACT", AOS)
    head_file(log.path).unlink()
    with pytest.raises(LogError):
        EventLog.resume(log.path, met_clock=lambda: 0)


def test_red_a_writer_refuses_a_file_another_writer_changed(tmp_path):
    first = new_log(tmp_path)
    first.append("CONTACT", AOS)
    second = EventLog.resume(first.path, met_clock=lambda: 700, utc_clock=Clock.utc)
    second.append("CONTACT", AOS)
    _refused(first, lambda: first.append("CONTACT", AOS))


# ODIN's submissions (§8.3; the Director's ruling on U21: seven types through POST /log/agent)

SUBMISSIONS = {
    "AGENT_INPUT": "agent_input/good-input.json",
    "MODEL_CALL": "model_call/good-spark.json",
    "CANDIDATE": "candidate/good-content.json",
    "ANSWER": "answer_record/good-command.json",
    "MALFORMED": "malformed/good-not-json.json",
    "SPEND": "spend/good-after-call.json",
    "SPEND_STOP": "spend_stop/good-baseten.json",
}


def test_odin_submits_its_seven_records(tmp_path):
    log = new_log(tmp_path)
    for type_, rel in SUBMISSIONS.items():
        record = log.submit_agent({"type": type_, "body": example(rel)})
        assert (record["type"], record["body"]) == (type_, example(rel))
    assert sorted(SUBMISSIONS) == sorted(set(ODIN_TYPES) - {"REPORT"})
    assert verify_event_log(log.path) == []


def test_odin_files_a_report(tmp_path):
    log = new_log(tmp_path)
    assert log.submit_report(example("report/good-check-in.json"))["type"] == "REPORT"


NOT_ODINS = {
    "a decision, which only BALDUR-0 writes": {"type": "DECISION", "body": example("decision_record/good-allow.json")},
    "a trigger, which only the harness writes": {"type": "TRIGGER", "body": example("trigger_record/good-act.json")},
    "a report, which goes to POST /report": {"type": "REPORT", "body": example("report/good-check-in.json")},
    "a body that does not fit its type": {"type": "SPEND", "body": INPUT},
    "its own record_id": {"type": "AGENT_INPUT", "body": INPUT, "record_id": 9},
    "its own prev_hash": {"type": "AGENT_INPUT", "body": INPUT, "prev_hash": None},
}


@pytest.mark.parametrize("label", NOT_ODINS)
def test_red_odin_cannot_submit(tmp_path, label):
    log = new_log(tmp_path)
    _refused(log, lambda: log.submit_agent(NOT_ODINS[label]))


def test_red_a_report_without_its_answer_is_refused(tmp_path):
    log = new_log(tmp_path)
    report = example("report/good-check-in.json")
    del report["answer"]
    _refused(log, lambda: log.submit_report(report))


# Truth kept apart (§12)

def test_truth_goes_to_its_own_file(tmp_path):
    events = new_log(tmp_path)
    truth = new_log(tmp_path, name="truth.jsonl", kind=TruthLog)
    events.append("CONTACT", AOS)
    truth.append("FAULT_ONSET", {"fault": "made up for this test"})
    assert events.path.parent == truth.path.parent and events.path != truth.path
    assert head_file(truth.path).name == "truth.head"
    assert b"FAULT_ONSET" not in events.path.read_bytes()
    assert verify_chain(truth.path, check=check_truth_record) == []


def test_red_truth_cannot_be_written_into_the_event_log(tmp_path):
    log = new_log(tmp_path)
    _refused(log, lambda: log.append("FAULT_ONSET", {"fault": "made up for this test"}))


def test_red_a_truth_file_not_named_truth_jsonl_is_refused(tmp_path):
    with pytest.raises(LogError):
        new_log(tmp_path, name="events.jsonl", kind=TruthLog)
