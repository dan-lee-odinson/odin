"""Shows every VERDA test failing on a planted change, then passing again.

    python tests/show_red.py            every red case, then the whole suite green
    python tests/show_red.py NAME ...   only the red cases whose test id contains NAME

For each test there is a red case: a change planted in VERDA's source, or in a
temporary copy of an input that the test is pointed at, which must make that test
fail. A test that checks two things that could each go wrong alone has one red
case for each. The runner plants it, runs that one test alone, and restores the source
byte for byte. A red case counts as caught only if the test ran and failed: a
test that did not run, passed, or stopped on an error does not count.

Before planting in a source file it saves the original under .scratch/red-backup,
and on its next start it restores anything a stopped run left planted.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
BACKUP = ROOT / ".scratch" / "red-backup"
# The real inputs, as the tests find them (tests/_support.py): beside VERDA, or where
# VERDA_INPUTS, VERDA_RUNS and VERDA_DICTIONARY point.
INPUTS = Path(os.environ.get("VERDA_INPUTS", ROOT / "inputs"))
RUNS = Path(os.environ.get("VERDA_RUNS", INPUTS / "runs"))
DICTIONARY = Path(os.environ.get("VERDA_DICTIONARY", INPUTS / "dictionaries" / "HUGINN" / "tlm_cmd.yaml"))
SCRIPTED = Path(os.environ.get("VERDA_SCRIPTED", INPUTS / "scripted-commands" / "phase2_scripted_commands.json"))

# Put together from pieces so this file holds none of the names the clean-room test looks for.
OLD_PACKAGE = "v" + "e"
OLD_FOLDER = "view" + "er" + "/"
# A path under a user's own folder, put together the same way.
USER_FOLDER = "C:" + "\\" + "Us" + "ers" + "\\" + "someone" + "\\" + "Documents" + "\\" + "verda"


def edit(path, old, new):
    return ("edit", path, old, new)


def new_file(path, text):
    return ("new", path, text)


def data(make_env):
    return ("data", make_env)


# -- planted inputs, built in a temporary folder -----------------------------------

def changed_runs(tmp):
    runs = Path(tmp, "runs")
    shutil.copytree(RUNS, runs)
    log = runs / "dev-practice-p4" / "events.jsonl"
    data_ = log.read_bytes()
    assert data_.count(b'"route":"UPLINK"') == 1
    log.write_bytes(data_.replace(b'"route":"UPLINK"', b'"route":"COSMOS"'))
    return {"VERDA_RUNS": str(runs)}


def changed_ground_seat_run(tmp):
    runs = Path(tmp, "runs")
    shutil.copytree(RUNS, runs)
    log = runs / "dev-s5-live-ground-seat" / "events.jsonl"
    data_ = log.read_bytes()
    assert data_.count(b'"route":"COSMOS"') == 2
    log.write_bytes(data_.replace(b'"route":"COSMOS"', b'"route":"UPLINK"', 1))
    return {"VERDA_RUNS": str(runs)}


def changed_scripted(old, new):
    def make(tmp):
        text = SCRIPTED.read_text(encoding="utf-8")
        assert text.count(old) == 1, old
        target = Path(tmp, SCRIPTED.name)
        target.write_bytes(text.replace(old, new).encode("utf-8"))
        return {"VERDA_SCRIPTED": str(target)}
    return make


P4_RESET = ('"when": "in contact",\n     "kept_in_odins_runs": false,\n'
            '     "source": "sim/scenarios/P4_hk_generation_halt.yaml:31"')


def changed_dictionary(old, new):
    def make(tmp):
        source = DICTIONARY
        text = source.read_text(encoding="utf-8")
        assert text.count(old) == 1, old
        target = Path(tmp, "tlm_cmd.yaml")
        target.write_bytes(text.replace(old, new).encode("utf-8"))
        return {"VERDA_DICTIONARY": str(target)}
    return make


def contract_without_tool_use(tmp):
    inputs = Path(tmp, "inputs")
    shutil.copytree(INPUTS / "contract", inputs / "contract")
    text = (INPUTS / "CONTRACT.md").read_text(encoding="utf-8")
    assert text.count(", `TOOL_USE`, `RUN_END`") == 1
    (inputs / "CONTRACT.md").write_bytes(text.replace(", `TOOL_USE`, `RUN_END`", ", `RUN_END`").encode("utf-8"))
    return {"VERDA_INPUTS": str(inputs)}


CONVERT = "convert/verda_convert.py"
PASSES = "convert/pass_records.py"
JS = "page/verda.js"

RED_CASES = [
    # tests/test_clean_room.py
    ("test_clean_room.CleanRoom.test_the_scan_sees_verda_files", "the scan skips the convert folder",
     edit("tests/test_clean_room.py", 'SKIP_DIRS = {"inputs",', 'SKIP_DIRS = {"convert", "inputs",')),
    ("test_clean_room.CleanRoom.test_nothing_imports_the_old_viewer_package", "a planted file imports the old viewer package",
     new_file("convert/_red_plant.py", "import %s\n" % OLD_PACKAGE)),
    ("test_clean_room.CleanRoom.test_nothing_names_the_old_viewer_folders", "a planted file names the old viewer folder",
     new_file("page/_red_plant.txt", "deps/huginn/%sindex.html\n" % OLD_FOLDER)),
    ("test_clean_room.CleanRoom.test_no_deposited_file_holds_a_user_folder_path", "README.md gives the runs folder by its full path",
     edit("README.md", "   python convert/verda_convert.py --all <folder holding run folders>\n",
          "   python convert/verda_convert.py --all %s\\inputs\\runs\n" % USER_FOLDER)),
    # tests/test_convert.py
    ("test_convert.CanonicalJson.test_reproduces_every_contract_vector", "canonical JSON gains a space after commas",
     edit(CONVERT, 'separators=(",", ":"),\n                      ensure_ascii=False', 'separators=(", ", ":"),\n                      ensure_ascii=False')),
    ("test_convert.HashChain.test_every_run_verifies", "one record of a copied practice run is changed",
     data(changed_runs)),
    ("test_convert.HashChain.test_every_run_verifies", "one record of the copied ground-seat run is changed",
     data(changed_ground_seat_run)),
    ("test_convert.HashChain.test_a_changed_record_breaks_the_chain", "the chain check stops comparing prev_hash",
     edit(CONVERT, 'if record.get("prev_hash") != prev:', 'if False:')),
    ("test_convert.Limits.test_dictionary_has_the_sixteen_points", "a copied dictionary's yellow staleness limit is 12 s",
     data(changed_dictionary("yellow_s: 10", "yellow_s: 12"))),
    ("test_convert.Limits.test_limit_states_match_every_observation", "a copied dictionary's load-current yellow high is 1.9 A",
     data(changed_dictionary("yh: 1.5", "yh: 1.9"))),
    ("test_convert.TruthMapping.test_truth_matches_every_observation", "battery voltage is mapped to the bus voltage",
     edit(CONVERT, '"EPS_BATT_V": ("eps", "battery_v"),', '"EPS_BATT_V": ("eps", "bus_v"),')),
    ("test_convert.Timelines.test_each_practice_run_has_a_timeline_file", "the index leaves P4 out",
     edit(CONVERT, 'if path.name == "index.js":\n            continue', 'if path.name == "index.js" or "p4" in path.name:\n            continue')),
    ("test_convert.Timelines.test_p3_payload_shed_is_one_allowed_accepted_chain", "outcomes are dropped",
     edit(CONVERT, 'request.update({"outcome": body.get("outcome"),', 'request.update({"outcome": None,')),
    ("test_convert.Timelines.test_p4_reset_and_the_frame_gap", "frame age turns yellow 20 s late",
     edit(CONVERT, 'elif age >= limits["yellow_s"]:', 'elif age >= limits["yellow_s"] + 20:')),
    ("test_convert.Timelines.test_p3_process_has_two_malformed_turns_and_no_request", "malformed answers read as no action",
     edit(CONVERT, 'turn["answer"] = {"kind": "malformed",', 'turn["answer"] = {"kind": "none",')),
    ("test_convert.Timelines.test_check_ins_reports_and_contact", "check-ins land on the reports lane",
     edit(CONVERT, 'self.event("director", met, "Check-in",', 'self.event("reports", met, "Check-in",')),
    ("test_convert.Timelines.test_v1_points_from_both_sources", "the payload rate lane is gone",
     edit(CONVERT, '    ("tlm:PLD_RATE", "Payload rate", ("PLD_RATE",), "chart"),\n', '')),
    ("test_convert.Timelines.test_every_record_is_drawn", "turn records are not marked as drawn",
     edit(CONVERT, '        turn["refs"].append(ref)\n        self.placed.add(ref)\n', '        turn["refs"].append(ref)\n')),
    ("test_convert.Repeatable.test_the_same_inputs_give_the_same_files_whatever_the_hash_seed", "the truth flags are walked in their set's order",
     edit(CONVERT, "                for name in sorted(flags):", "                for name in flags:")),
    ("test_convert.GroundSeat.test_its_bundles_staleness_and_ground_link_are_drawn", "the ground link a bundle recorded is dropped",
     edit(CONVERT, "            if link is not None:", "            if link is None:")),
    ("test_convert.GroundSeat.test_its_derived_frame_age_agrees_with_the_age_it_recorded", "the derived age is a second short",
     edit(CONVERT, "            age = t - newest\n", "            age = max(0, t - newest - 1)\n")),
    # tests/test_page.py
    ("test_page.NoNetwork.test_no_network_calls_or_addresses", "verda.js gains a fetch",
     edit(JS, "  function start() {", "  function start() {\n    fetch('timelines/index.js');")),
    ("test_page.NoNetwork.test_html_loads_only_files_beside_it", "index.html gains an icon link",
     edit("page/index.html", '<link rel="stylesheet" href="verda.css">', '<link rel="stylesheet" href="verda.css">\n<link rel="icon" href="icon.png">')),
    ("test_page.NoNetwork.test_content_security_policy_refuses_connections", "the policy allows connections to the page's origin",
     edit("page/index.html", "connect-src 'none'", "connect-src 'self'")),
    ("test_page.NoWriting.test_page_writes_nothing", "verda.js saves to localStorage",
     edit(JS, "  function start() {", "  function start() {\n    window.localStorage.setItem('verda', '1');")),
    ("test_page.NoWriting.test_recorded_text_is_never_parsed_as_html", "the inspector takes records as HTML",
     edit(JS, "$('inspector').textContent = body;", "$('inspector').innerHTML = body;")),
    # tests/test_page_in_browser.py
    ("test_page_in_browser.PageInBrowser.test_asks_only_for_its_own_files_on_disk", "the page asks a local address for an image",
     edit(JS, "  function start() {", "  function start() {\n    new Image().src = 'http://127.0.0.1:9/verda-red.png';")),
    ("test_page_in_browser.PageInBrowser.test_no_script_or_console_errors", "the page writes an error to the console",
     edit(JS, "  function start() {", "  function start() {\n    console.error('VERDA red case');")),
    ("test_page_in_browser.PageInBrowser.test_draws_every_lane_of_each_run", "the contact lane is not drawn",
     edit(JS, "const lanes = tl.lanes.filter((l) => !(", "const lanes = tl.lanes.filter((l) => l.id !== 'contact' && !(")),
    ("test_page_in_browser.PageInBrowser.test_hover_and_click_show_a_request_and_its_records", "clicks on the timeline do nothing",
     edit(JS, "if (target) { inspectHit(S.hits[Number(target.getAttribute('data-hit'))]); return; }", "if (target) { return; }")),
    ("test_page_in_browser.PageInBrowser.test_play_moves_the_playhead", "playback stands still",
     edit(JS, "setMet(S.met + dt * S.speed);", "setMet(S.met);")),
    ("test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_directors_command_and_his_rows", "clicks on the Director's command show nothing",
     edit(JS, "    } else if (p.passCommand) {", "    } else if (false) {")),
    ("test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_scenarios_command_apart_from_his", "a click names the scenario's command the Director's",
     edit(JS, "inspect('The scenario\u2019s command \u00b7 MET ' + c.met_s", "inspect('The Director\u2019s command \u00b7 MET ' + c.met_s")),
    ("test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_scenarios_command_apart_from_his", "the lane's note is cut to the label column",
     edit(JS, "fit(sub, (lane.kind === 'chart' ? LABEL_W : PLOT_X) - 22)", "fit(sub, LABEL_W - 22)")),
    ("test_page_in_browser.PageInBrowser.test_the_ground_seat_age_lane_names_what_its_bundles_recorded", "the strip above the age chart is never drawn",
     edit(JS, "      if (lane.strip) {", "      if (!lane.strip) {")),
    # tests/test_passes.py
    ("test_passes.PassFiles.test_reads_all_five_passes", "each pass takes the last plan of its scenario, whatever its window",
     edit(PASSES, '        s = overlap(pass_data["met_range"], [plan["aos_met_s"], plan["los_met_s"]])\n', '        s = 1.0\n')),
    ("test_passes.PassFiles.test_p1_reads_both_blocks_of_repeated_columns", "arguments are read from the header's first block only",
     edit(PASSES, "            for i, name in enumerate(c_header[3:], start=3):", "            for i, name in enumerate(c_header[3:11], start=3):")),
    ("test_passes.PassFiles.test_what_his_telemetry_showed_next", "his counters are watched for 0 s after a command",
     edit(PASSES, "OUTCOME_WINDOW_S = 10", "OUTCOME_WINDOW_S = 0")),
    ("test_passes.KnownCommandTimes.test_one_known_command_time_on_each_side", "the Director's command takes the MET of the frame after it",
     edit(PASSES, '        met = before["met_s"] + (t - before["utc_s"]) * rate\n', '        met = after["met_s"]\n')),
    ("test_passes.KnownCommandTimes.test_one_known_command_time_on_each_side", "ODIN's dispatch is placed a second late",
     edit(CONVERT, 'request.update({"dispatch_met_s": met, "route": body.get("route")})', 'request.update({"dispatch_met_s": met + 1, "route": body.get("route")})')),
    ("test_passes.LineUp.test_each_pass_lines_up_with_its_runs", "no run pairs with a pass",
     edit(CONVERT, '    best, score = None, 0.5\n    if summary["met_range"] is None:', '    best, score = None, 1.5\n    if summary["met_range"] is None:')),
    ("test_passes.LineUp.test_his_frame_age_shows_the_gap_in_his_p4_frames", "his frame age forgets the gap in his frames",
     edit(PASSES, "        age = t - newest\n", "        age = 0\n")),
    ("test_passes.ScenarioCommands.test_reads_the_seven_and_checks_each_against_its_plan", "a copied file says P4's reset falls before contact and is kept",
     data(changed_scripted(P4_RESET, P4_RESET.replace('"in contact"', '"before contact"').replace("false", "true")))),
    ("test_passes.ScenarioCommands.test_on_his_side_as_the_scenarios_and_never_his", "the scenario's commands are filed among his",
     edit(CONVERT, '    timeline["pass_commands"] = commands\n    timeline["scenario_commands"] = scenario\n',
          '    timeline["pass_commands"] = commands + scenario\n    timeline["scenario_commands"] = scenario\n')),
    ("test_passes.ScenarioCommands.test_on_his_side_as_the_scenarios_and_never_his", "the lane no longer says ODIN's runs drop the in-contact ones",
     edit(CONVERT, "note, short = _scenario_note(entry), \"ODIN's runs drop the in-contact ones\"",
          "note, short = _scenario_note(entry), \"The scenario's own\"")),
    ("test_passes.ScenarioCommands.test_what_his_telemetry_showed_after_the_scenarios_commands", "the frame stamped with the command's MET counts as before it",
     edit(PASSES, '        if frame["met_s"] < met_s:\n', '        if frame["met_s"] <= met_s:\n')),
    ("test_passes.ScenarioCommands.test_a_span_his_command_shares_with_the_scenarios_is_credited_to_neither", "a shared span is never looked for",
     edit(CONVERT, '            if shared and c["outcome"]["kind"] != "outside":', '            if False:')),
    ("test_passes.ScenarioCommands.test_odins_runs_dropped_exactly_the_in_contact_ones", "a copied file puts P4's reset at MET 1321",
     data(changed_scripted('"met_s": 1320,', '"met_s": 1321,'))),
    # tests/test_record_types.py
    ("test_record_types.RecordTypes.test_contract_and_schema_agree", "a copied contract drops TOOL_USE from its list",
     data(contract_without_tool_use)),
    ("test_record_types.RecordTypes.test_every_contract_type_is_shown_or_listed", "TOOL_USE is missing from VERDA's table",
     edit("convert/record_types.py", '    "TOOL_USE": "In its turn\'s record list, and a tool count on the turn\'s marker",\n', '')),
    # tests/test_watch_only.py
    ("test_watch_only.WatchOnly.test_converter_writes_only_its_files_and_leaves_the_run_untouched", "the converter leaves a file in the run folder",
     edit(CONVERT, '    path = _write_output(out_dir, timeline["id"] + ".js", timeline_script(timeline))\n',
          '    path = _write_output(out_dir, timeline["id"] + ".js", timeline_script(timeline))\n    _write_output(run_dir, "verda-was-here.txt", "x")\n')),
    ("test_watch_only.WatchOnly.test_with_passes_it_writes_only_timelines_and_leaves_passes_and_plans_untouched", "the converter leaves a file in a pass folder",
     edit(CONVERT, '    name = timeline["id"] + ".js"\n', '    name = timeline["id"] + ".js"\n    _write_output(pass_dir, "verda-was-here.txt", "x")\n')),
    ("test_watch_only.WatchOnly.test_output_names_cannot_leave_the_folder", "output names may hold a backslash",
     edit(CONVERT, 'if "/" in name or "\\\\" in name or name in', 'if "/" in name or name in')),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def restore_leftovers():
    if not BACKUP.exists():
        return
    for saved in sorted(p for p in BACKUP.rglob("*") if p.is_file()):
        rel = saved.relative_to(BACKUP)
        if saved.name.endswith(".absent"):
            target = ROOT / str(rel)[:-len(".absent")]
            if target.exists():
                target.unlink()
            print("restored: removed the planted %s" % target.relative_to(ROOT).as_posix())
        else:
            shutil.copyfile(saved, ROOT / rel)
            print("restored %s from a stopped run" % rel.as_posix())
        saved.unlink()
    shutil.rmtree(BACKUP, ignore_errors=True)


def run_test(test_id, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-m", "unittest", "-v", test_id], cwd=TESTS, env=env,
                          capture_output=True, text=True, timeout=300)
    out = done.stdout + done.stderr
    ran = re.search(r"^Ran (\d+) tests? in", out, re.M)
    failures = re.search(r"FAILED \((?:[^)]*?)failures=(\d+)", out)
    errors = re.search(r"FAILED \((?:[^)]*?)errors=(\d+)", out)
    return {"code": done.returncode, "ran": int(ran.group(1)) if ran else 0,
            "failures": int(failures.group(1)) if failures else 0,
            "errors": int(errors.group(1)) if errors else 0, "output": out}


def first_failure_line(output):
    lines = output.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("AssertionError") or line.startswith("    raise AssertionError"):
            return line.strip()[:160]
    for line in lines:
        if "Error:" in line:
            return line.strip()[:160]
    return ""


def one_red(test_id, what, plant):
    kind = plant[0]
    env = {}
    tmp = None
    planted = []
    try:
        if kind == "edit":
            _, rel, old, new = plant
            path = ROOT / rel
            original = path.read_bytes()
            text = original.decode("utf-8")
            if text.count(old) != 1:
                return {"caught": False, "note": "the plant does not match %s exactly once" % rel}
            (BACKUP / rel).parent.mkdir(parents=True, exist_ok=True)
            (BACKUP / rel).write_bytes(original)
            planted.append((path, original))
            path.write_bytes(text.replace(old, new).encode("utf-8"))
        elif kind == "new":
            _, rel, text = plant
            path = ROOT / rel
            if path.exists():
                return {"caught": False, "note": "%s already exists" % rel}
            (BACKUP / (rel + ".absent")).parent.mkdir(parents=True, exist_ok=True)
            (BACKUP / (rel + ".absent")).write_bytes(b"")
            planted.append((path, None))
            path.write_bytes(text.encode("utf-8"))
        else:
            tmp = tempfile.mkdtemp(prefix="verda-red-")
            env = plant[1](tmp)
        result = run_test(test_id, env)
    finally:
        for path, original in planted:
            if original is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(original)
        shutil.rmtree(BACKUP, ignore_errors=True)
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    for path, original in planted:
        if original is not None and hashlib.sha256(original).hexdigest() != sha(path):
            raise SystemExit("could not restore %s" % path)
    caught = result["ran"] >= 1 and result["code"] == 1 and result["failures"] >= 1
    note = first_failure_line(result["output"])
    if result["ran"] == 0:
        note = "NO TEST RAN"
    elif result["code"] == 0:
        note = "THE TEST STILL PASSED"
    elif result["failures"] == 0:
        note = "STOPPED ON AN ERROR, NOT A FAILURE: " + note
    return {"caught": caught, "note": note, "result": result}


def main(argv):
    restore_leftovers()
    wanted = argv[1:]
    cases = [c for c in RED_CASES if not wanted or any(w in c[0] for w in wanted)]
    listed = discover_tests()
    covered = {c[0] for c in RED_CASES}
    missing = sorted(set(listed) - covered)
    unknown = sorted(covered - set(listed))
    print("VERDA red cases: %d tests, %d red cases" % (len(listed), len(RED_CASES)))
    if missing:
        print("TESTS WITH NO RED CASE: " + ", ".join(missing))
    if unknown:
        print("RED CASES FOR NO TEST: " + ", ".join(unknown))
    caught_all = not missing and not unknown
    for number, (test_id, what, plant) in enumerate(cases, start=1):
        outcome = one_red(test_id, what, plant)
        mark = "caught" if outcome["caught"] else "NOT CAUGHT"
        print("%2d. %-10s %s\n      planted: %s\n      failed with: %s" % (number, mark, test_id, what, outcome["note"]))
        caught_all = caught_all and outcome["caught"]
    print("\nThe whole suite, with nothing planted:")
    green = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(TESTS)], cwd=ROOT,
                           capture_output=True, text=True, timeout=600, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    tail = (green.stdout + green.stderr).strip().split("\n")[-3:]
    print("  " + "\n  ".join(tail))
    ok = caught_all and green.returncode == 0
    print("\nRESULT: %s" % ("every red case caught, and the suite passes" if ok else "NOT ALL RED CASES CAUGHT, OR THE SUITE FAILS"))
    return 0 if ok else 1


def discover_tests():
    import unittest
    sys.path.insert(0, str(TESTS))
    suite = unittest.defaultTestLoader.discover(str(TESTS))
    out = []

    def walk(item):
        if isinstance(item, unittest.TestSuite):
            for sub in item:
                walk(sub)
        else:
            out.append(item.id())
    walk(suite)
    return out


if __name__ == "__main__":
    sys.exit(main(sys.argv))
