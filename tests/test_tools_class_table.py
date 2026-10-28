"""BALDUR-0's command classes as ODIN reads them (the Director's ruling of 28 October 2026): a table generated
from BALDUR-0's own class configuration, never typed, frozen in plans/, covering every command of HUGINN's
dictionary with its class and whether it needs a lease, and naming the C3 PROTECT commands no plan can
prohibit or restrict."""

import pytest

from gateway.rules import COMMAND_CLASS, PROTECTIVE
from tools.class_table import FROZEN, generate
from wrapper.frames import COMMANDS


def rows(data):
    return [line.split(" | ") for line in data.decode("utf-8").splitlines() if line.startswith("| `")]


def test_the_frozen_table_is_its_regeneration_from_baldur0s_configuration():
    assert FROZEN.read_bytes() == generate()


def test_every_dictionary_command_has_its_class_in_the_dictionarys_order():
    assert [(r[0].strip("| `"), r[1].split()[0]) for r in rows(FROZEN.read_bytes())] == [
        (command, COMMAND_CLASS[command]) for command in COMMANDS]


def test_the_c3_protect_commands_are_named_as_no_plan_can_restrict_them():
    text = FROZEN.read_bytes().decode("utf-8")
    assert {r[0].strip("| `") for r in rows(FROZEN.read_bytes()) if r[1] == "C3 PROTECT"} == PROTECTIVE
    assert "No plan can prohibit or restrict the C3 PROTECT commands, `CMD_SAFE_ENTER` and `CMD_SYS_RESET`" in text


def test_red_a_class_changed_in_baldur0_changes_the_table():
    moved = dict(COMMAND_CLASS, CMD_PLD_SET_RATE="C4")
    assert generate(command_class=moved) != FROZEN.read_bytes()


@pytest.mark.parametrize("command_class", [
    {c: k for c, k in COMMAND_CLASS.items() if c != "CMD_MODE_SET"},   # a dictionary command with no class
    dict(COMMAND_CLASS, CMD_NOT_IN_DICTIONARY="C1"),                    # a classed command not in the dictionary
    dict(COMMAND_CLASS, CMD_MODE_SET="C5")])                            # a class with no wording
def test_red_the_generator_stops_rather_than_guess(command_class):
    with pytest.raises(ValueError):
        generate(command_class=command_class)
