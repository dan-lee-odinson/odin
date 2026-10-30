"""Red-case runner for M16 (Glimmer's format G).

Plants one fault at a time in the real source, runs the M16 test(s)
that cover it, and counts only tests that ran and failed (a failure
at collection, or an error, does not count). The source file is
restored byte for byte after each plant and its hash checked before
the next one. At the end the whole M16 file is run again, restored.

Run from the workspace root: python odin/devtools/red_cases_m16.py
Exit 0 only if every plant made its test(s) run and fail, no plant
produced an error, and every source was restored.
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_FILE = "odin/tests/test_m16_format_g.py"


def _t(*names):
    return [f"{TEST_FILE}::{n}" for n in names]


CASES = [
    {
        "name": "format R sent to Glimmer instead of G",
        "file": "odin/adapters/spark.py",
        "find": '    return {"anyOf": [\n        branch("command"',
        "replace": '    return act_format(commands) if True else {"anyOf": [\n        branch("command"',
        "tests": _t("test_glimmer_modal_sends_format_g_not_r", "test_format_g_equals_huginn_and_inst_files_as_parsed_json"),
    },
    {
        "name": "spark sent format G instead of R",
        "file": "odin/adapters/spark.py",
        "find": "        return act_format(commands)",
        "replace": "        return act_format_g(commands)",
        "tests": _t("test_spark_still_sends_format_r_not_g"),
    },
    {
        "name": "spark_open sent a json_schema response format",
        "file": "odin/adapters/spark_open.py",
        "find": "                call_index=index, sink=sink)",
        "replace": ('                call_index=index, sink=sink, response_format={"type": "json_schema", '
                    '"json_schema": {"name": "odin_answer", "schema": '
                    '__import__("odin.adapters.spark", fromlist=["act_format_g"]).act_format_g({})}})'),
        "tests": _t("test_spark_open_still_sends_no_format_g"),
    },
    {
        "name": "answers judged otherwise than recorded (escalation put-back dropped)",
        "file": "odin/loop/loop.py",
        "find": "judged = drop_nulls(put_back_command_call(put_back_escalation(obj)))",
        "replace": "judged = drop_nulls(put_back_command_call(obj))",
        "tests": _t("test_answers_g_judged_exactly_as_recorded",
                    "test_escalations_g_judged_and_admitted_exactly_as_recorded",
                    "test_checks_g_judged_and_admitted_exactly_as_recorded"),
    },
    {
        "name": "the endpoint read from the old file",
        "file": "odin/adapters/glimmer_modal.py",
        "find": ('        if not endpoint:\n'
                 '            raise RuntimeError(\n'
                 '                "glimmer_modal endpoint must come from configuration: "\n'
                 '                "no endpoint in its model block")'),
        "replace": ('        if not endpoint:\n'
                    '            endpoint = __import__("yaml").safe_load(\n'
                    '                (REPO_ROOT / "config" / "glimmer_modal.yaml")'
                    '.read_text(encoding="utf-8"))["endpoint"]'),
        "tests": _t("test_endpoint_is_not_read_from_old_file"),
    },
    {
        "name": "a timeout logged as ERROR while the server is processing",
        "file": "odin/adapters/glimmer_common.py",
        "find": 'status = "TIMEOUT" if processing else "ERROR"',
        "replace": 'status = "ERROR" if processing else "TIMEOUT"',
        "tests": _t("test_timeout_while_processing_logs_timeout"),
    },
    {
        "name": "a timeout logged as TIMEOUT when the server is not processing",
        "file": "odin/adapters/glimmer_common.py",
        "find": "        return slots_processing(payload)",
        "replace": "        return True  # planted: always claim processing",
        "tests": _t("test_timeout_when_not_processing_or_refused_logs_error"),
    },
    {
        "name": "/slots asked only after the call is dropped",
        "file": "odin/adapters/glimmer_common.py",
        "find": "            processing = self._probe_slots(headers)",
        "replace": ("            worker.join()  # planted: let the call go first\n"
                    "            processing = self._probe_slots(headers)"),
        "tests": _t("test_timeout_while_processing_logs_timeout"),
    },
    {
        "name": "a timeout logged as TIMEOUT when /slots refuses (refused treated as processing)",
        "file": "odin/adapters/glimmer_common.py",
        "find": ("            status, payload = self.http_get(\n"
                 "                self._slots_url(), headers, SLOTS_PROBE_TIMEOUT_S)\n"
                 "        except Exception:\n"
                 "            return False"),
        "replace": ("            status, payload = self.http_get(\n"
                    "                self._slots_url(), headers, SLOTS_PROBE_TIMEOUT_S)\n"
                    "        except Exception:\n"
                    "            return True  # planted: a refused /slots claims processing"),
        "tests": _t("test_timeout_when_not_processing_or_refused_logs_error"),
    },
    {
        "name": "what /slots returned written into the MODEL_CALL record",
        "file": "odin/adapters/glimmer_common.py",
        "find": ("            self._record(sink, turn_id=turn_id, call_index=call_index,\n"
                 "                         status=status, usage=None, reservation=reservation,"),
        "replace": ("            self._record(sink, turn_id=turn_id, call_index=call_index,\n"
                    "                         status=status, usage={\"slots\": self.http_get(self._slots_url(), headers, 5)[1]}, "
                    "reservation=reservation,"),
        "tests": _t("test_timeout_while_processing_logs_timeout",
                    "test_timeout_through_loop_writes_no_key_or_slots_payload"),
    },
    {
        "name": "a key's value written into a file the run writes (MODEL_CALL usage)",
        "file": "odin/adapters/glimmer_common.py",
        "find": ("            self._record(sink, turn_id=turn_id, call_index=call_index,\n"
                 "                         status=status, usage=None, reservation=reservation,"),
        "replace": ("            self._record(sink, turn_id=turn_id, call_index=call_index,\n"
                    "                         status=status, usage={\"planted_key\": headers[\"Modal-Key\"]}, "
                    "reservation=reservation,"),
        "tests": _t("test_timeout_through_loop_writes_no_key_or_slots_payload"),
    },
]


def _run_pytest(nodes):
    done = subprocess.run(
        [sys.executable, "-m", "pytest", *nodes, "-q"],
        cwd=ROOT, capture_output=True, text=True)
    out = done.stdout + done.stderr
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) errors?", out)) else 0
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    summary = [line for line in out.splitlines() if "passed" in line or "failed" in line]
    return done.returncode, failed, errors, passed, summary[-1] if summary else out[-200:]


def main() -> int:
    ok = True
    for i, case in enumerate(CASES, 1):
        path = ROOT / case["file"]
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        if text.count(case["find"]) != 1:
            print(f"[{i}] {case['name']}: PLANT DID NOT APPLY "
                  f"(find count {text.count(case['find'])}) in {case['file']}")
            ok = False
            continue
        try:
            path.write_bytes(text.replace(case["find"], case["replace"]).encode("utf-8"))
            code, failed, errors, passed, summary = _run_pytest(case["tests"])
        finally:
            path.write_bytes(original)
        restored = hashlib.sha256(path.read_bytes()).hexdigest() == digest
        verdict = "RED OK" if (failed >= 1 and errors == 0 and code != 0 and restored) else "NOT RED"
        if verdict != "RED OK":
            ok = False
        print(f"[{i}] {case['name']}\n"
              f"    plant: {case['file']}\n"
              f"    tests: {', '.join(n.split('::')[-1] for n in case['tests'])}\n"
              f"    ran: {failed} failed, {passed} passed, {errors} errors "
              f"(exit {code}); restored: {restored} -> {verdict}\n"
              f"    pytest: {summary.strip()}")
    code, failed, errors, passed, summary = _run_pytest([TEST_FILE])
    green = code == 0 and failed == 0 and errors == 0
    print(f"[restored] full M16 file: {summary.strip()} -> {'GREEN' if green else 'NOT GREEN'}")
    print("RESULT:", "all plants ran and failed, code restored" if ok and green else "FAILURE")
    return 0 if ok and green else 1


if __name__ == "__main__":
    raise SystemExit(main())
