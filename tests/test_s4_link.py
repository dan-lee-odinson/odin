"""The link between the simulator and COSMOS (00_HANDOFF.md §4, S4): frames down and commands up inside
each contact window, nothing either way outside one, and frames dropped at the ground receiver while
COSMOS stays connected. The ground here is a TCP client that reads frames by their LENGTH field, as
COSMOS's HUGINN_INT does, on a free local port."""

import socket
import struct
import time

import pytest

from tests.repo_checks import REPO_ROOT
from wrapper import frames
from tests.huginn_scenarios import bare
from wrapper.link import Link, link_address, split_commands
from wrapper.simulator import Simulator


class Ground:
    """A stand-in for COSMOS's HUGINN_INT: dials the link, reads frames by their LENGTH field, writes
    commands as bare bytes."""

    def __init__(self, link):
        self.socket = socket.create_connection(link.address, timeout=2)
        self._waiting = b""
        deadline = time.monotonic() + 2
        while link.clients < 1 and time.monotonic() < deadline:
            time.sleep(0.01)

    def send(self, data):
        self.socket.sendall(data)

    def frames(self, settle=0.2):
        """Every whole frame received so far, decoded."""
        self.socket.settimeout(settle)
        try:
            while True:
                data = self.socket.recv(65536)
                if not data:
                    raise ConnectionError("the link closed the connection")
                self._waiting += data
        except TimeoutError:
            pass
        read = []
        while len(self._waiting) >= 4:
            length = struct.unpack_from(">H", self._waiting, 2)[0]
            if len(self._waiting) < 4 + length:
                break
            read.append(frames.decode_frame(self._waiting[:4 + length]))
            self._waiting = self._waiting[4 + length:]
        return read

    def close(self):
        self.socket.close()


@pytest.fixture
def world():
    made = []

    def make(windows, scenario="P1_nominal", start_at=0):
        link = Link(windows, address=("127.0.0.1", 0)).start()
        simulator = Simulator(bare(scenario), windows=link.windows, link=link, start_at=start_at)
        made.append(link)
        return link, simulator

    yield make
    for link in made:
        link.stop()


def run(simulator, ticks, ground=None, settle=0.05):
    """Step the simulator, giving the ground time to read and the link time to receive."""
    stepped = []
    for _ in range(ticks):
        stepped.append(simulator.step())
        if ground is not None:
            time.sleep(0.002)
    time.sleep(settle)
    return stepped


def acc(simulator):
    return simulator.spacecraft.cdh.acc_count


def test_the_link_listens_where_config_ports_yaml_says_and_never_on_huginns_simulator_port():
    assert link_address() == ("127.0.0.1", 8713)
    assert link_address()[1] != 7801
    assert (REPO_ROOT / "config" / "ports.yaml").read_text(encoding="utf-8").count("link: 8713") == 1


def test_frames_go_down_in_contact(world):
    link, simulator = world([(0, 100)])
    ground = Ground(link)
    run(simulator, 20, ground)
    received = ground.frames()
    assert [f["CDH_MET"] for f in received] == list(range(20))
    assert received[-1] == frames.decode_frame(frames.CODEC.encode(simulator.tap.latest()))
    assert link.counts["SENT"] == 20


def test_a_window_runs_from_aos_up_to_but_not_including_los(world):
    link, simulator = world([(5, 10), (15, 18)])
    ground = Ground(link)
    run(simulator, 25, ground)
    assert [f["CDH_MET"] for f in ground.frames()] == [5, 6, 7, 8, 9, 15, 16, 17]
    assert link.counts["OUT_OF_CONTACT"] == 17


def test_commands_go_up_in_contact_and_take_effect_by_the_next_frame(world):
    link, simulator = world([(0, 100)])
    ground = Ground(link)
    run(simulator, 5, ground)
    ground.send(frames.encode_command("CMD_PLD_SET_STATE", {"state": "ON"}))
    time.sleep(0.1)
    frame = simulator.step()
    assert (frame["PLD_STATE"], frame["CDH_CMD_ACC_CNT"]) == ("ON", 1)
    assert simulator.applied == [(5, "CMD_PLD_SET_STATE", True, "NONE")]


def test_two_commands_in_one_write_are_both_received(world):
    link, simulator = world([(0, 100)])
    ground = Ground(link)
    ground.send(frames.encode_command("CMD_PLD_SET_STATE", {"state": "ON"})
                + frames.encode_command("CMD_PLD_SET_RATE", {"rate": 4.0}))
    run(simulator, 1, settle=0.1)
    frame = simulator.step()
    assert (frame["PLD_RATE"], frame["CDH_CMD_ACC_CNT"]) == (4.0, 2)


def test_a_command_split_across_writes_is_received_once_whole(world):
    link, simulator = world([(0, 100)])
    ground = Ground(link)
    raw = frames.encode_command("CMD_PLD_SET_RATE", {"rate": 4.0})
    ground.send(raw[:3])
    time.sleep(0.1)
    simulator.step()
    assert acc(simulator) == 0
    ground.send(raw[3:])
    time.sleep(0.1)
    simulator.step()
    assert simulator.spacecraft.cdh.rej_count == 1 and simulator.spacecraft.cdh.rej_reason == "MODE_INHIBIT"


def test_an_opcode_the_dictionary_does_not_define_is_accounted_as_unknown(world):
    link, simulator = world([(0, 100)])
    ground = Ground(link)
    ground.send(b"\x00\x63\x01\x02")
    time.sleep(0.1)
    frame = simulator.step()
    assert (frame["CDH_CMD_REJ_CNT"], frame["CDH_REJ_REASON"]) == (1, "UNKNOWN_OPCODE")
    assert split_commands(b"\x00\x63\x01\x02") == ([b"\x00\x63\x01\x02"], b"")


def test_red_commands_sent_out_of_contact_never_reach_the_spacecraft(world):
    link, simulator = world([(10, 20)])
    ground = Ground(link)
    run(simulator, 3, ground)
    ground.send(frames.encode_command("CMD_SAFE_ENTER", {}))
    time.sleep(0.1)
    run(simulator, 12, ground)
    assert acc(simulator) == 0 and simulator.spacecraft.eps.state.mode == "NOMINAL"
    assert link.commands_lost == 1


def test_dropping_frames_at_the_receiver_leaves_cosmos_connected(world):
    link, simulator = world([(0, 200)])
    ground = Ground(link)
    run(simulator, 10, ground)
    link.receiver_up = False
    run(simulator, 40, ground)
    assert link.clients == 1
    assert [f["CDH_MET"] for f in ground.frames()] == list(range(10))
    assert link.counts["RECEIVER_DOWN"] == 40
    # Still connected: a command goes up, and once the receiver is back the frames show it.
    ground.send(frames.encode_command("CMD_PLD_SET_STATE", {"state": "ON"}))
    time.sleep(0.1)
    link.receiver_up = True
    run(simulator, 5, ground)
    after = ground.frames()
    assert [f["CDH_MET"] for f in after] == list(range(50, 55))
    assert after[0]["PLD_STATE"] == "ON" and after[0]["CDH_CMD_ACC_CNT"] == 1


def test_red_a_receiver_that_closed_the_connection_would_be_caught(world):
    # The check the test above relies on: a link that hung up on the ground would be seen.
    link, simulator = world([(0, 200)])
    ground = Ground(link)
    run(simulator, 5, ground)
    link.stop()
    with pytest.raises(ConnectionError):
        for _ in range(20):
            ground.frames()
            time.sleep(0.05)


def test_frames_resume_when_cosmos_dials_again(world):
    link, simulator = world([(0, 200)])
    first = Ground(link)
    run(simulator, 5, first)
    first.close()
    deadline = time.monotonic() + 2
    while link.clients and time.monotonic() < deadline:
        time.sleep(0.01)
    run(simulator, 5)
    assert link.counts["NO_GROUND"] == 5
    second = Ground(link)
    run(simulator, 5, second)
    assert [f["CDH_MET"] for f in second.frames()] == list(range(10, 15))


def test_a_housekeeping_halt_sends_nothing_on_a_live_link(world):
    link, simulator = world([(1100, 1400)], scenario="P4_hk_generation_halt", start_at=1100)
    ground = Ground(link)
    run(simulator, 140, ground)
    received = [f["CDH_MET"] for f in ground.frames()]
    assert received == list(range(1100, 1200))
    assert link.clients == 1
