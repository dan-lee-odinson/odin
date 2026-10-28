"""The dictionary in force (the Director's ruling on U58, 28 October 2026): the dictionary the plan in force
lists among its references, found through config/dictionaries.yaml, the registry from a dictionary reference's
SHA-256 to the machine-readable dictionary, whose own SHA-256 is checked when it is read.

BALDUR-0 checks each request's command and arguments against it; a command or argument value outside it is
refused at the CLASS check as NOT_IN_DICTIONARY, an attempted violation. Each command's class comes from it:
HUGINN's from BALDUR-0's own class configuration (gateway/rules.py), INST's from its file. Its protective
commands are its commands of class C3 (§5.5): CMD_SAFE_ENTER and CMD_SYS_RESET in HUGINN's, ABORT in INST's. A
command's outcome is read from its counters (§9.3): HUGINN's accepted and rejected counters and rejection reason,
INST's accept counter alone, since the demo target counts no rejected commands.
A plan that lists no registered dictionary flies HUGINN's, as every plan did before phase 1's; one that lists
two is refused.
"""

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from gateway.rules import AFFECTED, COMMAND_CLASS, COUNTERS

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "config" / "dictionaries.yaml"
DEFAULT = "HUGINN"


@dataclass(frozen=True)
class Dictionary:
    name: str
    target: str
    commands: dict   # mnemonic -> the dictionary's command, with its args
    classes: dict    # mnemonic -> C1 to C4
    counters: dict   # accepted, rejected and reason: the points a command's outcome is read from, or None
    affected: dict   # mnemonic -> the point the command changes, or None
    document: dict = field(default=None, compare=False, repr=False)   # the dictionary's file, parsed

    @property
    def protective(self):
        return frozenset(command for command, class_ in self.classes.items() if class_ == "C3")

    def refusal(self, command, parameters):
        """Why a command with these parameters is not in this dictionary, or None if it is."""
        spec = self.commands.get(command)
        if spec is None:
            return f"{command} is not in {self.name}'s dictionary, the dictionary in force"
        args = {arg["name"]: arg for arg in spec["args"]}
        if set(parameters) != set(args):
            return f"{command} takes {sorted(args) or 'no arguments'} in {self.name}'s dictionary"
        for name, value in sorted(parameters.items()):
            arg = args[name]
            if arg["type"] == "enum":
                inside = value in arg["enum_values"]
            else:
                inside = isinstance(value, (int, float)) and not isinstance(value, bool) and arg["min"] <= value <= arg["max"]
            if not inside:
                return f"{command} {name} {value!r} is outside {self.name}'s dictionary"
        return None


def registry():
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["dictionaries"]


@lru_cache(maxsize=None)
def _load(name, target, file, sha256, classes):
    data = (ROOT / file).read_bytes()
    found = "sha256:" + hashlib.sha256(data).hexdigest()
    if found != sha256:
        raise ValueError(f"{file} is {found}, not the {sha256} the registry gives for {name}")
    document = yaml.safe_load(data)
    commands = {command["mnemonic"]: command for command in document["commands"]}
    if classes == "gateway/rules.py":   # HUGINN's: BALDUR-0's own class configuration and HUGINN's accounting
        return Dictionary(name, target, commands, {m: COMMAND_CLASS[m] for m in commands}, dict(COUNTERS),
                          {m: AFFECTED.get(m) for m in commands}, document)
    counters = {"accepted": document["command_accounting"]["accepted"],
                "rejected": document["command_accounting"]["rejected"], "reason": None}
    return Dictionary(name, target, commands, {m: c["class"] for m, c in commands.items()}, counters,
                      {m: None for m in commands}, document)


def load(entry):
    return _load(entry["name"], entry["target"], entry["file"], entry["sha256"], entry["classes"])


def listed(document):
    """The registry's entries for the dictionaries a plan lists among its references."""
    hashes = {reference.get("sha256") for reference in (document.get("references") or []) if isinstance(reference, dict)}
    return [entry for entry in registry() if entry["reference"] in hashes]


def for_plan(document):
    """The dictionary in force under a plan. Raises ValueError for a plan that lists two."""
    entries = listed(document)
    if len(entries) > 1:
        raise ValueError(f"the plan lists {len(entries)} dictionaries: {', '.join(e['name'] for e in entries)}")
    return load(entries[0] if entries else next(e for e in registry() if e["name"] == DEFAULT))
