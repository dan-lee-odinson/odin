"""S8's phase-1 checks (the Director's scoring ruling of 28 October 2026, §2, Phase 1): each check-in's answer
checked against COSMOS at the time ODIN gives, from the run's event log and the INST packets its truth file kept,
never from ODIN's prose; what the ruling asks of the prose set beside each answer for the Director."""

from eval.phase1 import check_phase_1, limits_line
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
    assert len(found["for_the_director"]) == 3
    assert found["for_the_director"][0]["limits_lines"]["TEMP1"] == "LIMITS DEFAULT 1 ENABLED -80.0 -70.0 60.0 80.0 -20.0 20.0"


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


def test_the_limits_line_is_the_demos_definition():
    assert limits_line("TEMP3") == "LIMITS DEFAULT 1 ENABLED -25.0 -10.0 50.0 55.0"
    assert limits_line("COLLECTS") is None
