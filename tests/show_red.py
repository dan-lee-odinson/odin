"""Show the repository tests failing on purpose in the real working tree, then put it back.

    python tests/show_red.py          every stage
    python tests/show_red.py s1       one stage (s0, s1, s2, s3, deposits)

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


def in_turn(*changes):
    """Several changes to one file, made one after another."""
    def change(data):
        for one in changes:
            data = one(data)
        return data
    return change


def flip_one_byte_in_line(index):
    """Change one byte in the middle of a JSON Lines file's line (counting from 0)."""
    def change(data):
        lines = data.split(b"\n")
        line = bytearray(lines[index])
        line[len(line) // 2] ^= 0x01
        lines[index] = bytes(line)
        return b"\n".join(lines)
    return change


def drop_line(index):
    def change(data):
        lines = data.split(b"\n")
        return b"\n".join(lines[:index] + lines[index + 1:])
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
], "s2": [
    ("one byte changed in the middle of the example log's REQUEST record",
     "tests/test_s2_event_log.py::test_example_log_verifies",
     change_file("log/examples/events.jsonl", flip_one_byte_in_line(6))),
    ("the example log's REQUEST record deleted",
     "tests/test_s2_event_log.py::test_example_log_verifies",
     change_file("log/examples/events.jsonl", drop_line(6))),
    ("the last record's met_s changed, which only the head file can catch (U23)",
     "tests/test_s2_event_log.py::test_example_log_verifies",
     change_file("log/examples/events.jsonl", replace_once(b'"met_s":604,"prev_hash"', b'"met_s":605,"prev_hash"'))),
    ("the example log's head file holding another hash (U23)",
     "tests/test_s2_event_log.py::test_example_log_verifies",
     change_file("log/examples/events.head", lambda data: b"sha256:" + b"0" * 64 + b"\n")),
    ("one hex digit changed in the canonical vector for negative zero (U22)",
     "tests/test_s2_canonical.py::test_canonical_json_reproduces_every_vector",
     change_file("contract/schemas/canonical_vectors.json",
                 replace_once(b'"canonical_hex": "2d302e30"', b'"canonical_hex": "2d302e31"'))),
    ("the log server answering a refused record with 200 (U24)",
     "tests/test_s2_server.py::test_red_a_refused_submission_gets_400_and_writes_nothing[a decision on /log/agent]",
     change_file("log/server.py", replace_once(b'self._reply(400, {"problems": refusal.problems})',
                                               b'self._reply(200, {"problems": refusal.problems})'))),
    ("a Python file in gateway/ that opens a run's truth file",
     "tests/test_s2_truth_guard.py::test_only_the_writers_and_eval_name_the_truth_file",
     add_file("gateway/_red_probe_truth.py", 'open("runs/dev-run-0001/' + "truth" + '.jsonl")\n')),
], "s3": [
    ("BALDUR-0 sending a command across a plan boundary: the plan compared neither with the request nor the basis",
     "tests/test_s3_dispatch.py::test_a_command_allowed_under_one_plan_is_voided_once_the_boundary_passes",
     change_file("gateway/decision.py", in_turn(
         replace_once(b'if request["plan_id"] != ctx.plan.plan_id:', b"if False:"),
         replace_once(b'BASIS = (("plan_id", "PLAN"), ', b"BASIS = (")))),
    ("BALDUR-0 dispatching a command whose class changed while it waited",
     "tests/test_s3_dispatch.py::test_a_class_raised_while_waiting_changes_the_basis",
     change_file("gateway/gateway.py", replace_once(b"elif changed:", b"elif False:"))),
    ("scored mode accepting the development test key",
     "tests/test_s3_signed.py::test_red_scored_mode_refuses_plans_signed_with_the_test_key",
     change_file("gateway/signed.py", replace_once(b'if mode == "DEVELOPMENT":', b"if mode in MODES:"))),
    ("development mode no longer accepting the test key",
     "tests/test_s3_signed.py::test_development_mode_accepts_the_test_key",
     change_file("gateway/signed.py", replace_once(b'accepted.append((DEV_TEST, f"{DEV_TEST} {keytype} {key}"))',
                                                   b"pass"))),
    ("acts verified under tyr0, so a plan's signature passes as an act's",
     "tests/test_s3_signed.py::test_red_a_signed_plan_presented_as_the_act",
     change_file("gateway/signed.py", replace_once(b'ACT_NAMESPACE = "aesir-arm"', b'ACT_NAMESPACE = "tyr0"'))),
    ("plan spans closed at the end, so two plans are in force at 5400",
     "tests/test_s3_decision.py::test_a_plan_is_in_force_from_its_start_up_to_but_not_including_its_end",
     change_file("gateway/plans.py", replace_once(b"self.valid_from_met_s <= met_s < self.valid_until_met_s",
                                                  b"self.valid_from_met_s <= met_s <= self.valid_until_met_s"))),
    ("the ORIGIN check no longer refusing a used nonce",
     "tests/test_s3_decision.py::test_red_origin_a_request_replayed",
     change_file("gateway/decision.py", replace_once(b"if ctx.nonce_reused:", b"if False:"))),
    ("an envelope limit that does not hold no longer raising C1 to C4",
     "tests/test_s3_decision.py::test_an_envelope_limit_that_does_not_hold_raises_c1_to_c4_and_a_lease_can_cover_it",
     change_file("gateway/decision.py", replace_once(b'found["class"] = "C4" if broken else base',
                                                     b'found["class"] = base'))),
    ("stale telemetry blocking the protective commands",
     "tests/test_s3_decision.py::test_stale_or_missing_telemetry_never_blocks_a_protective_command",
     change_file("gateway/decision.py", replace_once(
         b'if request["command"] not in PROTECTIVE and not is_fresh(ctx.frame, ctx.met_s):',
         b"if not is_fresh(ctx.frame, ctx.met_s):"))),
    ("stale telemetry refusing only C1 and C2 at CLASS, so LEASE judges the mode command on an old frame (U25)",
     "tests/test_s3_decision.py::test_red_class_no_fresh_telemetry_refuses_the_mode_command_whatever_its_lease",
     change_file("gateway/decision.py", replace_once(
         b'if request["command"] not in PROTECTIVE and not is_fresh(ctx.frame, ctx.met_s):',
         b'if base in ("C1", "C2") and not is_fresh(ctx.frame, ctx.met_s):'))),
    ("plan verification letting two leases cover one request (U27)",
     "tests/test_s3_signed.py::test_red_overlapping_leases_are_named_in_the_refusal",
     change_file("gateway/plans.py", replace_once(b"shared = _shared(one, other)", b"shared = None"))),
    ("the ORIGIN check no longer refusing a request for another run (U28)",
     "tests/test_s3_decision.py::test_red_origin_a_request_for_another_run",
     change_file("gateway/decision.py", replace_once(b'if request["run_id"] != ctx.run_id:', b"if False:"))),
    ("the PLAN check no longer refusing a request that names another plan (U29)",
     "tests/test_s3_decision.py::test_red_plan_mismatch_a_request_naming_another_plan_or_none",
     change_file("gateway/decision.py", replace_once(b'if request["plan_id"] != ctx.plan.plan_id:', b"if False:"))),
    ("revocation leaving the waiting requests in the queue",
     "tests/test_s3_dispatch.py::test_revocation_voids_every_waiting_request_at_once",
     change_file("gateway/gateway.py", replace_once(b"pending, self._pending = self._pending, []", b"pending = []"))),
    ("a restore act accepted a second time",
     "tests/test_s3_restore.py::test_a_restore_act_is_accepted_once",
     change_file("gateway/acts.py", replace_once(b'elif act["act_id"] in used:', b"elif False:"))),
    ("BALDUR-0 answering a refused body before reading it",
     "tests/test_s3_server.py::test_every_refusal_is_answered_though_its_body_is_large",
     change_file("gateway/server.py", replace_once(b"if length.isdigit() else None", b"if False else None"))),
], "deposits": [
    ("one byte changed in the committed deposit deposits/MC-M1-01.zip",
     "tests/test_deposits.py::test_each_committed_deposit_is_odin_at_its_commit",
     change_file("deposits/MC-M1-01.zip", lambda data: data[:len(data) // 2] + bytes([data[len(data) // 2] ^ 0x01])
                 + data[len(data) // 2 + 1:])),
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
