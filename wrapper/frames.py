"""HUGINN's frames and commands as bytes on the link, read and written as COSMOS reads and writes them.

The simulator packs each housekeeping frame with HUGINN's own codec (sim/interface.py), and COSMOS
reads it by the packet definition HUGINN generates from the same dictionary. The onboard seat reads
the same bytes beside the simulator (CONTRACT.md §6.4), so its values are COSMOS's values: an
analogue point is the 32-bit float on the wire, not the simulator's 64-bit one. Each point's limit
state is computed from the dictionary by COSMOS's rule (§16.2, U7), so the two seats agree.

Commands go the other way as COSMOS writes them: the opcode, then each argument, an enumerated one
as its index and a number as a 32-bit float, which is what HUGINN's CommandCodec reads.
"""

import struct

from wrapper.huginn import DICTIONARY, FrameCodec

CODEC = FrameCodec(DICTIONARY)
HEADER_SIZE = struct.calcsize(CODEC.header_format)
POINTS = {p["mnemonic"]: p for group in DICTIONARY["telemetry_groups"] for p in group["points"]}
COMMANDS = {c["mnemonic"]: c for c in DICTIONARY["commands"]}
OPCODES = {c["opcode"]: c for c in DICTIONARY["commands"]}
ENDIAN = CODEC.endian
_ARG_FORMAT = {"enum": "B", "float": "f"}


def decode_frame(raw):
    """One frame's bytes -> {mnemonic: value} in dictionary order. Raises ValueError for bytes that
    are not one whole frame."""
    if len(raw) < HEADER_SIZE:
        raise ValueError(f"{len(raw)} bytes is shorter than a frame header")
    sync, length = struct.unpack_from(CODEC.header_format, raw, 0)
    if sync != CODEC.sync_value:
        raise ValueError(f"sync marker {sync:#06x}, not {CODEC.sync_value:#06x}")
    if length != CODEC.body_size or len(raw) != HEADER_SIZE + length:
        raise ValueError(f"{len(raw)} bytes with LENGTH {length}; a frame is {CODEC.frame_size}")
    values = dict(zip((p["mnemonic"] for p in CODEC.body), struct.unpack_from(CODEC.body_format, raw, HEADER_SIZE)))
    return {name: point["enum_values"][values[name]] if point["type"] == "enum" else values[name]
            for name, point in POINTS.items()}


def limit_state(mnemonic, value):
    """The Director's ruling on U7 (26 October 2026). A point with numeric thresholds: below the red low
    limit RED_LOW, else below the yellow low limit YELLOW_LOW, else above the red high limit RED_HIGH,
    else above the yellow high limit YELLOW_HIGH, else GREEN; a limit the dictionary leaves out never
    trips. EPS_MODE is RED in its annunciating state and GREEN otherwise. Every other point is NONE."""
    limits = POINTS[mnemonic]["limits"]
    if limits["kind"] == "state":
        return "RED" if value in limits["annunciates"] else "GREEN"
    if limits["kind"] != "thresholds":
        return "NONE"
    rl, yl, yh, rh = (limits[key] for key in ("rl", "yl", "yh", "rh"))
    if rl is not None and value < rl:
        return "RED_LOW"
    if yl is not None and value < yl:
        return "YELLOW_LOW"
    if rh is not None and value > rh:
        return "RED_HIGH"
    if yh is not None and value > yh:
        return "YELLOW_HIGH"
    return "GREEN"


def points(frame):
    """A decoded frame as the observation's points (§6.4): each {value, units, limit_state}."""
    return {name: {"value": frame[name], "units": point["units"], "limit_state": limit_state(name, frame[name])}
            for name, point in POINTS.items()}


def encode_command(command, parameters):
    """A command's bytes as COSMOS writes them for HUGINN's packet definition."""
    spec = COMMANDS[command]
    if set(parameters) != {arg["name"] for arg in spec["args"]}:
        raise ValueError(f"{command} takes {[arg['name'] for arg in spec['args']]}, not {sorted(parameters)}")
    data = struct.pack(ENDIAN + "H", spec["opcode"])
    for arg in spec["args"]:
        value = parameters[arg["name"]]
        if arg["type"] == "enum":
            value = arg["enum_values"].index(value)
        data += struct.pack(ENDIAN + _ARG_FORMAT[arg["type"]], value)
    return data


def command_length(opcode):
    """How many bytes a command with this opcode takes on the link, or None for an opcode the
    dictionary does not define."""
    spec = OPCODES.get(opcode)
    if spec is None:
        return None
    return 2 + sum(struct.calcsize(_ARG_FORMAT[arg["type"]]) for arg in spec["args"])
