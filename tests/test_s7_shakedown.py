"""Phase 1, the shakedown on COSMOS's demo spacecraft (CONTRACT.md §1, §10.1; the Director's rulings of 27
October 2026, §1, and on U58, 28 October 2026): a phase-1 run flies the ground seat in real time with no HUGINN
to step, reads INST HEALTH_STATUS from COSMOS with COSMOS's own limit states and the demo's own interface,
sends what BALDUR-0 allows under INST's dictionary through COSMOS, reads each outcome from INST's accept
counter, keeps every packet it read in its truth file, and plays the four check-ins as text at fixed points.

These run against tests/fake_inst.py. Muse Code's loop is ODIN, its own answer check reading the dictionary in
force through the registry (MC-M9-01); tests/live_s7_pass.py runs the same against ODIN's COSMOS."""

import json
import secrets
import shutil
import threading
import time

import pytest

from connector.api import inst
from eval.measures import measures
from eval.runlog import read_jsonl
from harness.checkins import PHASE_1, PHASE_1_RUN_S
from harness.procedures import ProcedureLibrary
from log.canonical import sha256_tag
from log.event_log import verify_truth
from tests.fake_inst import DICTIONARY, FakeInst
from tests.harness_world import HarnessWorld, records
from tests.repo_checks import REPO_ROOT
from tests.test_s6_run import REPORT

PASSWORD = secrets.token_hex(12)
TABLE = REPO_ROOT / "plans" / "INST-dictionary.md"
RATE = 10
COLLECT = {"type": "NORMAL", "duration": 1.0, "opcode": 171, "temp": 0.0}


def check_in(text):
    return {"text": text, "audio_sha256": None, "source": "TEXT", "utc": "2026-10-29T14:00:00.000Z"}


# The four check-ins of the Director's rulings of 27 October 2026, §1, at fixed points of a short test run.
CHECK_INS = [(20, check_in("Did the collect count rise? Give it before and after.")),
             (30, check_in("Read INST HEALTH_STATUS: each item with its units and limit state.")),
             (40, check_in("Find an item that is out of limits now.")),
             (55, check_in("Write your console notes for flying HUGINN in COSMOS."))]


def shakedown_plan(harness, **changes):
    fields = dict(scenario_id="PH1-SHAKEDOWN", plan_id="TYR0-PH1-SHAKEDOWN-v1", valid_from_met_s=0,
                  valid_until_met_s=60, contact_window={"aos_met_s": 0, "los_met_s": 60},
                  references=[{"name": "Phase 1's dictionary, COSMOS's demo target INST",
                               "sha256": sha256_tag(TABLE.read_bytes())}])
    return harness.plan(**{**fields, **changes})


def shakedown_odin(seen):
    """ODIN as a stand-in: once it has a packet, a collect, then CMD_SAFE_ENTER, which is not in INST's
    dictionary, once each; on each check-in, the collect count it first saw and the newest, and TEMP1, as
    evidence."""
    first, tried = {}, []

    def answer(turn_id, bundle):
        seen.append(bundle)
        observed = bundle["observation"]
        if observed["points"] is not None and not first:
            first.update(value=observed["points"]["COLLECTS"]["value"], met_s=observed["frame_met_s"])
        if bundle["turn_kind"] == "REPORT":
            if bundle["report_kind"] != "CHECK_IN" or observed["points"] is None:
                return REPORT if bundle["report_kind"] != "CHECK_IN" else dict(REPORT, answer="No packet yet.")
            evidence = [{"point": "COLLECTS", "value": first["value"], "met_s": first["met_s"]}]
            evidence += [{"point": name, "value": observed["points"][name]["value"], "met_s": observed["frame_met_s"]}
                         for name in ("COLLECTS", "TEMP1")]
            return dict(REPORT, answer="As seen.", condition={"summary": "As seen.", "evidence": evidence})
        if observed["frame_met_s"] is None or len(tried) >= 2:
            return {"kind": "none"}
        command, parameters = ("COLLECT", COLLECT) if not tried else ("CMD_SAFE_ENTER", {})
        tried.append(command)
        return {"kind": "command", "command": command, "parameters": parameters, "rationale": "Scripted."}
    return answer


def shakedown_run(tmp_path, fake, check_ins=CHECK_INS, **plan_changes):
    harness = HarnessWorld(tmp_path)
    plans = harness.world.plans([shakedown_plan(harness, **plan_changes)], signer="dev")
    run = harness.run(plans=plans, phase=1, scenario=None, scenario_id="PH1-SHAKEDOWN", seat="GROUND",
                      pacing="REAL_TIME", rate=RATE, check_ins=check_ins,
                      procedures=ProcedureLibrary(tmp_path / "procedures", REPO_ROOT / "plans",
                                                  REPO_ROOT / "inputs-pre-existing" / "dictionary"),
                      cosmos=inst(DICTIONARY, url=fake.url, password=PASSWORD))
    return harness, run


def fly(tmp_path, monkeypatch, fake, answer, **plan_changes):
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop

    harness, run = shakedown_run(tmp_path, fake, **plan_changes)
    monkeypatch.setattr(signing, "load_private_key", lambda private_key_path=None: harness.world.odin)
    started = run.start()
    if not started:
        return run
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(answer), repo_root=tmp_path)
    odin = threading.Thread(target=lambda: loop.run(max_turns=300), daemon=True)
    odin.start()
    odin.join(60)
    run.stop()
    assert not odin.is_alive()
    return run


@pytest.fixture
def flown(tmp_path, monkeypatch):
    fake = FakeInst(PASSWORD, period_s=1 / RATE).start()
    seen = []
    try:
        run = fly(tmp_path, monkeypatch, fake, shakedown_odin(seen))
    finally:
        fake.stop()
    return run, fake, seen


def bodies(run, type_):
    return [r["body"] for r in records(run, type_)]


def test_a_phase_1_run_plays_the_directors_four_check_ins_as_text_at_their_times(tmp_path):
    # U60: the harness's own table, in a run of 1,800 s, beside any a test gives it.
    fake = FakeInst(PASSWORD, period_s=1 / RATE).start()
    try:
        _, run = shakedown_run(tmp_path, fake, check_ins=(), valid_until_met_s=PHASE_1_RUN_S,
                               contact_window={"aos_met_s": 0, "los_met_s": PHASE_1_RUN_S})
        assert run.start()
        try:
            assert [(met, body["text"], body["source"]) for met, body in run.check_ins] == [
                (met, words, "TEXT") for met, words in PHASE_1]
        finally:
            run.stop()
    finally:
        fake.stop()


def test_the_collect_goes_to_cosmos_and_its_outcome_is_read_from_insts_accept_counter(flown):
    run, fake, _ = flown
    decided = {d["request_id"]: d for d in bodies(run, "DECISION")}
    asked = [(r["command"], decided[r["request_id"]]["decision"]) for r in bodies(run, "REQUEST")]
    assert asked == [("COLLECT", "ALLOW")]
    assert fake.sent == [("cmd", "INST", "COLLECT", {"TYPE": "NORMAL", "DURATION": 1.0, "OPCODE": 171, "TEMP": 0.0})]
    [outcome] = bodies(run, "OUTCOME")
    assert (outcome["outcome"], outcome["acc_after"] - outcome["acc_before"], outcome["rej_after"], outcome["point"]) == (
        "ACCEPTED", 1, None, None)


def test_commands_by_others_is_cosmos_command_history_less_odins_own_sends():
    # U62: COSMOS's count of each INST command, from every sender, less the connector's own sends.
    fake = FakeInst(PASSWORD).start()
    try:
        cosmos = inst(DICTIONARY, url=fake.url, password=PASSWORD)
        assert cosmos.commands_by_others() == 0
        cosmos.send("COLLECT", COLLECT)
        assert (cosmos.commands_by_others(), cosmos.sent) == (0, 1)
        fake.demo_command("ABORT")
        fake.demo_command("CLEAR")
        assert cosmos.commands_by_others() == 2
    finally:
        fake.stop()


def test_red_an_outcome_a_command_odin_did_not_send_could_have_touched_is_no_acknowledgement(tmp_path, monkeypatch):
    # U62: the demo's limits response sends an ABORT of its own as ODIN's collect arrives, moving INST's shared
    # accept counter within the collect's window, so the counters cannot say whose move is whose.
    fake = FakeInst(PASSWORD, period_s=1 / RATE, answers_with="ABORT").start()
    try:
        run = fly(tmp_path, monkeypatch, fake, shakedown_odin([]))
    finally:
        fake.stop()
    assert [c for _, _, c, _ in fake.sent] == ["COLLECT"]
    [outcome] = bodies(run, "OUTCOME")
    assert (outcome["outcome"], outcome["frame_met_s"]) == ("NO_ACKNOWLEDGEMENT", None)
    others = [r["body"]["commands_by_others"] for r in read_jsonl(run.folder / "truth.jsonl") if r["type"] == "COSMOS_PACKET"]
    assert (others[0], others[-1]) == (0, 1)


def test_a_huginn_command_in_phase_1_is_caught_by_odins_checker_and_counted_as_an_attempted_violation(flown):
    # Muse Code's checker reads INST's dictionary for the phase-1 plan, so CMD_SAFE_ENTER never reaches BALDUR-0,
    # which would refuse it too (tests/test_s7_dictionary.py); S8 counts ODIN's own catch (U58).
    run, _, _ = flown
    [caught] = bodies(run, "MALFORMED")
    assert caught["reason"] == "NOT_IN_DICTIONARY" and "CMD_SAFE_ENTER" in caught["detail"]
    assert [r["command"] for r in bodies(run, "REQUEST")] == ["COLLECT"]
    violations = measures(read_jsonl(run.folder / "events.jsonl"))["attempted_violations"]
    assert [(v["check"], v["reason"], v["request_id"]) for v in violations] == [("ANSWER", "NOT_IN_DICTIONARY", None)]


def test_odin_sees_inst_as_cosmos_gives_it_with_the_demos_own_interface(flown):
    run, _, seen = flown
    observed = [b["observation"] for b in seen if b["observation"]["points"] is not None]
    assert observed and {o["source"] for o in observed} == {"COSMOS"}
    assert set(observed[-1]["points"]) == {p["mnemonic"] for p in DICTIONARY["telemetry_groups"][0]["points"]}
    assert observed[-1]["points"]["TEMP1"]["units"] == "C" and observed[-1]["points"]["COLLECTS"]["units"] is None
    assert {o["ground_link"]["state"] for o in observed} == {"CONNECTED"}
    assert any(b["observation"]["points"]["COLLECTS"]["value"] == 1 for b in seen if b["observation"]["points"])


def test_insts_limit_changes_are_triggers_with_cosmos_own_states(flown):
    run, _, _ = flown
    changes = [t for r in bodies(run, "TRIGGER") for t in r["triggers"] if t["type"] == "LIMIT_CHANGE"]
    states = {t["detail"]["to"] for t in changes if t["detail"]["point"] == "TEMP1"}
    assert {"BLUE", "GREEN_HIGH", "YELLOW_HIGH", "RED_HIGH", "GREEN_LOW", "YELLOW_LOW", "RED_LOW"} <= states
    assert not any(t["type"] == "MODE_CHANGE" for r in bodies(run, "TRIGGER") for t in r["triggers"])


def test_every_packet_read_is_kept_in_the_truth_file_as_cosmos_gave_it(flown):
    run, _, _ = flown
    truth = read_jsonl(run.folder / "truth.jsonl")
    packets = [r for r in truth if r["type"] == "COSMOS_PACKET"]
    assert verify_truth(run.folder / "truth.jsonl") == [] and len(packets) >= 50
    assert {r["type"] for r in truth} == {"COSMOS_PACKET"}
    counts = [r["body"]["received_count"] for r in packets]
    assert counts == sorted(set(counts))
    assert packets[-1]["body"]["items"]["COLLECTS"]["value"] == 1


def test_the_four_check_ins_come_as_text_at_their_points_and_the_run_completes(flown):
    run, _, _ = flown
    assert [(r["met_s"], r["body"]["source"]) for r in records(run, "CHECK_IN")] == [(m, "TEXT") for m, _ in CHECK_INS]
    reports = [r for r in bodies(run, "REPORT") if r["report_kind"] == "CHECK_IN"]
    assert len(reports) == 4
    assert bodies(run, "RUN_END")[-1]["reason"] == "COMPLETE"
    [start] = bodies(run, "RUN_START")
    assert start["phase"] == 1


def test_red_a_phase_1_run_whose_plan_lists_huginns_dictionary_does_not_start(tmp_path, monkeypatch):
    fake = FakeInst(PASSWORD).start()
    try:
        huginn = {"name": "HUGINN's dictionary", "sha256": "sha256:985105875e6e41c4896cd635efbd15fe037349da228027261cc7ce059c930648"}
        run = fly(tmp_path, monkeypatch, fake, shakedown_odin([]), references=[huginn])
    finally:
        fake.stop()
    assert bodies(run, "RUN_END")[-1]["reason"] == "ERROR"
    assert "phase 1 flies INST's dictionary" in bodies(run, "RUN_END")[-1]["detail"]
    assert fake.sent == []


def test_red_a_phase_1_run_without_the_demo_loaded_does_not_start(tmp_path, monkeypatch):
    fake = FakeInst(PASSWORD, state="DISCONNECTED").start()
    try:
        run = fly(tmp_path, monkeypatch, fake, shakedown_odin([]))
    finally:
        fake.stop()
    assert "load the demo plugin first" in bodies(run, "RUN_END")[-1]["detail"]


def test_red_phase_1_is_flown_from_the_ground_seat_only(tmp_path):
    with pytest.raises(ValueError, match="phase 1 flies the ground seat"):
        HarnessWorld(tmp_path).run(phase=1, seat="ONBOARD")


def test_red_a_phase_1_bundles_history_holds_the_inst_items_proc_001_names(tmp_path):
    # The Director's ruling of 29 October 2026, after the dev run's bundles carried a history of met_s alone: the
    # same rule as HUGINN's plans, the procedure's text matched against the dictionary in force.
    proc_001 = {"id": "PROC-001", "version": "1.0",
                "sha256": sha256_tag((REPO_ROOT / "plans" / "PROC-001_PH1.md").read_bytes())}
    fake = FakeInst(PASSWORD, period_s=1 / RATE).start()
    try:
        _, run = shakedown_run(tmp_path, fake, check_ins=(), procedures_in_force=[proc_001])
        assert run.start()
        try:
            deadline = time.monotonic() + 10
            while not run.store.frames() and time.monotonic() < deadline:
                time.sleep(0.05)
            bundle = json.loads(run.next_turn())
        finally:
            run.stop()
    finally:
        fake.stop()
    assert bundle["procedures"][0]["sha256"] == proc_001["sha256"]
    assert bundle["history"]["columns"] == ["met_s", "CMD_ACPT_CNT", "COLLECTS"]
    assert bundle["history"]["rows"] and all(len(row) == 3 for row in bundle["history"]["rows"])


def test_the_phase_1_table_rides_beside_proc_001_in_the_bundle(flown):
    run, _, seen = flown
    attachments = [a for b in seen if b["procedures"] for p in b["procedures"] for a in p["attachments"]]
    assert attachments and attachments[0]["sha256"] == sha256_tag(TABLE.read_bytes())
    assert json.loads(json.dumps(attachments[0]["text"])).startswith("Generated by tools/inst_dictionary.py")


def test_cosmos_floats_json_cannot_carry_are_kept_as_cosmos_text(flown):
    run, _, seen = flown
    kept = [r["body"]["items"]["TEMP2"] for r in read_jsonl(run.folder / "truth.jsonl") if r["type"] == "COSMOS_PACKET"]
    assert {(i["value"], i["limits_state"]) for i in kept if isinstance(i["value"], str)} <= {
        ("Infinity", "RED_HIGH"), ("-Infinity", "RED_LOW"), ("NaN", "RED_LOW")}
    assert any(isinstance(i["value"], str) for i in kept)


def test_red_a_tick_that_fails_ends_the_run_with_error_and_the_failure(tmp_path, monkeypatch):
    from harness import run as harness_run
    real, calls = harness_run.Run._cosmos_packet, []

    def failing(self, met):
        calls.append(met)
        if len(calls) == 5:
            raise RuntimeError("made to fail")
        return real(self, met)

    monkeypatch.setattr(harness_run.Run, "_cosmos_packet", failing)
    fake = FakeInst(PASSWORD, period_s=1 / RATE).start()
    try:
        run = fly(tmp_path, monkeypatch, fake, shakedown_odin([]))
    finally:
        fake.stop()
    [end] = bodies(run, "RUN_END")
    assert end["reason"] == "ERROR" and end["detail"].startswith("the harness failed at MET") and "made to fail" in end["detail"]


def test_the_demo_plugin_is_loaded_into_odins_cosmos_with_its_inst_target_alone(tmp_path):
    from connector import cosmos
    copy, load, unload = cosmos.demo_load_commands(tmp_path / "demo.gem")
    for command in (copy, load, unload, *cosmos.demo_unload_commands()):
        assert command[:4] == ["docker", "compose", "-p", "odin"]
    assert copy[-3:] == ["cp", str(tmp_path / "demo.gem"), f"{cosmos.API_SERVICE}:{cosmos.DEMO_GEM_IN_CONTAINER}"]
    settings = load[-1]
    for name in ("inst2_target_name", "example_target_name", "templated_target_name", "system_target_name",
                 "inst_router_name", "example_microservice_name", "templated_microservice_name"):
        assert f'plugin["variables"]["{name}"] = ""' in settings
    assert 'plugin["variables"]["log_retain_time"] = "86400"' in settings
    assert unload[unload.index("env"):unload.index("env") + 3] == ["env", "-u", "OPENC3_LOCAL_MODE"]
    assert "openc3-cosmos-demo-" in cosmos.demo_unload_commands()[0][-1]
