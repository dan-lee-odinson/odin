"""The simulator in a run (CONTRACT.md §6.4, §9.3, §12): the onboard tap reads every frame beside the
simulator, BALDUR-0's UPLINK route reaches the C&DH with no contact window between, HUGINN's scripted
commands are kept outside the run's contact windows and dropped inside them (the Director's ruling on
U35), and the truth file holds the model's true state, each fault's onset and each command dropped."""

import json

import pytest

from log.chain import verify_chain
from log.event_log import TruthLog, check_truth_record
from tests.huginn_scenarios import FLOWN, bare
from wrapper import frames
from wrapper.huginn import Scenario, load_scenario
from wrapper.link import Link
from wrapper.simulator import Simulator, split_scripted_commands


def test_the_onboard_tap_reads_every_frame_whatever_the_contact_or_receiver():
    link = Link([(0, 5)], address=("127.0.0.1", 0))
    simulator = Simulator(bare("P1_nominal"), windows=link.windows, link=link)
    link.receiver_up = False
    for _ in range(20):
        simulator.step()
    assert [f["CDH_MET"] for f in simulator.tap.history()] == list(range(20))
    assert link.counts == {"SENT": 0, "OUT_OF_CONTACT": 15, "RECEIVER_DOWN": 5, "NO_GROUND": 0}
    assert [f["CDH_MET"] for f in simulator.tap.history(since_met_s=17)] == [17, 18, 19]


def test_the_onboard_tap_reads_the_values_cosmos_reads():
    simulator = Simulator(bare("P1_nominal"), windows=[])
    frame = simulator.step()
    assert simulator.tap.latest() == frames.decode_frame(frames.CODEC.encode(frame))
    assert simulator.tap.latest()["EPS_BATT_V"] != frame["EPS_BATT_V"]   # the 32-bit value, not the model's


def test_the_uplink_route_reaches_the_cdh_at_the_next_tick_out_of_contact_too():
    link = Link([(1000, 2000)], address=("127.0.0.1", 0))
    simulator = Simulator(bare("P1_nominal"), windows=link.windows, link=link)
    simulator.step()
    simulator.uplink("CMD_PLD_SET_STATE", {"state": "ON"})
    assert simulator.spacecraft.eps.state.payload_on is False
    frame = simulator.step()
    assert (frame["PLD_STATE"], frame["CDH_CMD_ACC_CNT"]) == ("ON", 1)
    assert simulator.applied == [(1, "CMD_PLD_SET_STATE", True, "NONE")]


def test_a_reset_on_the_uplink_ends_a_housekeeping_halt_with_the_counter_epoch():
    simulator = Simulator(bare("P4_hk_generation_halt"), windows=[], start_at=1195)
    simulator.uplink("CMD_PLD_SET_STATE", {"state": "OFF"})
    simulator.uplink("CMD_PLD_SET_STATE", {"state": "OFF"})   # the counters before the halt read 2, 0
    stepped = [simulator.step() for _ in range(30)]
    assert stepped[4] is not None and stepped[5] is None and stepped[29] is None   # halted from 1200
    simulator.uplink("CMD_SYS_RESET", {})
    frame = simulator.step()
    assert (frame["CDH_MET"], frame["CDH_CMD_ACC_CNT"], frame["CDH_CMD_REJ_CNT"]) == (1225, 1, 0)
    assert simulator.tap.latest()["CDH_MET"] == 1225


# -- HUGINN's scripted commands (U35) ---------------------------------------------------------

def scripted(commands):
    return [(c["t_s"], c["mnemonic"]) for c in commands]


@pytest.mark.parametrize("name", ["P2_array_string_loss", "P3_stuck_load", "P4_hk_generation_halt"])
def test_every_phase_2_scenario_but_p1_keeps_its_payload_on_before_contact(name):
    kept, dropped = split_scripted_commands(load_scenario(name), FLOWN[name])
    assert (120, "CMD_PLD_SET_STATE") in scripted(kept.commands)
    assert all(not aos <= t < los for t, _ in scripted(kept.commands) for aos, los in FLOWN[name])


def test_every_scripted_command_during_a_pass_is_dropped_so_every_command_then_is_odins():
    split = {name: split_scripted_commands(load_scenario(name), windows) for name, windows in FLOWN.items()}
    assert {name: scripted(dropped) for name, (_, dropped) in split.items()} == {
        "P1_nominal": [(180, "CMD_PLD_SET_STATE"), (240, "CMD_PLD_SET_RATE")],
        "P2_array_string_loss": [], "P3_stuck_load": [], "P4_hk_generation_halt": [(1320, "CMD_SYS_RESET")]}


def test_a_window_drops_commands_from_aos_up_to_but_not_including_los():
    data = dict(load_scenario("P1_nominal").data, commands=[
        {"t_s": t, "mnemonic": "CMD_PLD_SET_RATE", "args": {"rate": 2.0}} for t in (99, 100, 199, 200)])
    kept, dropped = split_scripted_commands(Scenario(data), [(100, 200)])
    assert ([c["t_s"] for c in kept.commands], [c["t_s"] for c in dropped]) == ([99, 200], [100, 199])


def test_the_split_changes_nothing_but_the_commands_and_no_file():
    scenario = load_scenario("P4_hk_generation_halt")
    before = scenario.path.read_bytes()
    kept, _ = split_scripted_commands(scenario, FLOWN["P4_hk_generation_halt"])
    assert (kept.faults, kept.eclipse_intervals_s, kept.seed, kept.duration_s, kept.initial_soc_pct) == (
        scenario.faults, scenario.eclipse_intervals_s, scenario.seed, scenario.duration_s, scenario.initial_soc_pct)
    assert scripted(scenario.commands) == [(120, "CMD_PLD_SET_STATE"), (1320, "CMD_SYS_RESET")]
    assert scenario.path.read_bytes() == before


def a_flown_run(tmp_path, name, start_at=0):
    run = {}
    truth = TruthLog.create(tmp_path / "truth.jsonl", met_clock=lambda: run["simulator"].met_s)
    run["simulator"] = Simulator(load_scenario(name), windows=FLOWN[name], truth=truth, start_at=start_at)
    return run["simulator"], truth


def test_p1_sees_no_command_at_180_or_240(tmp_path):
    simulator, truth = a_flown_run(tmp_path, "P1_nominal")
    seen = [frames.decode_frame(frames.CODEC.encode(simulator.step())) for _ in range(410)]
    assert simulator.applied == []
    assert {(f["PLD_STATE"], f["PLD_RATE"], f["CDH_CMD_ACC_CNT"]) for f in seen} == {("OFF", 1.0, 0)}
    assert [r["body"] for r in truth_records(truth.path) if r["type"] == "SCRIPTED_COMMAND_DROPPED"] == [
        {"scheduled_met_s": t, "command": command, "parameters": parameters, "source": "SCENARIO",
         "contact_window": {"aos_met_s": 0, "los_met_s": 410}, "before_start": False}
        for t, command, parameters in [(180, "CMD_PLD_SET_STATE", {"state": "ON"}),
                                       (240, "CMD_PLD_SET_RATE", {"rate": 2.0})]]


def test_p3_at_aos_reads_payload_on_and_a_1_4_a_load():
    simulator = Simulator(load_scenario("P3_stuck_load"), windows=FLOWN["P3_stuck_load"], start_at=800)
    aos = frames.decode_frame(frames.CODEC.encode(simulator.step()))
    assert (aos["CDH_MET"], aos["PLD_STATE"], aos["CDH_CMD_ACC_CNT"]) == (800, "ON", 1)
    assert aos["EPS_LOAD_I"] == pytest.approx(1.4, abs=1e-6)
    stepped = [simulator.step() for _ in range(100)]
    assert frames.limit_state("EPS_LOAD_I", stepped[-1]["EPS_LOAD_I"]) == "YELLOW_HIGH"   # the stuck load at 900


def test_red_without_its_payload_on_p3s_stuck_load_never_crosses_the_alarm():
    simulator = Simulator(bare("P3_stuck_load"), windows=FLOWN["P3_stuck_load"], start_at=800)
    stepped = [simulator.step() for _ in range(101)]
    assert stepped[0]["PLD_STATE"] == "OFF"
    assert frames.limit_state("EPS_LOAD_I", stepped[-1]["EPS_LOAD_I"]) == "GREEN"


def test_p4s_halt_persists_past_1320_with_no_reset(tmp_path):
    simulator, truth = a_flown_run(tmp_path, "P4_hk_generation_halt", start_at=1100)
    stepped = [simulator.step() for _ in range(430)]
    assert stepped[99] is not None and all(frame is None for frame in stepped[100:])   # MET 1200 to LOS
    assert simulator.applied == [] and simulator.spacecraft.cdh.hk_halted
    [dropped] = [r for r in truth_records(truth.path) if r["type"] == "SCRIPTED_COMMAND_DROPPED"]
    assert dropped["met_s"] == 1320 and dropped["body"]["command"] == "CMD_SYS_RESET"


def test_a_command_the_pre_roll_passed_is_written_with_the_first_tick(tmp_path):
    simulator, truth = a_flown_run(tmp_path, "P4_hk_generation_halt", start_at=1400)
    simulator.step()
    records = truth_records(truth.path)
    assert [(r["type"], r["met_s"]) for r in records] == [
        ("FAULT_ONSET", 1400), ("SCRIPTED_COMMAND_DROPPED", 1400), ("TRUE_STATE", 1400)]
    assert (records[1]["body"]["scheduled_met_s"], records[1]["body"]["before_start"]) == (1320, True)


# -- the truth file (U36) --------------------------------------------------------------------

def truth_records(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def a_run_with_truth(tmp_path, start_at):
    run = {}
    truth = TruthLog.create(tmp_path / "truth.jsonl", met_clock=lambda: run["simulator"].met_s)
    run["simulator"] = Simulator(bare("P4_hk_generation_halt"), windows=[], truth=truth, start_at=start_at)
    return run["simulator"], truth


def test_the_truth_file_holds_each_tick_and_each_fault_onset(tmp_path):
    simulator, truth = a_run_with_truth(tmp_path, 1198)
    for _ in range(4):
        simulator.step()
    records = truth_records(truth.path)
    assert [(r["type"], r["met_s"]) for r in records] == [
        ("TRUE_STATE", 1198), ("TRUE_STATE", 1199), ("FAULT_ONSET", 1200), ("TRUE_STATE", 1200), ("TRUE_STATE", 1201)]
    onset = records[2]["body"]
    assert onset == {"onset_met_s": 1200, "fault": "hk_generation_halt", "string": None, "source": "SCENARIO",
                     "before_start": False}
    halted = records[3]["body"]
    assert (halted["frame_generated"], halted["cdh"]["hk_halted"], halted["faults_active"]) == (
        False, True, ["hk_generation_halt"])
    assert verify_chain(truth.path, check=check_truth_record) == []


def test_a_fault_the_pre_roll_passed_through_is_in_the_truth_file(tmp_path):
    simulator, truth = a_run_with_truth(tmp_path, 1300)
    assert truth_records(truth.path) == []
    simulator.step()
    simulator.step()
    records = truth_records(truth.path)
    assert [(r["type"], r["met_s"]) for r in records] == [("FAULT_ONSET", 1300), ("TRUE_STATE", 1300),
                                                          ("TRUE_STATE", 1301)]
    assert records[0]["body"]["onset_met_s"] == 1200 and records[0]["body"]["before_start"] is True


def test_every_record_a_flown_run_writes_checks_against_the_truth_schema(tmp_path):
    simulator, truth = a_flown_run(tmp_path, "P2_array_string_loss", start_at=2190)
    for _ in range(20):
        simulator.step()
    assert verify_chain(truth.path, check=check_truth_record) == []
    assert {r["type"] for r in truth_records(truth.path)} == {"FAULT_ONSET", "TRUE_STATE"}
