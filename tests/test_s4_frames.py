"""Frames and commands as bytes on the link (CONTRACT.md §6.4, §16.2 U7): read and written as COSMOS reads
and writes them, by HUGINN's dictionary, so the onboard seat and COSMOS see the same values."""

import struct

import pytest

from contract.validate import check
from wrapper import frames
from wrapper.huginn import DICTIONARY, CommandCodec, build, load_scenario


def a_frame(**changes):
    craft = build(load_scenario("P1_nominal"))
    frame = craft.step()
    frame.update(changes)
    return frame


def test_a_frame_reads_back_as_its_32_bit_values():
    frame = a_frame(EPS_MODE="LOW_POWER", PLD_STATE="ON", CDH_REJ_REASON="MODE_INHIBIT", PLD_RATE=0.3)
    read = frames.decode_frame(frames.CODEC.encode(frame))
    assert list(read) == list(frames.POINTS)
    for name, value in frame.items():
        if frames.POINTS[name]["type"] == "float":
            assert read[name] == struct.unpack(">f", struct.pack(">f", value))[0]
        else:
            assert read[name] == value
    assert read["PLD_RATE"] != 0.3   # 0.3 is not a 32-bit float; COSMOS reads what was sent


@pytest.mark.parametrize("damage", ["short", "sync", "length", "extra byte"])
def test_red_bytes_that_are_not_one_frame_are_refused(damage):
    raw = bytearray(frames.CODEC.encode(a_frame()))
    if damage == "short":
        raw = raw[:3]
    elif damage == "sync":
        raw[0] ^= 0x01
    elif damage == "length":
        raw[3] ^= 0x01
    else:
        raw += b"\x00"
    with pytest.raises(ValueError):
        frames.decode_frame(bytes(raw))


LIMIT_CASES = [
    ("EPS_BATT_V", 6.79, "RED_LOW"), ("EPS_BATT_V", 6.8, "YELLOW_LOW"), ("EPS_BATT_V", 7.19, "YELLOW_LOW"),
    ("EPS_BATT_V", 7.2, "GREEN"), ("EPS_BATT_V", 8.3, "GREEN"), ("EPS_BATT_V", 8.31, "YELLOW_HIGH"),
    ("EPS_BATT_V", 8.5, "YELLOW_HIGH"), ("EPS_BATT_V", 8.51, "RED_HIGH"),
    ("EPS_BATT_SOC", 19.9, "RED_LOW"), ("EPS_BATT_SOC", 34.9, "YELLOW_LOW"), ("EPS_BATT_SOC", 100.0, "GREEN"),
    ("EPS_LOAD_I", -5.0, "GREEN"), ("EPS_LOAD_I", 1.51, "YELLOW_HIGH"), ("EPS_LOAD_I", 2.01, "RED_HIGH"),
    ("EPS_MODE", "SAFE", "RED"), ("EPS_MODE", "LOW_POWER", "GREEN"), ("EPS_MODE", "NOMINAL", "GREEN"),
    ("PLD_RATE", 50.0, "NONE"), ("CDH_CMD_REJ_CNT", 9, "NONE"), ("CDH_FRAME_CNT", 0, "NONE"), ("EPS_SA1_I", 0.0, "NONE"),
]


@pytest.mark.parametrize("name, value, state", LIMIT_CASES, ids=[f"{n}={v}" for n, v, _ in LIMIT_CASES])
def test_limit_states_follow_cosmos_rule_from_the_dictionary(name, value, state):
    assert frames.limit_state(name, value) == state


def test_the_points_are_what_the_observation_schema_allows():
    points = frames.points(frames.decode_frame(frames.CODEC.encode(a_frame(EPS_MODE="SAFE"))))
    observation = {"source": "ONBOARD", "frame_met_s": 0, "received_utc": "2026-10-28T12:00:00.000Z",
                   "age_s": 0, "staleness_state": None, "ground_link": None, "points": points}
    assert check("observation", observation) == []
    assert points["EPS_MODE"] == {"value": "SAFE", "units": "n/a", "limit_state": "RED"}


COMMANDS = [("CMD_PLD_SET_STATE", {"state": "ON"}), ("CMD_PLD_SET_STATE", {"state": "OFF"}),
            ("CMD_PLD_SET_RATE", {"rate": 2.0}), ("CMD_PLD_SET_RATE", {"rate": 10.0}), ("CMD_SAFE_ENTER", {}),
            ("CMD_SYS_RESET", {}), ("CMD_MODE_SET", {"target": "LOW_POWER"}), ("CMD_MODE_SET", {"target": "NOMINAL"})]


@pytest.mark.parametrize("command, parameters", COMMANDS)
def test_a_command_written_as_cosmos_writes_it_is_read_by_huginn(command, parameters):
    raw = frames.encode_command(command, parameters)
    assert len(raw) == frames.command_length(frames.COMMANDS[command]["opcode"])
    assert CommandCodec(DICTIONARY).decode(raw) == (command, parameters)


def test_the_command_bytes_are_the_packet_definitions():
    # HUGINN's cmd.txt: a 16-bit opcode, then STATE and TARGET as 8-bit indices and RATE as a 32-bit float.
    assert frames.encode_command("CMD_PLD_SET_STATE", {"state": "ON"}) == b"\x00\x01\x01"
    assert frames.encode_command("CMD_PLD_SET_RATE", {"rate": 2.0}) == b"\x00\x02" + struct.pack(">f", 2.0)
    assert frames.encode_command("CMD_SYS_RESET", {}) == b"\x00\x04"
    assert frames.encode_command("CMD_MODE_SET", {"target": "LOW_POWER"}) == b"\x00\x05\x01"
    assert frames.command_length(99) is None


def test_red_a_command_with_other_parameters_is_refused():
    with pytest.raises(ValueError):
        frames.encode_command("CMD_PLD_SET_RATE", {"rate": 2.0, "state": "ON"})
    with pytest.raises(ValueError):
        frames.encode_command("CMD_SAFE_ENTER", {"target": "SAFE"})
