"""Red-case runner for M17 (one run, two models, picked by seat).

Plants one fault at a time -- in the loop, the start command, or, for
the freeze-guard plants, in config/models.yaml or config/frozen.json
themselves -- runs the test(s) that cover it, and counts only tests
that ran and failed (a failure at collection, or an error, does not
count). Every planted file is restored byte for byte after its plant
and its hash checked before the next one. At the end the whole M17
file is run again, restored, and both config files hash as they did.

Run from the workspace root: python odin/devtools/red_cases_m17.py
Exit 0 only if every plant made its test(s) run and fail, no plant
produced an error, and every file was restored.
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_FILE = "odin/tests/test_m17_two_models.py"


def _t(*names):
    return [f"{TEST_FILE}::{n}" for n in names]


CASES = [
    {
        "name": "an ONBOARD turn answered by the run's model when an onboard model is given",
        "file": "odin/loop/loop.py",
        "find": 'if bundle.get("seat") == "ONBOARD" and self.onboard_adapter is not None:',
        "replace": "if False:  # planted: never pick the onboard adapter",
        "tests": _t("test_onboard_turn_goes_to_onboard_and_ground_to_run_model"),
    },
    {
        "name": "a GROUND turn answered by the onboard model",
        "file": "odin/loop/loop.py",
        "find": 'if bundle.get("seat") == "ONBOARD" and self.onboard_adapter is not None:',
        "replace": "if self.onboard_adapter is not None:  # planted: every seat onboard",
        "tests": _t("test_onboard_turn_goes_to_onboard_and_ground_to_run_model",
                    "test_any_other_seat_uses_run_model"),
    },
    {
        "name": "a MODEL_CALL naming the other model's configuration",
        "file": "odin/loop/loop.py",
        "find": '"config": getattr(adapter, "name", "stand_in"),',
        "replace": '"config": getattr(self.adapter, "name", "stand_in"),  # planted: always the run model',
        "tests": _t("test_onboard_turn_goes_to_onboard_and_ground_to_run_model"),
    },
    {
        "name": "ODIN starting without the onboard model's key",
        "file": "odin/run_odin.py",
        "find": "        missing = _missing_key_var(which)",
        "replace": "        missing = None  # planted: never refuse for a missing key",
        "tests": _t("test_start_without_onboard_models_key_refused"),
    },
    {
        "name": "after a change of seat, the next turn going to the old seat's adapter",
        "file": "odin/loop/loop.py",
        "find": "        adapter = self.adapter_for(bundle)",
        "replace": ("        adapter = getattr(self, '_planted_first_adapter', None) or self.adapter_for(bundle)\n"
                    "        self._planted_first_adapter = adapter  # planted: the first pick sticks"),
        "tests": _t("test_seat_change_between_turns_switches_adapter_each_turn"),
    },
    {
        "name": "a model's settings changed with its frozen.json entry left as it was",
        "file": "config/models.yaml",
        "find": "reasoning_effort: high",
        "replace": "reasoning_effort: low",
        "tests": _t("test_freeze_guard_passes_on_todays_config"),
    },
    {
        "name": "a frozen.json entry changed with the settings left as they were",
        "file": "config/frozen.json",
        "find": "sha256:764c3a01537ba11e8f3fd303c750773498a39e77de9f8552774b15eb491d71a3",
        "replace": "sha256:064c3a01537ba11e8f3fd303c750773498a39e77de9f8552774b15eb491d71a3",
        "tests": _t("test_freeze_guard_passes_on_todays_config"),
    },
    {
        "name": "a model added to config/models.yaml with no frozen.json entry",
        "file": "config/models.yaml",
        "find": "spark_open:",
        "replace": ("glimmer_modal:\n"
                    "  model: planted-glimmer\n"
                    "  reasoning_effort: low\n"
                    "  max_output_tokens: 8192\n"
                    "  timeout_s: 60\n"
                    "  endpoint: http://127.0.0.1:9\n"
                    "  date: 2026-10-30\n\n"
                    "spark_open:"),
        "tests": _t("test_freeze_guard_passes_on_todays_config"),
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
    print(f"[restored] full M17 file: {summary.strip()} -> {'GREEN' if green else 'NOT GREEN'}")
    print("RESULT:", "all plants ran and failed, code restored" if ok and green else "FAILURE")
    return 0 if ok and green else 1


if __name__ == "__main__":
    raise SystemExit(main())
