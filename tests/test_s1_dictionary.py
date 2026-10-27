"""The schemas' points, units, value types, commands and arguments are HUGINN's pinned dictionary's
(CONTRACT.md §6.4, §7.4; deps/huginn/defs/tlm_cmd.yaml at b4dbe61)."""

import pytest
import yaml

from tests.schema_checks import DICTIONARY, check_schemas_match_dictionary


def test_schemas_match_the_pinned_dictionary():
    assert check_schemas_match_dictionary() == []


# Red cases: a scratch copy of the dictionary with one thing changed must no longer match.

def _point(dictionary, mnemonic):
    return next(p for group in dictionary["telemetry_groups"] for p in group["points"]
                if p["mnemonic"] == mnemonic)


def _command(dictionary, mnemonic):
    return next(c for c in dictionary["commands"] if c["mnemonic"] == mnemonic)


CHANGES = {
    "a point renamed": lambda d: _point(d, "EPS_BATT_V").update(mnemonic="EPS_BATT_VOLTS"),
    "a point's units changed": lambda d: _point(d, "EPS_BUS_V").update(units="mV"),
    "a state added to EPS_MODE": lambda d: _point(d, "EPS_MODE")["enum_values"].append("HIBERNATE"),
    "a counter widened to 32 bits": lambda d: _point(d, "CDH_FRAME_CNT").update(type="uint32"),
    "the rate's maximum raised": lambda d: _command(d, "CMD_PLD_SET_RATE")["args"][0].update(max=20),
    "a mode target added": lambda d: _command(d, "CMD_MODE_SET")["args"][0]["enum_values"].append("SAFE"),
    "a sixth command": lambda d: d["commands"].append({"mnemonic": "CMD_DEPLOY", "args": []}),
    "a point given thresholds": lambda d: _point(d, "EPS_SA1_I").update(
        limits={"kind": "thresholds", "decimals": 1, "rl": None, "yl": None, "yh": 1.0, "rh": 1.5}),
    "a red high limit removed": lambda d: _point(d, "EPS_BATT_V")["limits"].update(rh=None),
    "another annunciating state": lambda d: _point(d, "EPS_MODE")["limits"]["annunciates"].append("LOW_POWER"),
    "a state point turned numeric": lambda d: _point(d, "ADM_ECLIPSE").update(type="float"),
    "an argument renamed": lambda d: _command(d, "CMD_MODE_SET")["args"][0].update(name="mode"),
}


@pytest.mark.parametrize("change", CHANGES)
def test_red_dictionary_change_is_caught(tmp_path, change):
    dictionary = yaml.safe_load(DICTIONARY.read_text(encoding="utf-8"))
    CHANGES[change](dictionary)
    copy = tmp_path / "tlm_cmd.yaml"
    copy.write_text(yaml.safe_dump(dictionary, sort_keys=False), encoding="utf-8")
    assert check_schemas_match_dictionary(copy) != []
