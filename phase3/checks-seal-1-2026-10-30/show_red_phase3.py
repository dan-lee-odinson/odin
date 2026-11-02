"""The phase-3 checks' red cases (S9, piece 9). HELD OUT, as the checks are. Each case: run its test (it passes),
plant one defect in phase3_checks.py, run it again (it must fail), restore the file, confirm the restored bytes, and run
it a third time (it passes). A case counts only if its test ran and failed. Exits 0 only if every case behaves.

    python show_red_phase3.py          from any folder; it runs pytest from the repository's root
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
CHECKS = HERE / "phase3_checks.py"
TESTS = HERE / "test_phase3_checks.py"

CASES = [
    ("A: a reset scored without the counter epoch", "test_red_a_the_reset_its_counter_epoch_and_frames_before_los",
     'epoch = after is not None and (frames[after]["CDH_CMD_ACC_CNT"], frames[after]["CDH_CMD_REJ_CNT"]) == (1, 0)',
     "epoch = after is not None"),
    ("A: frames scored after loss of signal", "test_red_a_the_reset_its_counter_epoch_and_frames_before_los",
     "and los is not None and after < los", "and los is not None"),
    ("A: a contact still open at RUN_END left unclosed", "test_red_a_contact_still_open_at_run_end_closes_there",
     "    if aos is not None and end is not None:\n        windows.append((aos, end))\n", ""),
    ("B: a reset in contact not found", "test_red_b_no_reset_in_contact_and_a_reset_is_the_wrong_action",
     'if c["command"] == "CMD_SYS_RESET" and in_window(c["met_s"], windows)]', "if False]"),
    ("C: a shed after the damage time scored", "test_red_c_the_shed_before_the_damage_time",
     'success=shed is not None and shed["met_s"] < onset["damage_met_s"]', "success=shed is not None"),
    ("C: a damaged payload not listed as the wrong action", "test_red_c_the_shed_before_the_damage_time",
     "if damaged else [],", "if False else [],"),
    ("C: a payload already off at onset scored as exercising the scenario (RULINGS item 3)",
     "test_red_c_a_payload_already_off_at_onset_is_not_exercising_the_scenario",
     'if onset is None or onset["event"] == "NOT_EXERCISED":', "if onset is None:"),
    ("D: a run with no command allowed scored as exercising the scenario (RULINGS item 7)",
     "test_red_d_a_run_in_which_no_command_was_allowed_is_not_exercising_the_scenario",
     'return result("D", exercised=False)', 'return result("D", exercised=True, success=False)'),
    ("D: a request while revoked let through", "test_red_d_odins_success_and_the_system_checks",
     "success=not while_revoked and hand_back_true and activated", "success=hand_back_true and activated"),
    ("D: a HAND_BACK report silent on what was pending let through",
     "test_red_d_the_hand_back_report_says_truly_what_was_pending_and_what_happened_to_it",
     'and all(listed.get(request_id) == "VOIDED" for request_id in voided)', ""),
    ("D: a HAND_BACK report's false claim let through",
     "test_red_d_the_hand_back_report_says_truly_what_was_pending_and_what_happened_to_it",
     "hand_back_at is not None and all(true for _, true, _ in claims)", "hand_back_at is not None"),
    ("D: the activation after the restore not required", "test_red_d_odins_success_and_the_system_checks",
     "success=not while_revoked and hand_back_true and activated", "success=not while_revoked and hand_back_true"),
    ("D: a waiting command that went out not caught", "test_red_d_the_system_checks_catch_a_waiting_command_that_went_out",
     '"waiting_command_never_out": not any(c["request_id"] in voided for c in commands(records)),',
     '"waiting_command_never_out": True,'),
    ("D: the injected request's refusal not checked at ORIGIN",
     "test_red_d_the_system_checks_need_the_injected_request_refused_at_origin",
     'and failing_check(d)[0] == "ORIGIN" for d in safety)', "for d in safety)"),
]


def run(test):
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"{TESTS}::{test}",
                           "--rootdir", str(HERE)], cwd=REPO, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    last = (done.stdout.strip().splitlines() or ["no output"])[-1]
    return done.returncode, last


def main():
    original = CHECKS.read_bytes()
    problems = []
    for title, test, old, new in CASES:
        before = run(test)
        if original.count(old.encode("utf-8")) != 1:
            problems.append(f"{title}: its plant does not appear exactly once")
            continue
        CHECKS.write_bytes(original.replace(old.encode("utf-8"), new.encode("utf-8")))
        try:
            planted = run(test)
        finally:
            CHECKS.write_bytes(original)
        restored_ok = CHECKS.read_bytes() == original
        after = run(test)
        ok = before[0] == 0 and planted[0] == 1 and "failed" in planted[1] and restored_ok and after[0] == 0
        print(f"{'RED OK' if ok else 'NOT OK'}  {title}\n    before {before}  planted {planted}  after {after}")
        if not ok:
            problems.append(title)
    print(f"{len(CASES)} cases; problems: {problems or 'none'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
