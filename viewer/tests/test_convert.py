"""The converter's checks: hashing, the log's chain, limit states, the truth
mapping, the timeline each practice run becomes, what the ground-seat run's
bundles recorded of the ground link and staleness, and that the same inputs give
the same files."""

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _support as S
import huginn_dictionary as hd
import verda_convert as vc

V1_POINTS = ("EPS_BATT_V", "EPS_BATT_SOC", "EPS_LOAD_I", "EPS_SA1_I", "EPS_SA2_I",
             "PLD_STATE", "PLD_RATE", "EPS_MODE")


def float32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


class CanonicalJson(unittest.TestCase):
    def test_reproduces_every_contract_vector(self):
        vectors = json.loads((S.schemas_dir() / "canonical_vectors.json").read_text(encoding="utf-8"))["vectors"]
        self.assertGreater(len(vectors), 10)
        for vector in vectors:
            with self.subTest(vector["name"]):
                data = vc.canonical_json(vector["value"])
                self.assertEqual(data.hex(), vector["canonical_hex"])
                self.assertEqual(vc.sha256_tag(data), vector["sha256"])


class HashChain(unittest.TestCase):
    def test_every_run_verifies(self):
        for run in S.all_runs():
            for name in ("events", "truth"):
                with self.subTest(run=run.name, file=name):
                    records, check = vc.read_chain(run / (name + ".jsonl"), run / (name + ".head"))
                    self.assertGreater(len(records), 50)
                    self.assertEqual(check["problems"], [])
                    self.assertEqual(check["chain"], "VERIFIED")
                    self.assertEqual(check["head"], "MATCHES")

    def test_a_changed_record_breaks_the_chain(self):
        run = S.practice_runs()[0]
        lines = (run / "events.jsonl").read_bytes().split(b"\n")
        target = next(i for i, line in enumerate(lines) if b'"type":"DISPATCH"' in line)
        changed = lines[target].replace(b'"route":"UPLINK"', b'"route":"COSMOS"')
        self.assertNotEqual(changed, lines[target], "the planted change did not apply")
        lines[target] = changed  # still canonical JSON; only the chain can tell
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "events.jsonl").write_bytes(b"\n".join(lines))
            shutil.copy(run / "events.head", Path(tmp, "events.head"))
            records, check = vc.read_chain(Path(tmp, "events.jsonl"), Path(tmp, "events.head"))
        self.assertEqual(check["chain"], "BROKEN")
        self.assertTrue(any("prev_hash" in p for p in check["problems"]), check["problems"])


class Limits(unittest.TestCase):
    def test_dictionary_has_the_sixteen_points(self):
        points = hd.read_points(S.dictionary_path())
        self.assertEqual(len(points), 16)
        for name in ("EPS_BATT_V", "EPS_BATT_I", "EPS_BATT_SOC", "EPS_BUS_V", "EPS_LOAD_I"):
            self.assertEqual(points[name]["limits"]["kind"], "thresholds", name)
        self.assertEqual(points["EPS_MODE"]["limits"]["annunciates"], ["SAFE"])
        self.assertEqual(hd.staleness_limits(points), {"yellow_s": 10, "red_s": 30})

    def test_limit_states_match_every_observation(self):
        """VERDA's limit states agree with every limit state the bundles recorded."""
        points = hd.read_points(S.dictionary_path())
        compared = 0
        for run in S.all_runs():
            for trigger, bundle in S.bundles(run):
                for name, point in (bundle["observation"]["points"] or {}).items():
                    with self.subTest(run=run.name, turn=bundle["turn_id"], point=name):
                        self.assertEqual(hd.limit_state(points[name], point["value"]), point["limit_state"])
                        compared += 1
        self.assertGreater(compared, 400)


class TruthMapping(unittest.TestCase):
    def test_truth_matches_every_observation(self):
        """Each observed frame equals the simulator's true state at that frame's MET."""
        compared = 0
        for run in S.all_runs():
            truth = {}
            with open(run / "truth.jsonl", encoding="utf-8") as handle:
                for line in handle:
                    record = json.loads(line)
                    if record["type"] == "TRUE_STATE":
                        truth[record["met_s"]] = record["body"]
            for trigger, bundle in S.bundles(run):
                observation = bundle["observation"]
                body = truth[observation["frame_met_s"]]
                for name, mapping in vc.TRUTH_POINTS.items():
                    expected = vc._truth_value(body, mapping)
                    seen = observation["points"][name]["value"]
                    with self.subTest(run=run.name, turn=bundle["turn_id"], point=name):
                        if isinstance(expected, float):
                            self.assertEqual(float32(expected), seen)
                        else:
                            self.assertEqual(expected, seen)
                        compared += 1
        self.assertGreater(compared, 400)


class Timelines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.timelines = {}
        for run in S.practice_runs():
            path, _ = vc.convert(run, cls.out, S.dictionary_path())
            summary, timeline = vc.read_timeline_script(path)
            cls.timelines[run.name] = timeline

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def request(self, run, command):
        found = [r for r in self.timelines[run]["requests"] if r["command"] == command]
        self.assertEqual(len(found), 1, self.timelines[run]["requests"])
        return found[0]

    def test_each_practice_run_has_a_timeline_file(self):
        names = sorted(p.name for p in self.out.glob("*.js"))
        self.assertEqual(names, sorted([n + ".js" for n in S.PRACTICE_RUNS] + ["index.js"]))
        index = (self.out / "index.js").read_text(encoding="utf-8")
        for name in S.PRACTICE_RUNS:
            self.assertIn('"id": "%s"' % name, index)
        for name, timeline in self.timelines.items():
            self.assertEqual(timeline["format"], "verda-timeline")
            self.assertEqual(timeline["id"], name)
            self.assertEqual([c["chain"] for c in timeline["integrity"]], ["VERIFIED"] * 3)

    def test_p3_payload_shed_is_one_allowed_accepted_chain(self):
        r = self.request("dev-practice-p3", "CMD_PLD_SET_STATE")
        self.assertEqual(r["parameters"], {"state": "OFF"})
        self.assertEqual((r["turn_id"], r["met_s"], r["decision"], r["decision_met_s"]), (4, 900, "ALLOW", 900))
        self.assertEqual((r["dispatch_met_s"], r["route"], r["outcome"], r["outcome_met_s"]), (901, "UPLINK", "ACCEPTED", 902))
        self.assertEqual(r["outcome_point"], {"mnemonic": "PLD_STATE", "value": "OFF"})
        self.assertIsNone(r["refusal"])

    def test_p4_reset_and_the_frame_gap(self):
        tl = self.timelines["dev-practice-p4"]
        r = self.request("dev-practice-p4", "CMD_SYS_RESET")
        self.assertEqual((r["met_s"], r["decision"], r["class"], r["outcome"]), (1220, "ALLOW", "C3", "ACCEPTED"))
        soc = [s[0] for s in tl["series"]["odin:EPS_BATT_SOC"]["samples"]]
        self.assertIn(1199, soc)
        self.assertIn(1222, soc)
        self.assertFalse([m for m in soc if 1199 < m < 1222], "ODIN had no frame between 1199 and 1222")
        age = {s[0]: s for s in tl["series"]["odin:FRAME_AGE"]["samples"]}
        self.assertEqual(age[1220][1:3], [21, "YELLOW"])
        self.assertEqual(age[1222][1:3], [0, "GREEN"])
        onsets = [e for e in tl["events"] if e["lane"] == "truth" and "hk_generation_halt" in e["label"]]
        self.assertEqual([e["met_s"] for e in onsets], [1200])

    def test_p3_process_has_two_malformed_turns_and_no_request(self):
        tl = self.timelines["dev-practice-p3-process"]
        self.assertEqual(tl["requests"], [])
        bad = sorted(int(k) for k, t in tl["turns"].items() if (t["answer"] or {}).get("kind") == "malformed")
        self.assertEqual(bad, [2, 8])
        self.assertEqual({tl["turns"][str(k)]["answer"]["reason"] for k in bad}, {"WRONG_FORM_FOR_TURN"})

    def test_check_ins_reports_and_contact(self):
        for name, met in (("dev-practice-p3", 1140), ("dev-practice-p4", 1440)):
            tl = self.timelines[name]
            checkins = [e for e in tl["events"] if e["lane"] == "director"]
            self.assertEqual([e["met_s"] for e in checkins], [met], name)
            self.assertIn("ODIN this is Flight", checkins[0]["text"])
            reports = sorted(e["report_kind"] for e in tl["events"] if e["lane"] == "reports")
            self.assertEqual(reports, ["CHECK_IN", "PASS_START"], name)
            contact = [s for s in tl["spans"] if s["lane"] == "contact" and s.get("row") == 0]
            self.assertEqual(len(contact), 1, name)

    def test_v1_points_from_both_sources(self):
        for name, tl in self.timelines.items():
            lane_points = {p for lane in tl["lanes"] for p in lane.get("points", [])}
            for point in V1_POINTS:
                with self.subTest(run=name, point=point):
                    self.assertIn(point, lane_points)
                    self.assertGreater(len(tl["series"]["odin:" + point]["samples"]), 5)
                    self.assertGreater(len(tl["series"]["truth:" + point]["samples"]), 400)

    def test_every_record_is_drawn(self):
        for name, tl in self.timelines.items():
            with self.subTest(run=name):
                self.assertEqual(tl["warnings"], [])
                refs = set()
                for item in tl["events"] + tl["spans"]:
                    refs.update(item["refs"])
                for turn in tl["turns"].values():
                    refs.update(turn["refs"])
                for request in tl["requests"]:
                    refs.update(request["refs"])
                missing = [k for k in tl["records"] if "log:" + k not in refs]
                self.assertEqual(missing, [])


class Repeatable(unittest.TestCase):
    def test_the_same_inputs_give_the_same_files_whatever_the_hash_seed(self):
        """Python orders a set by its hash seed, which changes from one process to the next."""
        made = []
        with tempfile.TemporaryDirectory() as tmp:
            for seed in ("1", "2", "3", "4"):
                out = Path(tmp, seed)
                done = subprocess.run(
                    [sys.executable, str(S.ROOT / "convert" / "verda_convert.py"), *map(str, S.all_runs()),
                     "--out", str(out), "--dictionary", str(S.dictionary_path()), "--passes", str(S.passes_dir()),
                     "--plans", str(S.plans_dir()), "--scripted", str(S.scripted_path())],
                    env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1"),
                    capture_output=True, text=True, timeout=300)
                self.assertEqual(done.returncode, 0, done.stderr)
                made.append({p.name: p.read_bytes() for p in sorted(out.glob("*.js"))})
        self.assertEqual(len(made[0]), len(S.ALL_RUNS) + 3 + 1)  # each run, the three passes alone, the index
        for seed, files in zip(("2", "3", "4"), made[1:]):
            with self.subTest(seed=seed):
                self.assertEqual(sorted(files), sorted(made[0]))
                self.assertEqual([n for n in files if files[n] != made[0][n]], [])


class GroundSeat(unittest.TestCase):
    """S5's live check, flown in the ground seat: its bundles carry the ground
    station's staleness state and ground link, which an onboard seat's never do."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path, _ = vc.convert(S.ground_seat_run(), Path(cls.tmp.name), S.dictionary_path())
        cls.tl = vc.read_timeline_script(path)[1]
        cls.observed = [(trigger["met_s"], bundle["observation"]) for trigger, bundle in S.bundles(S.ground_seat_run())]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_its_bundles_staleness_and_ground_link_are_drawn(self):
        tl = self.tl
        self.assertEqual((tl["id"], tl["header"]["seat"], tl["header"]["scenario_id"]), ("dev-s6-0001", "GROUND", "P3"))
        lane = [l for l in tl["lanes"] if l["id"] == "staleness"][0]
        self.assertTrue(lane["strip"])
        self.assertEqual(lane["height"], vc.AGE_H + vc.STRIP_H)
        marks = [e for e in tl["events"] if e["lane"] == "staleness"]
        states = [(e["met_s"], e["label"]) for e in marks if (e.get("row") or 0) == 0]
        links = [(e["met_s"], e["label"]) for e in marks if e.get("row") == 1]
        # What each turn's bundle recorded, read here from the bundles themselves.
        self.assertEqual(states, [(m, "Ground staleness %s" % o["staleness_state"]) for m, o in self.observed])
        self.assertEqual(links, [(m, "Ground link %s, %d packets" % (o["ground_link"]["state"], o["ground_link"]["received_count"]))
                                 for m, o in self.observed])
        self.assertEqual([label.split()[-1] for _, label in states], ["GREEN"] * 9 + ["YELLOW"])
        self.assertEqual(states[-1][0], 909)
        self.assertEqual([int(label.split()[-2]) for _, label in links], [100] * 5 + [101, 110, 170, 200, 200])
        contact = [(s["start"], s["end"]) for s in tl["spans"] if s["lane"] == "contact" and s.get("row") == 0]
        self.assertEqual(contact, [(800, 900)])

    def test_its_derived_frame_age_agrees_with_the_age_it_recorded(self):
        derived = {q[0]: q for q in self.tl["series"]["odin:FRAME_AGE"]["samples"]}
        recorded = self.tl["series"]["odin:AGE_S"]["samples"]
        self.assertEqual(len(recorded), len(set(m for m, _ in self.observed)))
        for met, age, state, _ in recorded:
            with self.subTest(met=met):
                self.assertEqual(derived[met][1:3], [age, state])
        self.assertEqual(derived[900][1:3], [1, "GREEN"])
        self.assertEqual(derived[909][1:3], [10, "YELLOW"])


if __name__ == "__main__":
    unittest.main()
