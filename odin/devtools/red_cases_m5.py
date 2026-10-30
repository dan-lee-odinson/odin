"""Red-case runner for M5 prep (glimmer_modal).

Plants one fault at a time in the real source, runs the one M5 test
that covers it, and counts only tests that ran and failed (a failure
at collection, or an error, does not count). The source file is
restored byte for byte after each plant and its hash checked before
the next one. At the end the whole M5 file is run again, restored.

Run from the workspace root: python odin/devtools/red_cases_m5.py
Exit 0 only if every plant made its test run and fail, no plant
produced an error, and every source was restored.
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_FILE = "odin/tests/test_m5_glimmer_modal.py"

CASES = [
    {
        "name": "request sent to a URL other than the configured endpoint",
        "file": "odin/adapters/glimmer_modal.py",
        "find": 'return f"{base}/v1/chat/completions"',
        "replace": 'return f"{base}/v1/wrong-completions"',
        "test": f"{TEST_FILE}::test_request_to_configured_endpoint_with_headers_and_json_schema",
    },
    {
        "name": "a header missing (Modal-Secret dropped)",
        "file": "odin/adapters/glimmer_modal.py",
        "find": 'return {"Modal-Key": key, "Modal-Secret": secret}',
        "replace": 'return {"Modal-Key": key}',
        "test": f"{TEST_FILE}::test_request_to_configured_endpoint_with_headers_and_json_schema",
    },
    {
        "name": "a response_format that is not json_schema",
        "file": "odin/adapters/glimmer_modal.py",
        "find": 'body["response_format"] = response_format',
        "replace": 'body["response_format"] = {"type": "json_object"}',
        "test": f"{TEST_FILE}::test_request_to_configured_endpoint_with_headers_and_json_schema",
    },
    {
        "name": "a key's value written into the log (MODEL_CALL record)",
        "file": "odin/adapters/glimmer_modal.py",
        "find": ('            sink.append(model_call_body(\n'
                 '                config=self.name, provider=self.provider,\n'
                 '                model_id=self.model_id,\n'
                 '                reasoning_effort=self.reasoning_effort,\n'
                 '                max_output_tokens=self.max_output_tokens,\n'
                 '                turn_id=turn_id, call_index=call_index, status="OK",'),
        "replace": ('            sink.append(model_call_body(\n'
                    '                config=self.name, provider=self.provider + headers["Modal-Key"],\n'
                    '                model_id=self.model_id,\n'
                    '                reasoning_effort=self.reasoning_effort,\n'
                    '                max_output_tokens=self.max_output_tokens,\n'
                    '                turn_id=turn_id, call_index=call_index, status="OK",'),
        "test": f"{TEST_FILE}::test_key_values_never_in_log_ledger_or_files",
    },
    {
        "name": "a missing key variable accepted at start",
        "file": "odin/run_odin.py",
        "find": ("    for var in KEYS_FOR_MODEL.get(model, ()):\n"
                 "        if not os.environ.get(var):"),
        "replace": ("    for var in KEYS_FOR_MODEL.get(model, ()):\n"
                    "        if False:  # planted: never refuse"),
        "test": f"{TEST_FILE}::test_missing_proxy_variable_refuses_at_start",
    },
    {
        "name": "the charge computed per call instead of per GPU-second",
        "file": "odin/spend/meter.py",
        "find": 'return float(seconds) * float(prices["per_gpu_second"])',
        "replace": 'return float(prices["per_gpu_second"])',
        "test": f"{TEST_FILE}::test_charge_is_gpu_seconds_times_price",
    },
    {
        "name": "a call past $125 allowed (Modal stop raised)",
        "file": "odin/spend/meter.py",
        "find": '"MODAL": 125.0',
        "replace": '"MODAL": 125000.0',
        "test": f"{TEST_FILE}::test_call_that_would_pass_125_is_refused",
    },
    {
        "name": "a code path added that starts a server",
        "file": "odin/adapters/glimmer_modal.py",
        "find": "        return payload, usage, latency",
        "replace": ("        return payload, usage, latency\n\n\n"
                    "def _planted_lifecycle(server):\n"
                    "    server.start()"),
        "test": f"{TEST_FILE}::test_adapter_has_no_code_path_that_starts_warms_or_stops_a_server",
    },
]


def _run_pytest(node):
    done = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q"],
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
            code, failed, errors, passed, summary = _run_pytest(case["test"])
        finally:
            path.write_bytes(original)
        restored = hashlib.sha256(path.read_bytes()).hexdigest() == digest
        verdict = "RED OK" if (failed >= 1 and errors == 0 and code != 0 and restored) else "NOT RED"
        if verdict != "RED OK":
            ok = False
        print(f"[{i}] {case['name']}\n"
              f"    plant: {case['file']}\n"
              f"    test:  {case['test'].split('::')[-1]}\n"
              f"    ran: {failed} failed, {passed} passed, {errors} errors "
              f"(exit {code}); restored: {restored} -> {verdict}\n"
              f"    pytest: {summary.strip()}")
    code, failed, errors, passed, summary = _run_pytest(TEST_FILE)
    green = code == 0 and failed == 0 and errors == 0
    print(f"[restored] full M5 file: {summary.strip()} -> {'GREEN' if green else 'NOT GREEN'}")
    print("RESULT:", "all plants ran and failed, code restored" if ok and green else "FAILURE")
    return 0 if ok and green else 1


if __name__ == "__main__":
    raise SystemExit(main())
