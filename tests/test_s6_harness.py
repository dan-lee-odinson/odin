"""The harness in a run (CONTRACT.md §6, §8.1, §9.4, §12; Addendum A-1): the read-only tools logged as
TOOL_USE, POST /checkin making a check-in turn and recorded check-ins played from frozen transcripts
(U44), a run that fails its checks ending before it starts, where a run starts and ends and where its
folder goes (U46), and the scripted revocation with its signed restore. Turns are taken in-process, as
GET /turn/next takes them, or over HTTP."""

import json
import subprocess
import urllib.error
import urllib.request

import pytest

from contract.validate import check
from harness.server import Refused
from log.canonical import canonical_json, sha256_tag
from tests.harness_world import CHECK_IN, RUN, HarnessWorld, records, turns
from tests.repo_checks import REPO_ROOT


@pytest.fixture
def harness(tmp_path):
    return HarnessWorld(tmp_path)


@pytest.fixture
def started(harness):
    made = []

    def start(**options):
        run = harness.run(**options)
        made.append(run)
        assert run.start()
        return run

    yield start
    for run in made:
        run.stop()


def http(method, url, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def until(run, wanted, limit=40):
    """Turns taken until one satisfies wanted; all of them, oldest first."""
    taken = []
    for _ in range(limit):
        bundle = json.loads(run.next_turn())
        assert not bundle.get("run_complete"), "the run ended first"
        taken.append(bundle)
        if wanted(bundle):
            return taken
    raise AssertionError("no such turn")


# -- the tools -------------------------------------------------------------------------------------

def test_a_history_call_is_answered_and_logged_with_its_turn(started):
    run = started()
    [first] = turns(run, 1)
    reply = run.history(["EPS_LOAD_I", "EPS_BATT_SOC"], 60)
    assert reply["columns"] == ["met_s", "EPS_BATT_SOC", "EPS_LOAD_I"] and reply["rows"][-1][0] == first["met_s"]
    assert check("history_reply", reply) == []
    [use] = [r["body"] for r in records(run, "TOOL_USE")]
    assert use == {"run_id": RUN, "turn_id": 1, "tool": "history", "arguments": {"points": ["EPS_LOAD_I", "EPS_BATT_SOC"],
                   "window_s": 60}, "result_sha256": sha256_tag(canonical_json(reply))}
    assert check("tool_use", use) == []


def test_a_docs_lookup_is_answered_from_the_cache_and_logged(started, tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "commanding.md").write_text("# Commanding\nA hazardous command asks to confirm.\n", encoding="utf-8")
    run = started(docs_folder=tmp_path / "docs")
    turns(run, 1)
    reply = run.docs_lookup("hazardous command")
    assert [r["title"] for r in reply["results"]] == ["Commanding"] and check("docs_lookup_reply", reply) == []
    [use] = [r["body"] for r in records(run, "TOOL_USE")]
    assert (use["tool"], use["arguments"]) == ("docs_lookup", {"q": "hazardous command"})


def test_red_a_tool_used_before_any_turn_is_refused_and_nothing_logged(started):
    run = started()
    with pytest.raises(Refused):
        run.history(["EPS_LOAD_I"], 60)
    assert records(run, "TOOL_USE") == []


@pytest.mark.parametrize("query", ["points=EPS_LOAD_X&window_s=60", "points=EPS_LOAD_I&window_s=0",
                                   "points=EPS_LOAD_I&window_s=3601", "points=&window_s=60", "window_s=60",
                                   "points=EPS_LOAD_I&window_s=1.5"])
def test_red_a_history_call_whose_arguments_do_not_fit_gets_400(started, query):
    run = started()
    turns(run, 1)
    status, reply = http("GET", run.url("harness") + "/history?" + query)
    assert status == 400 and reply["problems"]
    assert records(run, "TOOL_USE") == []


def test_the_tools_answer_over_http(started):
    run = started()
    turns(run, 1)
    status, reply = http("GET", run.url("harness") + "/history?points=EPS_LOAD_I,PLD_STATE&window_s=3600")
    assert status == 200 and reply["columns"] == ["met_s", "EPS_LOAD_I", "PLD_STATE"]
    assert http("GET", run.url("harness") + "/docs/lookup?q=telemetry")[0] == 200


def test_red_an_endpoint_the_harness_does_not_serve_gets_404(started):
    run = started()
    assert http("GET", run.url("harness") + "/turn/previous")[0] == 404
    assert http("POST", run.url("harness") + "/turn/next", {})[0] == 404


# -- the check-in (A-1) ---------------------------------------------------------------------------------

def test_a_check_in_posted_is_logged_and_becomes_its_own_report_turn(started):
    run = started()
    turns(run, 2)
    status, reply = http("POST", run.url("harness") + "/checkin", CHECK_IN)
    [logged] = records(run, "CHECK_IN")
    assert (status, reply, logged["body"]) == (200, {"record_id": logged["record_id"]}, CHECK_IN)
    report = until(run, lambda b: b["turn_kind"] == "REPORT")[-1]
    assert (report["report_kind"], report["check_in_text"], [t["type"] for t in report["triggers"]]) == (
        "CHECK_IN", CHECK_IN["text"], ["CHECK_IN"])


@pytest.mark.parametrize("change", [{"source": "SPOKEN"}, {"text": 7}, {"audio_sha256": "abc"}, {"extra": 1}])
def test_red_a_check_in_that_is_not_one_gets_400_and_nothing_is_logged(started, change):
    run = started()
    status, reply = http("POST", run.url("harness") + "/checkin", {**CHECK_IN, **change})
    assert status == 400 and reply["problems"]
    assert records(run, "CHECK_IN") == []


# -- a run that cannot start --------------------------------------------------------------------------

def test_red_a_run_whose_plan_is_unsigned_ends_before_it_starts(harness):
    run = harness.run(plans=harness.world.plans([harness.plan()], signer=None))
    assert run.start() is False
    assert [r["type"] for r in records(run)] == ["RUN_START", "PLAN_CHAIN_VERIFIED", "RUN_END"]
    assert records(run, "RUN_END")[0]["body"] == {"reason": "PLAN_CHAIN_FAILED", "turns": 0, "detail": None}


def test_red_a_run_no_arming_act_covers_ends_not_armed(harness):
    plans = harness.world.plans([harness.plan()])
    run = harness.run(plans=plans, act=harness.world.act(plans, runs=["dev-s6-0002"]))
    assert run.start() is False
    assert records(run, "RUN_END")[0]["body"] == {"reason": "NOT_ARMED", "turns": 0, "detail": None}


def test_red_a_run_whose_plan_names_a_procedure_not_there_does_not_start(harness):
    plan = harness.plan(procedures_in_force=[{"id": "PROC-009", "version": "1", "sha256": "sha256:" + "0" * 64}])
    run = harness.run(plans=harness.world.plans([plan]))
    assert run.start() is False
    assert records(run, "RUN_END")[0]["body"] == {"reason": "ERROR", "turns": 0, "detail": None}


def test_red_a_recorded_check_in_that_is_not_a_frozen_transcript_is_refused_before_the_run(harness):
    for change in ({"source": "LIVE"}, {"audio_sha256": "abc"}, {"text": None}):
        with pytest.raises(ValueError):
            harness.run(check_ins=[(900, {**CHECK_IN, **change})])


# -- where a run starts and ends, and its folder (U46) ---------------------------------------------------

def test_a_run_starts_at_its_chains_first_valid_from_and_rolls_on_silently_to_aos(started, harness):
    run = started(plans=harness.world.plans([harness.plan(valid_from_met_s=0)]))
    [first] = turns(run, 1)
    assert (first["met_s"], [t["type"] for t in first["triggers"]]) == (800, ["AOS"])
    assert [r["met_s"] for r in records(run) if r["type"] in ("RUN_START", "PLAN_CHAIN_VERIFIED")] == [0, 0]
    assert (run.start_met_s, run.end_met_s) == (0, 1240)


def test_the_run_ends_at_its_chains_last_valid_until(started):
    run = started()
    taken = until(run, lambda b: any(t["type"] == "LOS" for t in b["triggers"]))
    assert taken[-1]["met_s"] == 1230
    while not json.loads(run.next_turn()).get("run_complete"):
        pass
    assert run.simulator.met_s == 1239 and records(run, "RUN_END")[0]["body"]["reason"] == "COMPLETE"


def test_a_run_that_stops_moves_from_runs_to_runs_dev(started, harness):
    run = started()
    turns(run, 1)
    assert run.folder == harness.tmp / "runs" / RUN
    run.stop()
    assert run.folder == harness.tmp / "runs" / "dev" / RUN and not (harness.tmp / "runs" / RUN).exists()
    assert records(run)[-1]["type"] == "RUN_END"


def test_a_scored_run_that_cannot_start_still_moves_to_runs_scored(harness):
    run = harness.run(mode="SCORED")   # scored mode refuses the development test key (§5.3)
    assert run.start() is False
    assert run.folder == harness.tmp / "runs" / "scored" / RUN
    assert records(run, "RUN_END")[0]["body"]["reason"] == "PLAN_CHAIN_FAILED"


@pytest.mark.parametrize("where", [("runs", RUN), ("runs", "dev", RUN)])
def test_red_a_run_folder_is_never_reused(harness, where):
    harness.tmp.joinpath(*where).mkdir(parents=True)
    with pytest.raises(FileExistsError):
        harness.run().start()


@pytest.mark.parametrize("path, ignored", [("runs/dev-s6-0001/events.jsonl", True),
                                           ("runs/PH2-PASS3-SPARK-R1/inputs/bundle", True),
                                           ("runs/dev/dev-s6-0001/events.jsonl", True),
                                           ("runs/scored/PH2-PASS3-SPARK-R1/events.jsonl", False),
                                           ("runs/scored/PH2-PASS3-SPARK-R1/truth.jsonl.gz", False)])
def test_git_ignores_everything_under_runs_but_runs_scored(path, ignored):
    result = subprocess.run(["git", "check-ignore", "--no-index", "-q", path], cwd=REPO_ROOT)
    assert result.returncode == (0 if ignored else 1)


# -- the scripted revocation and the restore (§9.4) ------------------------------------------------------

def test_revocation_at_its_scripted_moment_then_the_signed_restore(started, harness):
    restore = harness.world.restore_act(run_id=RUN, plan_id="TYR0-P3-PASS1-v1")
    run = started(revoke_at=850, restore=(870, restore))
    taken = until(run, lambda b: any(t["type"] == "RESTORE" for t in b["triggers"]))
    revoked = next(b for b in taken if any(t["type"] == "REVOKE" for t in b["triggers"]))
    hand_back = taken[taken.index(revoked) + 1]
    assert (revoked["turn_kind"], revoked["rung"], revoked["rung_reason"]) == ("ACT", "HUMAN_ONLY", "REVOKED")
    assert (hand_back["turn_kind"], hand_back["report_kind"]) == ("REPORT", "HAND_BACK")
    assert (taken[-1]["rung"], taken[-1]["rung_reason"]) == ("AI_AUTONOMOUS", None)
    assert [r["body"] for r in records(run, "REVOKE")] == [{"source": "SCRIPT"}]
    [restored] = records(run, "RESTORE")
    assert restored["met_s"] == 870 and restored["body"]["result"] == "ACCEPTED"
