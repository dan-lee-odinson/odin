"""Show the repository tests failing on purpose in the real working tree, then put it back.

    python tests/show_red.py          every stage
    python tests/show_red.py s1       one stage

For each case: run the real test (it passes), plant one defect, run it again (it must fail),
restore the tree, confirm the restored bytes, and run it a third time (it passes). Planted
files are named _red_probe* and are git-ignored. Exits 0 only if every case behaves.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def change_file(rel, change):
    path = ROOT / rel
    original = path.read_bytes()

    def plant():
        path.write_bytes(change(original))

    def restore():
        path.write_bytes(original)
        return path.read_bytes() == original

    return plant, restore


def add_file(rel, text):
    path = ROOT / rel

    def plant():
        if path.exists():
            sys.exit(f"{rel} already exists; remove it before running this")
        path.write_text(text, encoding="utf-8")

    def restore():
        path.unlink(missing_ok=True)
        return not path.exists()

    return plant, restore


def flip_one_key_character(data):
    principal, keytype, key, comment = data.decode("utf-8").split(" ", 3)
    swapped = "B" if key[30] != "B" else "C"
    return " ".join([principal, keytype, key[:30] + swapped + key[31:], comment]).encode("utf-8")


def replace_once(old, new):
    def change(data):
        if data.count(old) != 1:
            sys.exit(f"expected exactly one {old!r} to change; the file has moved on")
        return data.replace(old, new)
    return change


# The planted text is assembled from pieces so that this file does not trip the scans.
CASES = {"s0": [
    ("CONTRACT.md with one byte appended",
     "tests/test_s0_hashes.py::test_contract_hash",
     change_file("CONTRACT.md", lambda b: b + b" ")),
    (".agents/AGENTS.md with one byte appended",
     "tests/test_s0_hashes.py::test_agents_rules_hash",
     change_file(".agents/AGENTS.md", lambda b: b + b" ")),
    ("keys/allowed_signers with one character of the Director's key changed",
     "tests/test_s0_signers.py::test_allowed_signers_fingerprint",
     change_file("keys/allowed_signers", flip_one_key_character)),
    ("a Python file in harness/ that imports ve",
     "tests/test_s0_huginn_guard.py::test_no_file_imports_ve",
     add_file("harness/_red_probe_ve.py", "import " + "ve\n")),
    ("a Python file in harness/ that opens HUGINN's replay folder",
     "tests/test_s0_huginn_guard.py::test_no_file_opens_forbidden_huginn_paths",
     add_file("harness/_red_probe_path.py", "open('deps/" + "huginn" + "/replay/x')\n")),
    ("a file in runs/scored/ holding a private key",
     "tests/test_s0_secrets.py::test_repository_has_no_secrets",
     add_file("runs/scored/_red_probe_secret.txt",
              "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nnot-a-real-key\n")),
], "s1": [
    ("a good answer example with the payload state set to STANDBY",
     "tests/test_s1_schemas.py::test_good_example_validates[answer/good-command-payload.json]",
     change_file("contract/schemas/examples/answer/good-command-payload.json",
                 replace_once(b'"state": "ON"', b'"state": "STANDBY"'))),
    ("the plan schema loosened so that a plan may prohibit CMD_SAFE_ENTER",
     "tests/test_s1_schemas.py::test_red_bad_example_is_rejected[tyr0_plan - prohibits CMD_SAFE_ENTER]",
     change_file("contract/schemas/tyr0_plan.schema.json",
                 replace_once(b'"items": {"$ref": "common.schema.json#/definitions/unprotected_command"}',
                              b'"items": {"$ref": "common.schema.json#/definitions/command"}'))),
    ("the schemas allowing a payload rate of 20 Hz, past the dictionary's 10 Hz",
     "tests/test_s1_dictionary.py::test_schemas_match_the_pinned_dictionary",
     change_file("contract/schemas/common.schema.json",
                 replace_once(b'"minimum": 0.1, "maximum": 10}', b'"minimum": 0.1, "maximum": 20}'))),
    ("the bundle schema letting an OUTCOME trigger carry the result, which ODIN reads from telemetry (U6)",
     "tests/test_s1_schemas.py::test_red_bad_example_is_rejected[turn_bundle - an OUTCOME trigger carrying the result]",
     change_file("contract/schemas/turn_bundle.schema.json",
                 replace_once(b'"required": ["request_id"], "additionalProperties": false,',
                              b'"required": ["request_id"],'))),
    ("the decision schema letting a record list fewer than all eight checks (U14)",
     "tests/test_s1_schemas.py::test_red_bad_example_is_rejected[decision_record - seven checks, not eight]",
     change_file("contract/schemas/decision_record.schema.json",
                 replace_once(b'"minItems": 8,', b'"minItems": 1,'))),
    ("the observation schema letting EPS_BATT_SOC go YELLOW_HIGH, a limit the dictionary does not give it (U7)",
     "tests/test_s1_dictionary.py::test_schemas_match_the_pinned_dictionary",
     change_file("contract/schemas/observation.schema.json",
                 replace_once(b'"limit_state": {"enum": ["GREEN", "YELLOW_LOW", "RED_LOW"]}',
                              b'"limit_state": {"enum": ["GREEN", "YELLOW_LOW", "YELLOW_HIGH", "RED_LOW"]}'))),
    ("the tool-use schema letting a tool be named by its path rather than docs_lookup or history (U19)",
     "tests/test_s1_schemas.py::test_red_bad_example_is_rejected[tool_use - a tool named by its path]",
     change_file("contract/schemas/tool_use.schema.json",
                 replace_once(b'"enum": ["docs_lookup", "history"]', b'"type": "string"'))),
    ("the model-call schema letting call_index count from 0 (U20)",
     "tests/test_s1_schemas.py::test_red_bad_example_is_rejected[model_call - call_index counting from 0]",
     change_file("contract/schemas/model_call.schema.json",
                 replace_once(b'2026).",\n      "$ref": "common.schema.json#/definitions/count_from_1"',
                              b'2026).",\n      "type": "integer", "minimum": 0'))),
]}


def run_test(node):
    result = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "--no-header", "--tb=short",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True)
    reasons = [line[2:].strip() for line in result.stdout.splitlines()
               if line.startswith("E ") and line[2:].strip()]
    return result.returncode == 0, reasons


def main():
    stages = sys.argv[1:] or list(CASES)
    unknown = [stage for stage in stages if stage not in CASES]
    if unknown:
        sys.exit(f"unknown stage {unknown}; choose from {list(CASES)}")
    cases = [(f"{stage.upper()} {number}/{len(CASES[stage])}", *case)
             for stage in stages for number, case in enumerate(CASES[stage], 1)]
    all_good = True
    for label, title, node, (plant, restore) in cases:
        print(f"[{label}] {title}")
        print(f"      test: {node}")
        before, _ = run_test(node)
        print(f"      before:   {'passed' if before else 'FAILED (tree was not clean)'}")
        plant()
        try:
            planted, reasons = run_test(node)
        finally:
            restored_exactly = restore()
        print(f"      planted:  {'PASSED (the check did not catch it)' if planted else 'FAILED, as intended'}")
        for reason in reasons[:3]:
            print(f"                {reason}")
        after, _ = run_test(node)
        print(f"      restored: {'passed' if after else 'FAILED'}, "
              f"{'bytes identical to before' if restored_exactly else 'BYTES DIFFER'}")
        all_good = all_good and before and not planted and after and restored_exactly
        print()
    print("Every red case failed as intended and the tree is back as it was." if all_good
          else "AT LEAST ONE CASE DID NOT BEHAVE. See above.")
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
