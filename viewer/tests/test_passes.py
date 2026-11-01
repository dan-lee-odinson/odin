"""V2: the Director's flown passes, beside ODIN's runs on one MET axis.

The brief's test for V2 is KnownCommandTimes: one known command time on each
side, checked against its source file. On the Director's side, his P3 load shed:
its UTC time in commands.csv, placed between the two frames of telemetry_hk.csv
that bracket it, worked out here with this file's own reading of the two CSV
files. On ODIN's side, the practice run's load shed: the DISPATCH record in
events.jsonl.

His passes also carried the commands each scenario sent by itself. They are
shown on his side as the scenario's, never as his, and ODIN's runs drop the ones
in contact: ScenarioCommands checks both, against the plans and ODIN's own runs.
"""

import calendar
import csv
import json
import re
import tempfile
import time
import unittest
from pathlib import Path

import _support as S
import huginn_dictionary
import pass_records
import scripted_commands
import verda_convert as vc

# For each pass: frames, commands, and the phase-2 plan whose contact window holds it.
EXPECTED = {
    "2026-09-13-P1": (425, 2, "TYR0-P2-PASS1-v1"),
    "2026-09-20-P2a": (329, 0, "TYR0-P2-PASS2A-v1"),
    "2026-09-20-P2b": (428, 1, "TYR0-P2-PASS2B-v1"),
    "2026-10-11-P3": (427, 1, "TYR0-P2-PASS3-v1"),
    "2026-10-11-P4": (308, 1, "TYR0-P2-PASS4-v1"),
}


def utc(text):
    """A COSMOS time as seconds since 1970, read without pass_records."""
    base, _, frac = text.rstrip("Z").partition(".")
    return calendar.timegm(time.strptime(base, "%Y-%m-%dT%H:%M:%S")) + (float("0." + frac) if frac else 0.0)


def rows_of(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


_SHARED = {}


def all_timelines():
    """Every run, beside his passes, converted once for this module into a folder kept until it ends."""
    if "timelines" not in _SHARED:
        _SHARED["tmp"] = tempfile.TemporaryDirectory()
        _SHARED["timelines"] = {
            timeline["id"]: timeline for _, path, timeline in
            vc.convert_all(S.all_runs(), Path(_SHARED["tmp"].name), S.dictionary_path(), True, S.passes_dir(),
                           S.plans_dir(), S.scripted_path())
            if path is not None}
    return _SHARED["timelines"]


def tearDownModule():
    if "tmp" in _SHARED:
        _SHARED["tmp"].cleanup()


class PassFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        points = huginn_dictionary.read_points(S.dictionary_path())
        plans = vc.read_plans(S.plans_dir())
        cls.passes = {name: pass_records.read_pass(S.passes_dir() / name, points) for name in S.PASSES}
        cls.plans = {name: pass_records.plan_for(p, plans) for name, p in cls.passes.items()}

    def test_reads_all_five_passes(self):
        for name, (frames, commands, plan_id) in EXPECTED.items():
            with self.subTest(passed=name):
                p = self.passes[name]
                self.assertEqual(p["problems"], [])
                self.assertEqual((len(p["frames"]), len(p["commands"])), (frames, commands))
                self.assertEqual((self.plans[name] or {}).get("plan_id"), plan_id)
        self.assertNotIn("commands.csv", self.passes["2026-09-20-P2a"]["files"])

    def test_p1_reads_both_blocks_of_repeated_columns(self):
        # P1's commands.csv holds two packets' columns side by side, with OPCODE and the
        # packet times named twice; its second command fills only the second block.
        commands = self.passes["2026-09-13-P1"]["commands"]
        self.assertEqual([(c["command"], c["parameters"]) for c in commands],
                         [("CMD_PLD_SET_STATE", {"state": "ON"}), ("CMD_PLD_SET_RATE", {"rate": 2})])
        self.assertEqual(commands[1]["fields"].get("OPCODE#2"), "2")
        self.assertAlmostEqual(commands[1]["met_s"], 142.678, places=3)

    def test_what_his_telemetry_showed_next(self):
        seen = {name: [(c["outcome"]["kind"], c["outcome"].get("met_s")) for c in p["commands"]]
                for name, p in self.passes.items()}
        self.assertEqual(seen, {
            "2026-09-13-P1": [("accepted", 88), ("accepted", 143)],
            "2026-09-20-P2a": [],
            "2026-09-20-P2b": [("accepted", 22006)],
            "2026-10-11-P3": [("accepted", 959)],
            "2026-10-11-P4": [("unchanged", None)],
        })


class KnownCommandTimes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        _, cls.timeline = vc.convert(S.runs_dir() / "dev-practice-p3", Path(cls.tmp.name), S.dictionary_path(),
                                     pass_dir=S.passes_dir() / "2026-10-11-P3", plans_dir=S.plans_dir())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_one_known_command_time_on_each_side(self):
        # The Director's side: his load shed in P3, from his two CSV files.
        folder = S.passes_dir() / "2026-10-11-P3"
        sent = [r for r in rows_of(folder / "commands.csv")[1:] if r[2] == "CMD_PLD_SET_STATE"]
        self.assertEqual(len(sent), 1)
        t = utc(sent[0][0])
        telemetry = rows_of(folder / "telemetry_hk.csv")
        i_time, i_met = telemetry[0].index("TIME"), telemetry[0].index("CDH_MET")
        frames = sorted((utc(r[i_time]), int(r[i_met])) for r in telemetry[1:])
        before = [f for f in frames if f[0] <= t][-1]
        after = [f for f in frames if f[0] > t][0]
        self.assertEqual((before[1], after[1]), (958, 959))
        expected = before[1] + (t - before[0]) * (after[1] - before[1]) / (after[0] - before[0])
        his = [c for c in self.timeline["pass_commands"] if c["command"] == "CMD_PLD_SET_STATE"]
        self.assertEqual(len(his), 1)
        self.assertAlmostEqual(his[0]["met_s"], expected, places=3)
        self.assertAlmostEqual(his[0]["met_s"], 958.539, places=3)

        # ODIN's side: its load shed in dev-practice-p3, the DISPATCH record of its event log.
        with open(S.runs_dir() / "dev-practice-p3" / "events.jsonl", encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle]
        dispatch = [r for r in records if r["type"] == "DISPATCH" and r["body"]["command"] == "CMD_PLD_SET_STATE"]
        self.assertEqual(len(dispatch), 1)
        self.assertEqual(dispatch[0]["met_s"], 901)
        ours = [r for r in self.timeline["requests"] if r["command"] == "CMD_PLD_SET_STATE"]
        self.assertEqual([r["dispatch_met_s"] for r in ours], [dispatch[0]["met_s"]])


class LineUp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.timelines = all_timelines()

    def test_each_pass_lines_up_with_its_runs(self):
        beside = {tid: (t["header"].get("pass") or {}).get("name") for tid, t in self.timelines.items()}
        expected = {
            "dev-practice-p3": "2026-10-11-P3",
            "dev-practice-p3-process": "2026-10-11-P3",
            "dev-practice-p4": "2026-10-11-P4",
            # The ground-seat run flew P3's scenario on 28 October, MET 800 to 909: it covers a
            # quarter of his P3 frames, so it stands alone.
            "dev-s6-0001": None,
            S.PREVIEW_RUN: "2026-10-11-P3",
        }
        # Each scored run beside his pass of its plan. Every pass of his now has runs, so none stands alone.
        expected.update({name: S.PASS_OF[name.split("-")[1]] for name in S.SCORED_RUNS})
        self.assertEqual(beside, expected)
        for tid, t in self.timelines.items():
            if beside[tid] is None:
                self.assertNotIn("director", t["sources"])
                continue
            with self.subTest(timeline=tid):
                frames = t["series"]["director:EPS_BATT_V"]["samples"]
                first, last = frames[0][0], frames[-1][0]
                if t["header"].get("pass_only"):
                    window = [s for s in t["spans"] if s["lane"] == "contact"][0]
                else:
                    window = [s for s in t["spans"] if s["lane"] == "contact" and s.get("row", 0) == 0][0]
                # His frames lie inside the run's contact window, or for a pass alone its plan's, within 20 s.
                self.assertGreaterEqual(first, window["start"] - 20)
                self.assertLessEqual(last, window["end"] + 20)
                self.assertIn("pass-commands", [lane["id"] for lane in t["lanes"]])

    def test_a_run_pairs_with_the_pass_flown_under_its_plan(self):
        # Two made-up P2 runs with the same MET span, 0 to 22230 s, which covers his P2a and P2b frames
        # alike; each is flown under one pass's plan, and that plan, not the span, decides.
        points = huginn_dictionary.read_points(S.dictionary_path())
        passes = vc.read_passes(S.passes_dir(), points)
        plans = vc.read_plans(S.plans_dir())
        paired = {}
        with tempfile.TemporaryDirectory() as tmp:
            for plan_id in ("TYR0-P2-PASS2A-v1", "TYR0-P2-PASS2B-v1"):
                run = Path(tmp, plan_id)
                run.mkdir()
                records = [{"type": "RUN_START", "met_s": 0, "body": {"scenario_id": "P2"}},
                           {"type": "PLAN_IN_FORCE", "met_s": 0, "body": {"plan_id": plan_id}},
                           {"type": "RUN_END", "met_s": 22230, "body": {}}]
                (run / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
                paired[plan_id] = (vc.pass_for_run(run, passes, plans) or {}).get("name")
        self.assertEqual(paired, {"TYR0-P2-PASS2A-v1": "2026-09-20-P2a", "TYR0-P2-PASS2B-v1": "2026-09-20-P2b"})

    def test_his_frame_age_shows_the_gap_in_his_p4_frames(self):
        age = {q[0]: q for q in self.timelines["dev-practice-p4"]["series"]["director:FRAME_AGE"]["samples"]}
        self.assertEqual(age[1199][1:3], [0, "GREEN"])
        self.assertEqual(age[1229][1:3], [30, "RED"])
        self.assertEqual(age[1319][1:3], [120, "RED"])
        self.assertEqual(age[1320][1:3], [0, "GREEN"])
        p3 = self.timelines["dev-practice-p3"]["series"]["director:FRAME_AGE"]["samples"]
        self.assertEqual(max(q[1] for q in p3), 0)


class ScenarioCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.timelines = all_timelines()
        cls.scripted = vc.read_scripted(S.scripted_path(), S.plans_dir())

    def test_reads_the_seven_and_checks_each_against_its_plan(self):
        s = self.scripted
        self.assertEqual(s["problems"], [])
        listed = [(e["pass"], c["met_s"], c["command"], c["when"], c["kept_in_odins_runs"])
                  for e in s["passes"].values() for c in e["commands"]]
        on = ("CMD_PLD_SET_STATE", "before contact", True)
        self.assertEqual(sorted(listed), [
            ("P1", 180, "CMD_PLD_SET_STATE", "in contact", False),
            ("P1", 240, "CMD_PLD_SET_RATE", "in contact", False),
            ("P2A", 120) + on, ("P2B", 120) + on, ("P3", 120) + on, ("P4", 120) + on,
            ("P4", 1320, "CMD_SYS_RESET", "in contact", False)])
        # Each pass's window is its plan file's, read here without the reader.
        for plan_file in sorted(S.plans_dir().glob("*.yaml")):
            text = plan_file.read_text(encoding="utf-8")

            def field(key):
                return re.search(r"^\s*%s:\s*(\S+)\s*$" % key, text, re.M).group(1)
            with self.subTest(plan=plan_file.name):
                self.assertEqual(s["passes"][field("plan_id")]["contact_window"],
                                 {"aos_met_s": int(field("aos_met_s")), "los_met_s": int(field("los_met_s"))})

    def test_on_his_side_as_the_scenarios_and_never_his(self):
        p4 = self.timelines["dev-practice-p4"]
        self.assertEqual([(c["command"], round(c["met_s"], 3)) for c in p4["pass_commands"]], [("CMD_SYS_RESET", 1341.055)])
        self.assertEqual([(c["met_s"], c["command"], c["when"], c["kept_in_odins_runs"], c["source"])
                          for c in p4["scenario_commands"]],
                         [(120, "CMD_PLD_SET_STATE", "before contact", True, "sim/scenarios/P4_hk_generation_halt.yaml:28"),
                          (1320, "CMD_SYS_RESET", "in contact", False, "sim/scenarios/P4_hk_generation_halt.yaml:31")])
        p1 = self.timelines["PH2-PASS1-SPARK-R1"]
        self.assertEqual([c["command"] for c in p1["pass_commands"]], ["CMD_PLD_SET_STATE", "CMD_PLD_SET_RATE"])
        self.assertEqual([c["met_s"] for c in p1["scenario_commands"]], [180, 240])
        for tid, t in self.timelines.items():
            if "director" not in t["sources"]:
                self.assertNotIn("scenario_commands", t)
                continue
            with self.subTest(timeline=tid):
                ids = [lane["id"] for lane in t["lanes"]]
                self.assertEqual(ids[ids.index("pass-commands") + 1], "scenario-commands")
                lane = t["lanes"][ids.index("scenario-commands")]
                self.assertEqual(lane["source"], "scenario")
                self.assertEqual(t["sources"]["scenario"]["kind"], "scenario_commands")
                self.assertIn("They are not the Director's.", lane["note"])
                self.assertIn("ODIN's runs keep the ones before contact and drop the ones in contact", lane["note"])
                self.assertEqual(lane["note_short"], "ODIN's runs drop the in-contact ones")
                his = {(c["command"], c["met_s"]) for c in t["pass_commands"]}
                for c in t["scenario_commands"]:
                    self.assertNotIn((c["command"], c["met_s"]), his)
                    self.assertTrue(c["summary"].endswith("ODIN's runs %s it" % ("keep" if c["kept_in_odins_runs"] else "drop")))
                listed = scripted_commands.for_plan(self.scripted, t["header"]["pass"]["plan_id"])
                self.assertEqual(len(t["scenario_commands"]), len(listed["commands"]))

    def test_what_his_telemetry_showed_after_the_scenarios_commands(self):
        seen = {tid: [(c["met_s"], c["outcome"]["kind"], c["outcome"].get("met_s"), c["outcome"].get("before_met_s"))
                      for c in t["scenario_commands"]] for tid, t in self.timelines.items() if "scenario_commands" in t}
        self.assertEqual(seen["PH2-PASS1-SPARK-R1"], [(180, "accepted", 180, 179), (240, "accepted", 240, 239)])
        self.assertEqual(seen["dev-practice-p4"], [(120, "outside", None, None), (1320, "unchanged", None, 1199)])
        self.assertEqual(seen["dev-practice-p3"], [(120, "outside", None, None)])
        # His P1 counter, read here from his CSV file: it steps up at the two METs the scenario sent its commands.
        telemetry = rows_of(S.passes_dir() / "2026-09-13-P1" / "telemetry_hk.csv")
        i_met, i_acc = telemetry[0].index("CDH_MET"), telemetry[0].index("CDH_CMD_ACC_CNT")
        acc = {int(r[i_met]): int(r[i_acc]) for r in telemetry[1:]}
        self.assertEqual([(acc[m - 1], acc[m]) for m in (180, 240)], [(2, 3), (3, 4)])

    def test_a_span_his_command_shares_with_the_scenarios_is_credited_to_neither(self):
        # In the five passes, no counter change falls where both his command and the scenario's were sent.
        for tid, t in self.timelines.items():
            for c in t.get("pass_commands", []) + t.get("scenario_commands", []):
                self.assertNotIn("shared", c["outcome"], (tid, c["summary"]))
        # A made-up pass where they do: his command at MET 101.5, the scenario's at 102, his counter up at 103.
        frames = [{"line": n + 2, "utc": "", "utc_s": 1000.0 + met, "met_s": met, "fields": {"CDH_MET": str(met)},
                   "values": {"CDH_CMD_ACC_CNT": 0 if met < 103 else 1, "CDH_CMD_REJ_CNT": 0}}
                  for n, met in enumerate(range(100, 111))]
        his = {"line": 2, "utc": "", "utc_s": 1101.5, "target": "T", "command": "CMD_MODE_SET",
               "parameters": {"target": "NOMINAL"}, "fields": {}}
        his.update(pass_records.place(frames, his["utc_s"]))
        his["outcome"] = pass_records.outcome(frames, his)
        made_up = {"name": "2026-01-01-P9", "date": "2026-01-01", "tag": "P9", "scenario": "P9", "problems": [],
                   "files": {}, "frames": frames, "commands": [his], "met_range": [100, 110]}
        plan = {"plan_id": "TEST-PLAN", "scenario_id": "P9", "aos_met_s": 90, "los_met_s": 200}
        scripted = {"file": "test.json", "sha256": "sha256:0", "problems": [], "passes": {"TEST-PLAN": {
            "pass": "P9", "plan_id": "TEST-PLAN", "scenario": "P9", "contact_window": {"aos_met_s": 90, "los_met_s": 200},
            "commands": [{"met_s": 102, "command": "CMD_PLD_SET_STATE", "parameters": {"state": "ON"},
                          "when": "in contact", "kept_in_odins_runs": False, "source": "test"}]}}}
        t = vc.pass_timeline(made_up, plan, huginn_dictionary.read_points(S.dictionary_path()), scripted)
        mine, theirs = t["pass_commands"][0], t["scenario_commands"][0]
        self.assertEqual((mine["outcome"]["kind"], mine["outcome"]["met_s"]), ("accepted", 103))
        self.assertEqual(mine["status"], "warn")
        self.assertEqual(mine["outcome"]["shared"], [{"met_s": 102, "who": "the scenario's", "command": "CMD_PLD_SET_STATE"}])
        self.assertIn("the scenario's CMD_PLD_SET_STATE at MET 102.00 was sent in the same span", mine["outcome"]["text"])
        # The scenario's own span, MET 102 to its change at 103, holds no command of his.
        self.assertNotIn("shared", theirs["outcome"])

    def test_odins_runs_dropped_exactly_the_in_contact_ones(self):
        dropped_in = {}
        for run in S.all_runs():
            truth = [json.loads(line) for line in S.record_lines(run, "truth")]
            start = json.loads(S.record_lines(run, "events")[0])["body"]
            plans = vc.run_summary(run)["plans"]
            span = (truth[0]["met_s"], truth[-1]["met_s"])
            dropped = [(r["met_s"], r["body"]["command"], r["body"]["contact_window"]) for r in truth
                       if r["type"] == "SCRIPTED_COMMAND_DROPPED"]
            # The file's pass flown under the run's plan; for a practice run's development plan, its scenario's.
            entries = [e for e in self.scripted["passes"].values() if e["plan_id"] in plans] or [
                e for e in self.scripted["passes"].values()
                if pass_records.scenario_base(e["pass"]) == pass_records.scenario_base(start["scenario_id"])]
            expected = [(c["met_s"], c["command"], e["contact_window"]) for e in entries
                        for c in e["commands"] if not c["kept_in_odins_runs"] and span[0] <= c["met_s"] <= span[1]]
            with self.subTest(run=run.name):
                self.assertEqual(dropped, expected)
            dropped_in[run.name] = [d[0] for d in dropped]
        # Every P1 run dropped the scenario's commands at MET 180 and 240, and every P4 run its reset at 1320.
        for name in S.SCORED_RUNS:
            want = {"PASS1": [180, 240], "PASS4": [1320]}.get(name.split("-")[1], [])
            self.assertEqual(dropped_in[name], want, name)
        self.assertEqual(dropped_in["dev-practice-p4"], [1320])


if __name__ == "__main__":
    unittest.main()
