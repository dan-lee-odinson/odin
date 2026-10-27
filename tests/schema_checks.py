"""Loading the contract schemas and checking documents against them (00_HANDOFF.md §4, S1).

Like tests/repo_checks.py, each check returns a list of problems; an empty list means it passed.
Documents are checked through contract/validate.py, as the build's own code checks them.
"""

import json
import re
from pathlib import Path

import yaml

from contract.validate import SCHEMA_DIR, SUFFIX
from contract.validate import check as check_document
from tests.repo_checks import REPO_ROOT

EXAMPLE_DIR = SCHEMA_DIR / "examples"
DICTIONARY = REPO_ROOT / "deps" / "huginn" / "defs" / "tlm_cmd.yaml"

# Schemas that only hold definitions for the others, so no document is checked against them.
DEFINITIONS_ONLY = {"common"}


def schema_names(schema_dir=SCHEMA_DIR):
    return sorted(p.name[:-len(SUFFIX)] for p in Path(schema_dir).glob("*" + SUFFIX))


def load_schema(name, schema_dir=SCHEMA_DIR):
    return json.loads((Path(schema_dir) / (name + SUFFIX)).read_text(encoding="utf-8"))


def load_document(path):
    """A document to check: YAML for plans and acts, read with yaml.safe_load; JSON otherwise."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) if path.suffix in {".yaml", ".yml"} else json.loads(text)


# ---------------------------------------------------------------------------------------
# A field the contract names without settling is marked UNSETTLED (Un) in its description,
# and accepts more than it should until the Director rules. S1 is not done while one remains.

MARKER = re.compile(r"(?i)\bunsettled\b")


def _strings(node, path=()):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, path + (index,))


def check_no_unsettled_markers(schema_dir=SCHEMA_DIR):
    """Every marker left in the schemas and their examples. The READMEs explain the marker, so
    they are not scanned."""
    folder = Path(schema_dir)
    problems = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "README.md"):
        rel = path.relative_to(folder).as_posix()
        text = path.read_text(encoding="utf-8")
        if path.name.endswith(SUFFIX):
            problems += [f"{rel}: {'/'.join(map(str, where))}: {value}"
                         for where, value in _strings(json.loads(text)) if MARKER.search(value)]
        else:
            problems += [f"{rel}:{number}: {line.strip()}"
                         for number, line in enumerate(text.splitlines(), 1) if MARKER.search(line)]
    return problems


# ---------------------------------------------------------------------------------------
# The schemas against HUGINN's pinned dictionary: the 16 points with their units, value types
# and limit states, and the 5 commands with their arguments (CONTRACT.md §6.4, §7.4, §16.2).

UNSIGNED = {"uint16": 65535, "uint32": 4294967295}


def _value_schema(point):
    if point["type"] == "float":
        return {"type": "number"}
    if point["type"] == "enum":
        return {"enum": point["enum_values"]}
    return {"type": "integer", "minimum": 0, "maximum": UNSIGNED[point["type"]]}


def _limit_state_schema(point):
    """The states a point's dictionary limits can produce, by COSMOS's rule (§16.2 U7)."""
    limits = point["limits"]
    if limits["kind"] == "thresholds":
        states = [("GREEN", True), ("YELLOW_LOW", limits["yl"] is not None),
                  ("YELLOW_HIGH", limits["yh"] is not None), ("RED_LOW", limits["rl"] is not None),
                  ("RED_HIGH", limits["rh"] is not None)]
        return {"enum": [state for state, reachable in states if reachable]}
    if limits["kind"] == "state":
        return {"enum": ["GREEN", "RED"]}
    return {"const": "NONE"}


def _annunciation(point):
    """A state point is RED in its annunciating states and GREEN otherwise."""
    if point["limits"]["kind"] != "state":
        return {}
    return {"if": {"required": ["value"], "properties": {"value": {"enum": point["limits"]["annunciates"]}}},
            "then": {"properties": {"limit_state": {"const": "RED"}}},
            "else": {"properties": {"limit_state": {"const": "GREEN"}}}}


def _parameters_schema(command):
    args = command["args"]
    if not args:
        return {"type": "object", "maxProperties": 0}
    properties = {}
    for arg in args:
        if arg["type"] == "enum":
            properties[arg["name"]] = {"enum": arg["enum_values"]}
        else:
            properties[arg["name"]] = {"type": "number", "minimum": arg["min"], "maximum": arg["max"]}
    return {"type": "object", "required": [a["name"] for a in args],
            "additionalProperties": False, "properties": properties}


def check_schemas_match_dictionary(dictionary_path=DICTIONARY, schema_dir=SCHEMA_DIR):
    dictionary = yaml.safe_load(Path(dictionary_path).read_text(encoding="utf-8"))
    common = load_schema("common", schema_dir)["definitions"]
    observed = load_schema("observation", schema_dir)["definitions"]["points"]

    problems = []
    points = [p for group in dictionary["telemetry_groups"] for p in group["points"]]
    names = [p["mnemonic"] for p in points]
    if common["point"]["enum"] != names:
        problems.append(f"common point list {common['point']['enum']} is not the dictionary's {names}")
    if observed["required"] != names or sorted(observed["properties"]) != sorted(names):
        problems.append("the observation's points are not the dictionary's")
    states = [p["mnemonic"] for p in points if p["type"] == "enum"]
    if (common["state_point"]["enum"] != states
            or common["numeric_point"]["enum"] != [n for n in names if n not in states]):
        problems.append("common's state and numeric points are not the dictionary's")
    for point in points:
        entry = observed["properties"].get(point["mnemonic"])
        if entry is None:
            continue
        if entry["properties"]["units"] != {"const": point["units"]}:
            problems.append(f"{point['mnemonic']}: units are not the dictionary's {point['units']!r}")
        if entry["properties"]["value"] != _value_schema(point):
            problems.append(f"{point['mnemonic']}: value type is not the dictionary's {point['type']}")
        if entry["properties"]["limit_state"] != _limit_state_schema(point):
            problems.append(f"{point['mnemonic']}: limit states are not those its dictionary limits produce")
        if {k: entry[k] for k in ("if", "then", "else") if k in entry} != _annunciation(point):
            problems.append(f"{point['mnemonic']}: annunciating states are not the dictionary's")

    commands = dictionary["commands"]
    mnemonics = [c["mnemonic"] for c in commands]
    if common["command"]["enum"] != mnemonics:
        problems.append(f"common command list {common['command']['enum']} is not the dictionary's {mnemonics}")
    for command in commands:
        defined = common.get("parameters_" + command["mnemonic"])
        if defined != _parameters_schema(command):
            problems.append(f"{command['mnemonic']}: parameters are not the dictionary's arguments")

    # A lease names every argument of its command (§16.2 U9).
    rules = load_schema("tyr0_plan", schema_dir)["definitions"]["lease"]["allOf"]
    leased = {rule["if"]["properties"]["command"]["const"]: rule["then"]["properties"]["arguments"]
              for rule in rules}
    for command in commands:
        if command["mnemonic"] not in common["unprotected_command"]["enum"]:
            continue
        arguments = leased.get(command["mnemonic"], {})
        args = [a["name"] for a in command["args"]]
        if arguments.get("required") != args or sorted(arguments.get("properties", {})) != sorted(args):
            problems.append(f"{command['mnemonic']}: a lease's arguments are not the dictionary's")
    return problems
