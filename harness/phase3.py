"""Phase 3's held-out scenarios, read where they are sealed (CONTRACT.md §10.3; the Director's approved phase-3
document, §4; his rulings of 28 and 29 October 2026). S9's first piece.

The scenario files stay outside the repository until the held-out runs are complete, in the held-out folder the
caller names. Nothing here names a scenario or holds any of its values: each comes from the sealed files at run time,
and only after they check against the seal in force, the first hash phase3/SEAL.md names. A file that does not match
the sealed manifest, or a file in the sealed folder that the manifest does not list, stops everything.

Each sealed scenario file carries HUGINN's own scenario under `huginn`, which HUGINN builds unchanged, beside what
the harness and the wrapper read: the plans it names, the run's span and seats, its check-ins, the scripted faults
and the outside feeds. Every feed rule is read from its sealed feed details here (the Director's ruling of 30 October
2026): each detail must state its rule once, in the words read below, or the scenario is refused.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from wrapper.feeds import CoreFeeds, CoreRules, Feeds, OtherStations, SpaceWeather
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


def _stated(pattern, text, what):
    """The one match of pattern in a sealed feed detail's text; SealBroken unless the detail states it exactly once."""
    found = re.findall(pattern, text) if isinstance(text, str) else []
    if len(found) != 1:
        raise SealBroken(f"the sealed feed details do not state {what} as the harness reads it")
    return found.pop()


def _decimals(step):
    """The decimals of a rounding step written as 0.1, 0.01 and so on."""
    return len(step.split(".")[1])


def core_rules(feeds):
    """The core feeds' rules, CoreRules, read from a scenario's sealed feed details: the receiver's and the beacon's
    cadence (one, stated for each), the signal model and its rounding, the noise floor, the callsign, and the
    beacon's rounding of battery voltage and state of charge."""
    receiver, beacon = feeds["station_receiver"], feeds["beacon"]
    every_s = int(_stated(r"\ba multiple of (\d+)\b", receiver["reports"], "the receiver's cadence"))
    if int(_stated(r"\ba multiple of (\d+)\b", beacon["at"], "the beacon's cadence")) != every_s:
        raise SealBroken("the sealed feed details give the receiver and the beacon different cadences")
    reference_dbm, db_per_decade, reference_km = _stated(
        r"^(-?\d+\.\d+) \+ (\d+(?:\.\d+)?) log10\((\d+(?:\.\d+)?) km / slant range\)",
        receiver["signal_level_dbm"], "the signal model")
    return CoreRules(
        every_s=every_s, reference_dbm=float(reference_dbm), reference_km=float(reference_km),
        db_per_decade=float(db_per_decade),
        level_decimals=_decimals(_stated(r"^a number, to (0\.0*1) dB$", receiver["content"]["signal_level_dbm"],
                                         "the signal level's rounding")),
        noise_floor_dbm=float(_stated(r"(-?\d+\.\d+), the noise floor", receiver["signal_level_dbm"],
                                      "the noise floor")),
        callsign=beacon["content"]["callsign"],
        battery_v_decimals=_decimals(_stated(r"^to (0\.0*1) V$", beacon["content"]["battery_v"],
                                             "the battery voltage's rounding")),
        soc_pct_step=int(_stated(r"^to the nearest (\d+) %$", beacon["content"]["soc_pct"],
                                 "the state of charge's rounding")))


def draw_rule(feeds):
    """The stand-in stations' draw rule, read from a scenario's sealed feed details: {seed, stations, heard_p,
    delay_s}, as wrapper.feeds.draw_schedule takes them."""
    others = feeds["other_stations"]
    heard_p, low, high = _stated(r"random\(\) < (0\.\d+), then, if heard, randint\((\d+), (\d+)\)",
                                 others["draws"], "the stand-in stations' draws")
    return {"seed": others["seed"], "stations": list(others["stations"]), "heard_p": float(heard_p),
            "delay_s": (int(low), int(high))}


def space_weather_every_s(feeds):
    """The space weather's cadence, read from a scenario's sealed feed details."""
    return int(_stated(r"^each MET that is a multiple of (\d+)\b", feeds["space_weather"]["at"],
                       "the space weather's cadence"))


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
    replay: dict = None   # the sealed space-weather replay its feeds name (S9, piece 8)

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

    @property
    def latch_up(self):
        """The scripted latch-up (S9, piece 6), {onset_met_s, damage_after_s}, as the simulator takes it; None for a
        scenario without one."""
        latch = self.script.get("latch_up")
        return {"onset_met_s": latch["onset_met_s"], "damage_after_s": latch["damage"]["after_s"]} if latch else None

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

    @property
    def core_rules(self):
        """The core feeds' rules, read from the sealed feed details."""
        return core_rules(self.feeds)

    @property
    def draw_rule(self):
        """The stand-in stations' draw rule, read from the sealed feed details."""
        return draw_rule(self.feeds)

    def beacon_mets(self):
        """Each MET a beacon goes out in the own station's contact windows, at the core feeds' cadence, in order: the
        beacons the stand-in stations' schedule is drawn for."""
        every = self.core_rules.every_s
        return [met for aos, los in self.windows for met in range(-(-aos // every) * every, los, every)]

    def all_feeds(self):
        """The run's four outside feeds, as harness.run.Run takes them (S9, pieces 2, 7 and 8): the core feeds, the
        stand-in stations' logs by the scenario's sealed schedule, and the space weather replayed from its sealed
        replay file, each delivered in contact only, every rule read from the sealed feed details."""
        in_contact = lambda met_s: in_window(met_s, self.windows)   # noqa: E731
        return Feeds(self.core_feeds(),
                     OtherStations(self.feeds["other_stations"]["schedule"], in_contact=in_contact,
                                   rules=self.core_rules),
                     SpaceWeather(self.replay, every_s=space_weather_every_s(self.feeds),
                                  sources=self.feeds["space_weather"]["content"]["sources"], in_contact=in_contact))

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
                         slant_range_km=lambda met_s: orbit.look_angles_at(met_s + offset_s)[2], rules=self.core_rules)


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
                               geometry=document["geometry"], replay=self.replay(document["feeds"]))

    def replay(self, feeds):
        """The space-weather replay a scenario's feeds name, read from the sealed files; None when they name none."""
        name = (feeds.get("space_weather") or {}).get("replay")
        if name is None:
            return None
        if name not in self.files:
            raise SealBroken(f"the feeds name the replay {name}, which is not sealed")
        return json.loads(self.files[name])
