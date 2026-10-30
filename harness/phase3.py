"""Phase 3's held-out scenarios, read where they are sealed (CONTRACT.md §10.3; the Director's approved phase-3
document, §4; his rulings of 28 and 29 October 2026). S9's first piece.

The scenario files stay outside the repository until the held-out runs are complete, in the held-out folder the
caller names. Nothing here names a scenario or holds any of its values: each comes from the sealed files at run time,
and only after they check against the seal in force, the first hash phase3/SEAL.md names. A file that does not match
the sealed manifest, or a file in the sealed folder that the manifest does not list, stops everything.

Each sealed scenario file carries HUGINN's own scenario under `huginn`, which HUGINN builds unchanged, beside what
the harness and the wrapper read: the plans it names, the run's span and seats, its check-ins, the scripted faults
and the outside feeds.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from wrapper.feeds import CoreFeeds
from wrapper.huginn import HUGINN, Scenario
from wrapper.link import in_window

ROOT = Path(__file__).resolve().parent.parent
SEAL = ROOT / "phase3" / "SEAL.md"
HASH = re.compile(r"\bsha256:[0-9a-f]{64}\b")
SUFFIX = ".scenario.yaml"


class SealBroken(Exception):
    pass


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def seal_in_force(seal_path=SEAL):
    """The seal in force: the first hash phase3/SEAL.md names, the first seal kept beside it."""
    found = HASH.findall(Path(seal_path).read_text(encoding="utf-8"))
    if not found:
        raise SealBroken(f"{seal_path} names no seal")
    return found[0]


@dataclass(frozen=True)
class HeldOutScenario:
    label: str
    scenario_id: str
    huginn: Scenario
    plan_paths: tuple
    run: dict
    script: dict
    feeds: dict
    geometry: dict

    @property
    def seats(self):
        """[(from_met_s, to_met_s, seat, pacing)] in MET order."""
        return sorted((s["from_met_s"], s["to_met_s"], s["seat"], s["pacing"]) for s in self.run["seats"])

    @property
    def windows(self):
        """[(aos_met_s, los_met_s)] of the scenario's contacts, in order."""
        return sorted((c["aos_met_s"], c["los_met_s"]) for c in self.geometry["contacts"])

    @property
    def receiver_down(self):
        """[(from_met_s, until_met_s)] of the scripted ground-receiver fault (S9, piece 3), each half-open; [] for a
        scenario without one."""
        fault = self.script.get("ground_receiver")
        return [(fault["failed_from_met_s"], fault["until_met_s"])] if fault else []

    def revocation(self, restore_act):
        """The scripted revocation (S9, piece 4) for one run, given the restore act signed in advance for it, as
        harness.run.Run takes it; None for a scenario without one."""
        script = self.script
        if "revocation" not in script:
            return None
        return {"restore_act": restore_act, "restore_after_s": script["restore"]["after_revocation_s"],
                "second_presentation_after_s": script["second_presentation"]["after_restore_s"],
                "safety_test_after_s": script["safety_test"]["after_restore_s"],
                "safety_test_request": script["safety_test"]["request"]}

    def core_feeds(self):
        """The run's station_receiver and beacon (S9, piece 2): in contact by its windows, the slant range from
        HUGINN's pinned orbit at the scenario's place in the campaign week (campaign time = MET +
        epoch_campaign_t_s, from the campaign epoch), and the own receiver down through a scripted fault, when
        it reports NO_SIGNAL and hears no beacon (piece 3)."""
        from sim.orbit import Orbit
        orbit = Orbit(HUGINN / "defs" / "orbit", self.geometry["campaign_epoch_utc"])
        offset_s = self.geometry["epoch_campaign_t_s"]
        return CoreFeeds(in_contact=lambda met_s: in_window(met_s, self.windows),
                         receiver_up=lambda met_s: not in_window(met_s, self.receiver_down),
                         slant_range_km=lambda met_s: orbit.look_angles_at(met_s + offset_s)[2])


class HeldOut:
    """The sealed folder of a held-out folder, checked against the seal in force before anything is read."""

    def __init__(self, folder, seal=None):
        self.sealed = Path(folder) / "sealed"
        manifest = (self.sealed / "MANIFEST.sha256").read_bytes()
        expected = seal or seal_in_force()
        if sha(manifest) != expected:
            raise SealBroken(f"the sealed manifest hashes to {sha(manifest)}, not the seal in force {expected}")
        self.files = {}
        for line in manifest.decode("utf-8").splitlines():
            digest, name = line.split("  ")
            data = (self.sealed / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise SealBroken(f"{name} does not match the sealed manifest")
            self.files[name] = data
        extra = sorted(p.name for p in self.sealed.iterdir()
                       if p.is_file() and p.name not in self.files and p.name != "MANIFEST.sha256")
        if extra:
            raise SealBroken(f"in the sealed folder but not in its manifest: {extra}")

    def labels(self):
        return sorted(name[:-len(SUFFIX)] for name in self.files if name.endswith(SUFFIX))

    def scenario(self, label):
        name = f"{label}{SUFFIX}"
        if name not in self.files:
            raise KeyError(f"no sealed scenario {label}")
        document = yaml.safe_load(self.files[name])
        plans = []
        for plan in document["plans"]:
            plan_name = plan if plan.endswith(".yaml") else f"{plan}.yaml"
            if plan_name not in self.files:
                raise SealBroken(f"{label} names plan {plan}, which is not sealed")
            plans.append(self.sealed / plan_name)
        scenario_ids = {yaml.safe_load(self.files[p.name])["scenario_id"] for p in plans}
        if len(scenario_ids) != 1:
            raise SealBroken(f"{label}'s plans name scenarios {sorted(scenario_ids)}, not one")
        return HeldOutScenario(label=label, scenario_id=scenario_ids.pop(),
                               huginn=Scenario(document["huginn"], self.sealed / name), plan_paths=tuple(plans),
                               run=document["run"], script=document["script"], feeds=document["feeds"],
                               geometry=document["geometry"])
