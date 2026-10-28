"""S5, the COSMOS connector and the ground seat (00_HANDOFF.md §4; CONTRACT.md §6.4, §9.3, §10.1): telemetry read
from COSMOS, and commands sent only after BALDUR-0 allows them, hazardous ones through COSMOS's no-hazardous-check
send. Done when a command BALDUR-0 refuses never reaches COSMOS.

These run against tests/fake_cosmos.py, which dials the run's link as HUGINN_INT does and answers the
connector's calls in COSMOS's shapes; tests/live_s5_pass.py runs the same against ODIN's COSMOS."""

import json
import re
import secrets
import socket
import threading
import urllib.error

import pytest

from connector.api import CosmosApi, CosmosError, decoded, send_method, utc_of
from contract.validate import check
from eval.results import score_run, summarize
from harness import run as harness_run
from tests.baldur_world import NOMINAL_POINTS
from tests.fake_cosmos import FakeCosmos
from tests.harness_world import HarnessWorld, records
from tests.test_s6_run import REPORT
from wrapper.frames import COMMANDS
from wrapper.huginn import HUGINN

PASSWORD = secrets.token_hex(12)   # made for each test session, never a real credential
PLUGIN_COMMANDS = HUGINN / "gnd" / "openc3" / "plugins" / "openc3-cosmos-huginn" / "targets" / "HUGINN" / "cmd_tlm" / "cmd.txt"
HAZARDOUS = {"CMD_SAFE_ENTER", "CMD_SYS_RESET", "CMD_MODE_SET"}
# A short pass of P3's: contact 800 to 900, so its stuck load does not come into it.
SHORT = dict(valid_until_met_s=910, contact_window={"aos_met_s": 800, "los_met_s": 900})
RATE = 20


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def cosmos():
    """A fake COSMOS waiting to dial a link on a free port, and the connector pointed at it."""
    link_at = ("127.0.0.1", free_port())
    fake = FakeCosmos(link_at, PASSWORD).start()
    yield fake, CosmosApi(fake.url, PASSWORD), link_at
    fake.stop()


# -- the connector -----------------------------------------------------------------------------------

def test_each_command_goes_by_the_send_its_hazard_needs():
    assert {name for name, spec in COMMANDS.items() if spec["hazardous"]} == HAZARDOUS
    assert {name: send_method(name) for name in COMMANDS} == {
        name: "cmd_no_hazardous_check" if name in HAZARDOUS else "cmd" for name in COMMANDS}


def test_cosmos_marks_hazardous_the_same_commands_as_the_dictionary():
    # HUGINN's plugin, generated from the same dictionary, is what COSMOS enforces.
    text = PLUGIN_COMMANDS.read_text(encoding="utf-8")
    marked = {name for name, body in re.findall(r"^COMMAND HUGINN (\w+)[^\n]*\n((?:  [^\n]*\n)*)", text, re.M)
              if "  HAZARDOUS " in body}
    assert marked == HAZARDOUS


def test_a_float_cosmos_json_cannot_carry_is_kept_as_its_text():
    assert [decoded({"json_class": "Float", "raw": raw}) for raw in ("Infinity", "-Infinity", "NaN")] == [
        "Infinity", "-Infinity", "NaN"]
    assert decoded(1.5) == 1.5 and decoded("ON") == "ON"


def test_received_time_is_written_as_section_4s_utc():
    assert utc_of(86400 + 3661.2509) == "1970-01-02T01:01:01.250Z"


def test_red_a_wrong_password_is_refused(cosmos):
    fake, _, _ = cosmos
    with pytest.raises(urllib.error.HTTPError):
        CosmosApi(fake.url, PASSWORD + "x").packet()


def test_red_cosmos_refuses_a_hazardous_command_through_the_ordinary_send(cosmos):
    fake, api, _ = cosmos
    with pytest.raises(CosmosError, match="Hazardous"):
        api.call("cmd", "HUGINN", "CMD_SAFE_ENTER", {})
    assert api.send("CMD_SAFE_ENTER", {}) == "cmd_no_hazardous_check"
    assert fake.sent[-1] == ("cmd_no_hazardous_check", "CMD_SAFE_ENTER", {})


def test_parameters_go_by_cosmos_names(cosmos):
    fake, api, _ = cosmos
    assert api.send("CMD_PLD_SET_RATE", {"rate": 2.0}) == "cmd"
    assert fake.sent == [("cmd", "CMD_PLD_SET_RATE", {"RATE": 2.0})]


def test_before_any_packet_cosmos_shows_no_frame(cosmos):
    _, api, _ = cosmos
    assert api.packet() == {"frame": None, "limits": None, "received_count": 0, "received_utc": None,
                            "packet_utc": None}
    assert api.ground_link() == {"state": "ATTEMPTING", "received_count": 0}


# -- the ground seat -------------------------------------------------------------------------------

def scripted(*commands, seen=None):
    """ODIN as a stand-in that asks for each command in turn on its action turns, once it has a frame to act
    on, and files a plain report on its report turns. seen collects each bundle's observation."""
    def answer(turn_id, bundle):
        if seen is not None:
            seen.append(bundle["observation"])
        if bundle["turn_kind"] == "REPORT":
            return REPORT
        asked = len(bundle["own_requests"])
        if asked < len(commands) and bundle["observation"]["frame_met_s"] is not None:
            command, parameters = commands[asked]
            return {"kind": "command", "command": command, "parameters": parameters, "rationale": "Scripted."}
        return {"kind": "none"}
    return answer


def fly(tmp_path, monkeypatch, cosmos, answer, **plan):
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop

    _, api, link_at = cosmos
    harness = HarnessWorld(tmp_path)
    plans = harness.world.plans([harness.plan(**SHORT, **plan)], signer="dev")
    run = harness.run(plans=plans, seat="GROUND", pacing="REAL_TIME", rate=RATE, cosmos=api, link_at=link_at)
    monkeypatch.setattr(signing, "load_private_key", lambda private_key_path=None: harness.world.odin)
    assert run.start()
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(answer), repo_root=tmp_path)
    odin = threading.Thread(target=lambda: loop.run(max_turns=200), daemon=True)
    odin.start()
    odin.join(60)
    run.stop()
    assert not odin.is_alive()
    return run


def logged(run, type_):
    return [r["body"] for r in records(run, type_)]


ASKED = (("CMD_MODE_SET", {"target": "LOW_POWER"}), ("CMD_PLD_SET_STATE", {"state": "OFF"}), ("CMD_SAFE_ENTER", {}))


@pytest.fixture
def flown(tmp_path, monkeypatch, cosmos):
    seen = []
    run = fly(tmp_path, monkeypatch, cosmos, scripted(*ASKED, seen=seen), prohibited=["CMD_MODE_SET"])
    return run, cosmos[0], seen


def test_a_command_baldur0_refuses_never_reaches_cosmos(flown):
    run, fake, _ = flown
    decided = {d["request_id"]: d["decision"] for d in logged(run, "DECISION")}
    requested = {r["request_id"]: r["command"] for r in logged(run, "REQUEST")}
    assert sorted((requested[i], decision) for i, decision in decided.items()) == [
        ("CMD_MODE_SET", "REFUSE"), ("CMD_PLD_SET_STATE", "ALLOW"), ("CMD_SAFE_ENTER", "ALLOW")]
    assert fake.sent == [("cmd", "CMD_PLD_SET_STATE", {"STATE": "OFF"}),
                         ("cmd_no_hazardous_check", "CMD_SAFE_ENTER", {})]
    assert [d["command"] for d in logged(run, "DISPATCH")] == ["CMD_PLD_SET_STATE", "CMD_SAFE_ENTER"]
    assert {d["route"] for d in logged(run, "DISPATCH")} == {"COSMOS"}


def test_what_baldur0_sent_through_cosmos_reached_the_spacecraft_and_was_read_back_from_cosmos(flown):
    run, _, _ = flown
    assert [(name, accepted) for _, name, accepted, _ in run.simulator.applied] == [
        ("CMD_PLD_SET_STATE", True), ("CMD_SAFE_ENTER", True)]
    assert [o["outcome"] for o in logged(run, "OUTCOME")] == ["ACCEPTED", "ACCEPTED"]


def test_odin_sees_cosmos_view_with_the_ground_link(flown):
    run, fake, seen = flown
    assert seen and {o["source"] for o in seen} == {"COSMOS"}
    assert {o["ground_link"]["state"] for o in seen} == {"CONNECTED"}
    counts = [o["ground_link"]["received_count"] for o in seen]
    assert counts == sorted(counts) and counts[-1] <= fake.rxcnt
    assert {o["staleness_state"] for o in seen if o["frame_met_s"] is not None} <= {"GREEN", "YELLOW"}


def test_the_ground_seat_receives_the_frames_the_spacecraft_sent_with_cosmos_values(flown):
    run, _, _ = flown
    onboard = {f["CDH_MET"]: f for f in run.simulator.tap.history()}
    ground = run.store.frames()
    assert ground and all(frame == onboard[frame["CDH_MET"]] for frame in ground)
    assert [f["CDH_MET"] for f in ground] == sorted({f["CDH_MET"] for f in ground})
    assert all(800 <= f["CDH_MET"] < 900 for f in ground)


def test_red_cosmos_counts_from_earlier_runs_are_not_this_runs_frames(tmp_path, monkeypatch):
    # COSMOS connected and holding a packet from an earlier run, but showing none of this run's: ODIN must
    # see no frame, never the earlier one as current.
    monkeypatch.setattr(harness_run, "GROUND_WAIT_S", 0.05)
    link_at = ("127.0.0.1", free_port())
    earlier = dict(NOMINAL_POINTS, CDH_MET=5, CDH_FRAME_CNT=5)
    fake = FakeCosmos(link_at, PASSWORD, earlier=(earlier, 9), decode=False).start()
    try:
        seen = []
        run = fly(tmp_path, monkeypatch, (fake, CosmosApi(fake.url, PASSWORD), link_at), scripted(seen=seen))
    finally:
        fake.stop()
    assert run.store.latest() is None
    assert seen and all(o["frame_met_s"] is None and o["staleness_state"] == "RED" for o in seen)


def test_red_a_ground_run_whose_cosmos_never_dials_stops_before_its_first_contact(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_run, "DIAL_S", 0.3)
    link_at = ("127.0.0.1", free_port())
    fake = FakeCosmos(link_at, PASSWORD, dial=False).start()
    try:
        run = HarnessWorld(tmp_path).run(seat="GROUND", pacing="REAL_TIME", rate=RATE,
                                         cosmos=CosmosApi(fake.url, PASSWORD), link_at=link_at)
        assert run.start() is False
    finally:
        fake.stop()
    assert [r["reason"] for r in logged(run, "RUN_END")] == ["ERROR"]
    assert run.simulator is None


def test_red_the_ground_seat_runs_in_real_time_only(tmp_path):
    with pytest.raises(ValueError, match="real time"):
        HarnessWorld(tmp_path).run(seat="GROUND", pacing="CHARGED")


def test_every_ground_seat_bundle_odin_saved_conforms(flown):
    run, _, seen = flown
    served = [r["bundle_sha256"] for r in logged(run, "TRIGGER")]
    assert len(served) == len(seen) > 0
    for digest in served:
        bundle = json.loads((run.folder / "inputs" / digest.split(":")[1]).read_bytes())
        assert check("turn_bundle", bundle) == []
        assert bundle["seat"] == "GROUND" and bundle["observation"]["source"] == "COSMOS"


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")   # ODIN's loop ends cleanly
def test_red_cosmos_refusing_an_allowed_command_ends_the_run_with_its_refusal(tmp_path, monkeypatch):
    # The Director's ruling on U59, 28 October 2026: the run ends with ERROR, COSMOS's refusal text in RUN_END,
    # and S8 lists the run as a build defect, not scored.
    link_at = ("127.0.0.1", free_port())
    refusal = "HUGINN CMD_PLD_SET_STATE is disabled"
    fake = FakeCosmos(link_at, PASSWORD, refuse={"CMD_PLD_SET_STATE": refusal}).start()
    try:
        run = fly(tmp_path, monkeypatch, (fake, CosmosApi(fake.url, PASSWORD), link_at), scripted(*ASKED),
                  prohibited=["CMD_MODE_SET"])
    finally:
        fake.stop()
    [end] = logged(run, "RUN_END")
    assert end["reason"] == "ERROR" and end["detail"] == f"COSMOS refused CMD_PLD_SET_STATE: cmd: {refusal}"
    assert logged(run, "DISPATCH") == []
    assert fake.sent == [("cmd", "CMD_PLD_SET_STATE", {"STATE": "OFF"})]   # nothing sent after the refusal
    scored = score_run(run.folder, "PASS-3")
    assert scored["build_defect"] == end["detail"]
    [(_, row)] = summarize([scored]).items()
    assert row["build_defects"] == {run.run_id: end["detail"]} and row["clean"] == "clean in 0 of 0 runs"
