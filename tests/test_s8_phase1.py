"""S8's phase-1 checks (the Director's scoring ruling of 28 October 2026, §2, Phase 1): each check-in's answer
checked against COSMOS at the time ODIN gives, from the run's event log and the INST packets its truth file kept,
never from ODIN's prose; the written claims laid beside COSMOS's record on one sheet for the Director's true or
false, read back apart from what S8 scores (U61)."""

import json

import pytest

from eval import phase1, score
from eval.phase1 import check_phase_1, limits_line, marks, sheet, sheet_text
from eval.results import score_phase_1
from eval.runlog import read_jsonl
from tests.s8_world import record
from tests.test_s7_shakedown import flown  # noqa: F401  (the phase-1 run these checks score)


def scored(run):
    return check_phase_1(read_jsonl(run.folder / "events.jsonl"), read_jsonl(run.folder / "truth.jsonl"))


def test_a_flown_shakedown_passes_the_collect_and_the_health_status_checks(flown):  # noqa: F811
    run, _, _ = flown
    found = scored(run)
    collect = found["checks"]["collect"]
    assert collect["accepted"] and collect["count_rose_by_one"] and collect["success"]
    assert [e["value"] for e in collect["evidence"]] == [0, 1] and all(e["match"] for e in collect["evidence"])
    assert found["checks"]["health_status"]["success"]
    assert found["checks"]["console_notes"]["scored"] is False


def utc(met_s):
    return f"2026-10-29T14:00:{met_s:02d}.500Z"


def packet(met_s, **values):
    items = {"COLLECTS": 2, "TEMP1": 10.0, "CMD_ACPT_CNT": 2, **values}
    states = {"TEMP1": "RED_HIGH" if items["TEMP1"] > 80 else "BLUE"}
    return {"type": "COSMOS_PACKET", "met_s": met_s, "utc": utc(met_s),
            "body": {"items": {k: {"value": v, "limits_state": states.get(k)} for k, v in items.items()}}}


def answer(met_s, *evidence):
    return record("REPORT", met_s, report_kind="CHECK_IN", turn_id=1, actions=[], timeline=[], answer="As seen.",
                  condition={"summary": "", "evidence": [{"point": p, "value": v, "met_s": m} for p, v, m in evidence]})


TRUTH = [packet(10, COLLECTS=2), packet(12, COLLECTS=3, CMD_ACPT_CNT=3), packet(30, COLLECTS=3, TEMP1=85.0),
         packet(40, COLLECTS=3)]
CHECK_INS = [record("CHECK_IN", 20, text="one"), record("CHECK_IN", 31, text="two"), record("CHECK_IN", 41, text="three")]
COLLECT = [record("REQUEST", 11, request_id="a", command="COLLECT", parameters={"type": "NORMAL", "duration": 1.0,
                                                                                 "opcode": 171, "temp": 0.0}),
           record("DISPATCH", 11, request_id="a", command="COLLECT", utc="2026-10-29T14:00:11.200Z"),
           record("OUTCOME", 12, request_id="a", outcome="ACCEPTED", frame_met_s=12)]


def test_red_a_collect_count_it_gives_wrongly_fails_the_collect_check():
    right = check_phase_1(CHECK_INS + COLLECT + [answer(21, ("COLLECTS", 2, 10), ("COLLECTS", 3, 12))], TRUTH)
    wrong = check_phase_1(CHECK_INS + COLLECT + [answer(21, ("COLLECTS", 2, 10), ("COLLECTS", 4, 12))], TRUTH)
    assert right["checks"]["collect"]["success"] and not wrong["checks"]["collect"]["success"]


def test_red_a_collect_never_accepted_fails_the_collect_check():
    found = check_phase_1(CHECK_INS + COLLECT[:2] + [answer(21, ("COLLECTS", 2, 10), ("COLLECTS", 2, 12))], TRUTH)
    assert not found["checks"]["collect"]["accepted"] and not found["checks"]["collect"]["success"]


def test_red_a_value_cosmos_did_not_show_at_its_time_fails_the_health_status_check():
    records = CHECK_INS + [answer(21), answer(32, ("TEMP1", 85.0, 30), ("COLLECTS", 3, 30))]
    assert check_phase_1(records, TRUTH)["checks"]["health_status"]["success"]
    records = CHECK_INS + [answer(21), answer(32, ("TEMP1", 85.0, 40), ("COLLECTS", 3, 30))]
    assert not check_phase_1(records, TRUTH)["checks"]["health_status"]["success"]


def test_red_an_item_named_while_in_limits_fails_the_out_of_limits_check():
    named = lambda met_s: CHECK_INS + [answer(21), answer(32), answer(42, ("TEMP1", 85.0 if met_s == 30 else 10.0, met_s))]
    hit = check_phase_1(named(30), TRUTH)["checks"]["out_of_limits"]
    assert hit["success"] and hit["out_of_limits"][0]["limits_state"] == "RED_HIGH"
    assert not check_phase_1(named(40), TRUTH)["checks"]["out_of_limits"]["success"]


RUN_START = record("RUN_START", 0, run_id="PH1-TEST", model_config="stand_in", phase=1)
ANSWERED = ([RUN_START] + CHECK_INS + [record("CHECK_IN", 50, text="four")] + COLLECT
            + [answer(21, ("COLLECTS", 2, 10), ("COLLECTS", 3, 12)), answer(32, ("TEMP1", 85.0, 30)),
               answer(42, ("TEMP1", 85.0, 30)), answer(51)])


def test_the_sheet_lays_each_answer_beside_cosmos_with_a_place_for_each_written_claim():
    document = sheet(ANSWERED, TRUTH)
    assert [[c["claim"] for c in e["claims"]] for e in document["check_ins"]] == [
        [], ["units", "limit_states", "tracked_items"], ["limits_line", "limit_crossed"], []]
    assert all(c["mark"] is None for e in document["check_ins"] for c in e["claims"])
    collect, health, limits, notes = (e["cosmos"] for e in document["check_ins"])
    assert collect["odins_collects"] == [{"dispatched_met_s": 11, "outcome": "ACCEPTED",
                                          "before": {"COLLECTS": {"value": 2, "units": None, "limits_state": None},
                                                     "CMD_ACPT_CNT": {"value": 2, "units": None, "limits_state": None}},
                                          "after": {"COLLECTS": {"value": 3, "units": None, "limits_state": None},
                                                    "CMD_ACPT_CNT": {"value": 3, "units": None, "limits_state": None}}}]
    assert health["at_check_in"]["TEMP1"] == {"value": 85.0, "units": "C", "limits_state": "RED_HIGH"}
    assert health["items_its_evidence_names_over_the_window"] == {
        "TEMP1": [[10, 10.0, "BLUE"], [12, 10.0, "BLUE"], [30, 85.0, "RED_HIGH"]]}
    assert limits["items_its_evidence_names"]["TEMP1"] == {
        "limits_line": "LIMITS DEFAULT 1 ENABLED -80.0 -70.0 60.0 80.0 -20.0 20.0", "limits_state": "RED_HIGH",
        "crossed": "red high 80.0"}
    assert limits["out_of_limits_at_check_in"] == {} and notes is None


def marked(text, *values):
    """A sheet with its first marks set, in order, as the Director sets them."""
    for value in values:
        assert "\n    mark: null" in text
        text = text.replace("\n    mark: null", f"\n    mark: {value}", 1)
    return text


def test_a_flown_shakedowns_marks_come_back_as_the_directors_apart_from_what_s8_scores(flown, tmp_path):  # noqa: F811
    run, _, _ = flown
    records, truth = read_jsonl(run.folder / "events.jsonl"), read_jsonl(run.folder / "truth.jsonl")
    path = tmp_path / "sheet.yaml"
    path.write_text(marked(sheet_text(sheet(records, truth)), "true", "false"), encoding="utf-8")
    found = score_phase_1(run.folder, sheet=path)
    assert {key: claim["mark"] for key, claim in found["checked_by_the_director"].items()} == {
        "units": True, "limit_states": False, "tracked_items": None, "limits_line": None, "limit_crossed": None}
    assert found["scored_by_s8"] == check_phase_1(records, truth)["checks"]
    unmarked = score_phase_1(run.folder, sheet=tmp_path / "none.yaml")
    assert unmarked["scored_by_s8"] == found["scored_by_s8"] and unmarked["sheet"] is None
    assert all(claim["mark"] is None for claim in unmarked["checked_by_the_director"].values())


def test_s8_lays_out_a_phase_1_runs_sheet_once_and_scores_the_run_as_phase_1(flown, tmp_path, monkeypatch):  # noqa: F811
    run, _, _ = flown
    monkeypatch.setattr(phase1, "SHEETS", tmp_path / "marks")
    assert score.main(["--sheet", str(run.folder)]) == 0
    path = tmp_path / "marks" / f"{run.run_id}.yaml"
    assert path.read_bytes().startswith(b"# Phase 1's marking sheet for run ") and b"\r" not in path.read_bytes()
    with pytest.raises(SystemExit, match="perhaps with the Director's marks"):
        score.main(["--sheet", str(run.folder)])
    found = score.score(run.folder)
    assert (found["phase"], found["sheet"], found["build_defect"]) == (1, path.as_posix(), None)


def test_red_a_phase_1_run_that_ended_with_error_is_a_build_defect_not_scored(tmp_path):
    # U59 holds in phase 1 too: COSMOS refusing a command BALDUR-0 allowed is the build's defect, not ODIN's.
    lines = [RUN_START, record("RUN_END", 5, reason="ERROR", detail="COSMOS refused INST COLLECT")]
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    (tmp_path / "truth.jsonl").write_text("", encoding="utf-8")
    found = score_phase_1(tmp_path)
    assert found["build_defect"] == "COSMOS refused INST COLLECT" and "scored_by_s8" not in found


def test_red_a_mark_that_is_not_true_or_false_is_refused():
    text = sheet_text(sheet(ANSWERED, TRUTH))
    assert marks(marked(text, "true"), ANSWERED, TRUTH)["units"] is True
    with pytest.raises(ValueError, match="not true or false"):
        marks(marked(text, "maybe"), ANSWERED, TRUTH)


def test_red_a_sheet_changed_beyond_its_marks_is_refused():
    text = marked(sheet_text(sheet(ANSWERED, TRUTH)), "true")
    assert marks(text, ANSWERED, TRUTH)["units"] is True
    with pytest.raises(ValueError, match="something other than a mark was changed"):
        marks(text.replace("units: C", "units: F", 1), ANSWERED, TRUTH)


def test_the_limits_line_is_the_demos_definition():
    assert limits_line("TEMP3") == "LIMITS DEFAULT 1 ENABLED -25.0 -10.0 50.0 55.0"
    assert limits_line("COLLECTS") is None
