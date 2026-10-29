"""The harness's parts, each on its own: the watcher's triggers (CONTRACT.md §6.1), the frames the seat
received as the observation and history read them (§6.4, §16.1 U3), the bundle's parts taken from the
event log and the plan chain (§6.2, §16.1 U6), and the docs lookup (§16.5)."""

import pytest
import yaml

from contract.validate import check
from gateway.plans import Chain, Plan
from harness.bundle import from_the_log, next_plan, procedure_points
from harness.docs import CACHE, lookup
from harness.telemetry import HUGINN, FrameStore, InstView, ground_staleness
from harness.watch import Watcher
from tests.baldur_world import NOMINAL_POINTS
from tests.harness_world import DOCS
from tests.repo_checks import REPO_ROOT


def frame(met_s, **points):
    return {**NOMINAL_POINTS, "CDH_MET": met_s, "CDH_FRAME_CNT": met_s, **points}


# -- the watcher ---------------------------------------------------------------------------------------

def types(found):
    return [(t["type"], t["detail"]) for t in found]


def test_contact_and_plan_start_at_the_ticks_they_happen():
    watcher = Watcher([(800, 1230)])
    assert types(watcher.tick(799, plan_id="P1")) == [("PLAN_START", {"plan_id": "P1"})]
    assert types(watcher.tick(800, plan_id="P1")) == [("AOS", {})]
    assert watcher.tick(1229, plan_id="P1") == []
    assert types(watcher.tick(1230, plan_id="P2")) == [("LOS", {}), ("PLAN_START", {"plan_id": "P2"})]


def test_a_run_that_starts_inside_its_window_opens_with_aos():
    assert types(Watcher([(800, 1230)]).tick(800, plan_id=None)) == [("AOS", {})]


def test_each_limit_change_and_mode_change_between_frames():
    watcher = Watcher([])
    assert watcher.tick(1, plan_id=None, frame=frame(1)) == []   # the first frame has nothing to change from
    found = watcher.tick(2, plan_id=None, frame=frame(2, EPS_LOAD_I=1.8, EPS_MODE="SAFE"))
    assert types(found) == [("LIMIT_CHANGE", {"point": "EPS_LOAD_I", "from": "GREEN", "to": "YELLOW_HIGH"}),
                            ("LIMIT_CHANGE", {"point": "EPS_MODE", "from": "GREEN", "to": "RED"}),
                            ("MODE_CHANGE", {"from": "NOMINAL", "to": "SAFE"})]
    assert watcher.tick(3, plan_id=None) == []   # no frame, no change


def test_red_the_same_limit_state_is_no_change():
    watcher = Watcher([])
    watcher.tick(1, plan_id=None, frame=frame(1, EPS_LOAD_I=1.6))
    assert watcher.tick(2, plan_id=None, frame=frame(2, EPS_LOAD_I=1.9)) == []   # yellow both times


def test_the_ground_monitors_changes_are_triggers():
    watcher = Watcher([])
    watcher.tick(1, plan_id=None, staleness="GREEN")
    assert types(watcher.tick(11, plan_id=None, staleness="YELLOW")) == [("STALENESS_CHANGE", {"from": "GREEN", "to": "YELLOW"})]
    assert watcher.tick(12, plan_id=None, staleness=None) == []   # the onboard seat has no monitor


# -- the frames received -------------------------------------------------------------------------------

@pytest.mark.parametrize("age, state", [(9, "GREEN"), (10, "YELLOW"), (29, "YELLOW"), (30, "RED")])
def test_the_ground_monitor_turns_yellow_at_10_s_and_red_at_30_s(age, state):
    assert ground_staleness(100, 100 + age) == state


def test_an_outage_is_an_observation_with_nothing_filled_in():
    store = FrameStore("ONBOARD")
    assert store.observation(5) == {"source": "ONBOARD", "frame_met_s": None, "received_utc": None, "age_s": None,
                                    "staleness_state": None, "ground_link": None, "points": None}
    store.receive(frame(5), "2026-10-28T14:00:05.000Z", 5)
    seen = store.observation(12)
    assert (seen["frame_met_s"], seen["age_s"], seen["points"]["EPS_LOAD_I"]) == (
        5, 7, {"value": 0.5, "units": "A", "limit_state": "GREEN"})
    assert check("observation", seen) == []


def test_the_ground_seat_sees_the_ground_link_as_cosmos_reports_it_and_the_onboard_seat_never():
    # The Director's scoring ruling of 28 October 2026, selection 1: what he read on CmdTlmServer for PROC-003-S02.
    link = {"state": "CONNECTED", "received_count": 9576}
    ground = FrameStore("COSMOS")
    ground.receive(frame(1), "2026-10-28T14:00:01.000Z", 1)
    seen = ground.observation(2, ground_link=link)
    assert seen["ground_link"] == link and check("observation", seen) == []
    with pytest.raises(ValueError):
        ground.observation(2)
    with pytest.raises(ValueError):
        FrameStore("ONBOARD").observation(2, ground_link=link)


def test_the_ground_seat_reads_staleness_from_new_frame_counts():
    store = FrameStore("COSMOS")
    store.receive(frame(1), "2026-10-28T14:00:01.000Z", 1)
    store.receive(frame(2, CDH_FRAME_CNT=1), "2026-10-28T14:00:02.000Z", 2)   # a halted counter
    assert store.staleness(11) == "YELLOW"


def test_history_is_the_last_window_one_row_per_frame_in_dictionary_order():
    store = FrameStore("ONBOARD")
    for met in range(1, 401):
        store.receive(frame(met), "2026-10-28T14:00:00.000Z", met)
    table = store.history(["PLD_STATE", "EPS_BATT_SOC"], 400, 300)
    assert table["columns"] == ["met_s", "EPS_BATT_SOC", "PLD_STATE"]
    assert (len(table["rows"]), table["rows"][0], table["rows"][-1]) == (300, [101, 80.0, "ON"], [400, 80.0, "ON"])


def test_the_history_holds_the_points_its_procedures_name_whole():
    text = [{"text": "Read EPS_LOAD_I and EPS_BATT_SOC; then PLD_STATE. Not EPS_BATT_SOCX."}]
    assert procedure_points(text, HUGINN.names) == ["EPS_BATT_SOC", "EPS_LOAD_I", "PLD_STATE"]
    assert procedure_points(None, HUGINN.names) == []


def test_the_history_holds_the_items_of_the_dictionary_in_force_its_procedures_name():
    # The Director's ruling of 29 October 2026: phase 1 by the same rule as HUGINN's, against INST's items.
    proc_001 = [{"text": (REPO_ROOT / "plans" / "PROC-001_PH1.md").read_bytes().decode("utf-8")}]
    inst = InstView(yaml.safe_load((REPO_ROOT / "config" / "dictionaries" / "INST.yaml").read_text(encoding="utf-8")))
    assert procedure_points(proc_001, inst.names) == ["CMD_ACPT_CNT", "COLLECTS"]
    assert procedure_points(proc_001, HUGINN.names) == []


# -- the bundle's parts from the log and the chain ---------------------------------------------------------

def record(record_id, type_, body):
    return {"record_id": record_id, "type": type_, "body": body}


def test_feedback_is_baldur0s_records_since_odins_latest_request():
    log = [record(1, "REQUEST", {"request_id": "a"}), record(2, "DECISION", {"request_id": "a"}),
           record(3, "REQUEST", {"request_id": "b"}), record(4, "DECISION", {"request_id": "b"}),
           record(5, "DISPATCH", {}), record(6, "DECISION_VOIDED", {"request_id": "a"}), record(7, "OUTCOME", {})]
    feedback, requests = from_the_log(log)
    assert feedback == [{"type": "DECISION", "record": {"request_id": "b"}},
                        {"type": "DECISION_VOIDED", "record": {"request_id": "a"}}]
    assert requests == [{"request_id": "a"}, {"request_id": "b"}]
    assert from_the_log([record(1, "RUN_START", {})]) == ([], [])


def plan(plan_id, start, end):
    return Plan(plan_id, "sha256:" + "0" * 64, start, end, {"plan_id": plan_id})


def test_the_next_plan_is_the_one_after_the_plan_in_force():
    chain = Chain((plan("A", 0, 100), plan("B", 100, 200)))
    assert next_plan(chain, chain.plan_at(50), 50).plan_id == "B"
    assert next_plan(chain, chain.plan_at(150), 150) is None
    assert next_plan(Chain((plan("C", 100, 200),)), None, 50).plan_id == "C"   # before the chain starts


# -- the docs lookup -----------------------------------------------------------------------------------------

def test_the_lookup_gives_at_most_three_pages_best_first_with_text_cut_at_4000(tmp_path):
    for name, text in {"a.md": "# Alpha\ncommand", "b.md": "# Beta\ncommand command", "c.html": "<title>Gamma</title>" +
                       "command " * 1000, "d.md": "# Delta\ncommand", "e.md": "# Epsilon\nnothing here"}.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    reply = lookup("Command", tmp_path)
    assert [r["title"] for r in reply["results"]] == ["Gamma", "Beta", "Alpha"]
    assert (len(reply["results"][0]["text"]), reply["results"][0]["truncated"], reply["results"][1]["truncated"]) == (
        4000, True, False)
    assert check("docs_lookup_reply", reply) == []


@pytest.mark.parametrize("query, titles", [
    ("hazardous command", ["Sending commands (made up for the tests)"]),
    ("limit", ["Limits (made up for the tests)"]),
    ("stale telemetry", ["Telemetry viewer (made up for the tests)", "Limits (made up for the tests)"])])
def test_the_lookup_over_the_fixture_cache_until_m4s_cache_lands(query, titles):
    # The real cache is cache/cosmos-docs-7.2.1/, which Muse Code's M4 fetch script writes (U42).
    reply = lookup(query, DOCS)
    assert [r["title"] for r in reply["results"]] == titles
    assert all(r["path"].startswith(("commanding", "limits", "telemetry-viewer")) for r in reply["results"])
    assert check("docs_lookup_reply", reply) == []


def test_the_lookup_reads_m4s_cache_and_nothing_else():
    assert CACHE == REPO_ROOT / "cache" / "cosmos-docs-7.2.1"


def test_red_no_cache_or_no_match_is_no_result(tmp_path):
    assert lookup("command", tmp_path / "absent") == {"query": "command", "results": []}
    assert lookup("", tmp_path) == {"query": "", "results": []}
