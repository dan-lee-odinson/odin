"""The simulator in a run: HUGINN's spacecraft, stepped one tick at a time, with the link to COSMOS, the
onboard tap and the truth file beside it (CONTRACT.md §3, §6.4, §9.3, §12).

Each tick, as HUGINN's tools/serve_sim.py does it: the commands that reached the spacecraft since the
last tick are applied at the tick boundary, then HUGINN steps once and generates its frame, or none
while the housekeeping halt is latched. The frame is packed by HUGINN's codec and the same bytes go
down the link to COSMOS and to the onboard tap, so both seats read identical values.

Commands reach the spacecraft two ways: up the link from COSMOS, in the ground seat, and straight to
the C&DH from BALDUR-0's UPLINK route, in the onboard seat (§9.3), which no contact window gates.
HUGINN's scenario files script commands of their own too. Those outside every contact window of the
run are kept and those inside one are dropped, so that every command during a pass is ODIN's (the
Director's ruling on U35, 27 October 2026).

Every tick from the start of the run also writes the model's true state to the truth file, which ODIN
never reads (§12), with each fault's onset and each scripted command dropped.
"""

import dataclasses
import threading
from collections import deque

from wrapper import frames
from wrapper.huginn import DICTIONARY, CommandCodec, Scenario, build
from wrapper.link import in_window


def split_scripted_commands(scenario, windows):
    """(kept, dropped): the scenario with only the scripted commands that fall outside every contact
    window, and the commands that fall inside one, oldest first, as HUGINN reads them. The split is
    made in memory; HUGINN's files are unchanged.

    The commands kept stand for what was commanded before the pass. Every phase-2 scenario but P1
    switches the payload ON at MET 120, before its contact, and P2, P3 and P4 depend on it: P3's stuck
    load crosses the 1.5 A alarm only because the payload already draws 0.6 A."""
    kept = [c for c in scenario.data.get("commands", []) if not in_window(int(c["t_s"]), windows)]
    dropped = [c for c in scenario.commands if in_window(c["t_s"], windows)]
    return Scenario(dict(scenario.data, commands=kept), scenario.path), dropped


class OnboardTap:
    """Every frame the spacecraft generates, read beside the simulator for the onboard seat (§6.4): no
    contact window or ground receiver stands between them. A housekeeping halt still leaves it with
    no new frame, since none is generated."""

    def __init__(self):
        self._lock = threading.Lock()
        self._frames = []

    def receive(self, raw):
        frame = frames.decode_frame(raw)
        with self._lock:
            self._frames.append(frame)

    def latest(self):
        """The newest decoded frame, or None before the first."""
        with self._lock:
            return self._frames[-1] if self._frames else None

    def history(self, since_met_s=None):
        """Every decoded frame, oldest first, or those stamped at or after since_met_s."""
        with self._lock:
            return [f for f in self._frames if since_met_s is None or f["CDH_MET"] >= since_met_s]


class Simulator:
    def __init__(self, scenario, *, windows, link=None, truth=None, start_at=0, latch_up=None):
        """scenario: a HUGINN Scenario (wrapper.huginn.load_scenario). windows: the run's contact
        windows as (aos_met_s, los_met_s), each half-open; the scenario's scripted commands inside them
        are dropped. link: the Link to COSMOS, or None. truth: the run's TruthLog, or None. start_at:
        the MET the run starts at; HUGINN steps to it first and nothing is carried before it, as
        serve_sim.py's --start-at does. latch_up: phase 3's scripted latch-up, {onset_met_s,
        damage_after_s} (S9, piece 6; _latch_up_tick)."""
        self.windows = sorted((aos, los) for aos, los in windows)
        scenario, self.dropped = split_scripted_commands(scenario, self.windows)
        self.spacecraft = build(scenario)
        self.latch_up = dict(latch_up, state="WAITING", damaged=False) if latch_up else None
        self._latch_events = []
        if self.latch_up:
            # HUGINN builds each tick's faults from the scenario alone; the latch-up adds its own stuck-load term
            # to them while it lasts, through this spacecraft's call, and HUGINN's code is unchanged.
            from_scenario = self.spacecraft._faults_now
            self.spacecraft._faults_now = lambda: self._with_latch_up(from_scenario())
        self.scenario = scenario
        self.link = link
        self.truth = truth
        self.tap = OnboardTap()
        self._codec = CommandCodec(DICTIONARY)
        self._onboard = deque()
        self._lock = threading.Lock()
        while self.spacecraft.t_s < start_at:
            self.spacecraft.step()
        self.start_met_s = int(self.spacecraft.t_s)
        # The MET of the newest tick. Before the first tick of the run it is the start, so a frame
        # stamped at the start is no older than the clock.
        self.met_s = self.start_met_s
        self.applied = []
        # Faults and dropped commands the pre-roll passed through are written with the first tick, when
        # the run's clock runs.
        self._passed = scenario.faults_active_at(self.spacecraft.t_s - self.spacecraft.dt)
        self._passed_commands = [c for c in self.dropped if c["t_s"] < self.spacecraft.t_s]

    def uplink(self, command, parameters):
        """BALDUR-0's UPLINK route in the onboard seat: the command reaches the C&DH at the next tick."""
        with self._lock:
            self._onboard.append(frames.encode_command(command, parameters))

    def step(self):
        """One tick. Returns the frame HUGINN generated, or None during a housekeeping halt."""
        craft = self.spacecraft
        met_s = int(craft.t_s)
        with self._lock:
            onboard, self._onboard = list(self._onboard), deque()
        arrived = (self.link.take_commands(met_s) if self.link else []) + onboard
        for raw in arrived:
            self.applied.append((met_s, *self._apply(raw)))
        if self.latch_up:
            self._latch_up_tick(met_s)
        onsets = [fault for fault in craft.scenario.faults if fault["t_s"] == craft.t_s]
        withheld = [command for command in self.dropped if command["t_s"] == craft.t_s]
        frame = craft.step()
        self.met_s = met_s
        raw = frames.CODEC.encode(frame) if frame is not None else None
        downlink = None
        if raw is not None:
            self.tap.receive(raw)
            if self.link is not None:
                downlink = self.link.downlink(raw, met_s)
        if self.truth is not None:
            for fault in self._passed:
                self._fault_onset(fault, before_start=True)
            for command in self._passed_commands:
                self._command_dropped(command, before_start=True)
            self._passed, self._passed_commands = [], []
            # In HUGINN's order within a tick: fault onsets, then scripted commands, then the state.
            for fault in onsets:
                self._fault_onset(fault, before_start=False)
            for command in withheld:
                self._command_dropped(command, before_start=False)
            for event in self._latch_events:
                self.truth.append("LATCH_UP", {"event": event, "onset_met_s": self.latch_up["onset_met_s"],
                                               "damage_met_s": self.latch_up["onset_met_s"]
                                               + self.latch_up["damage_after_s"], "source": "SCRIPT"})
            self._true_state(frame is not None, downlink)
        self._latch_events = []
        return frame

    def _with_latch_up(self, faults):
        return dataclasses.replace(faults, stuck_load=True) if self.latch_up["state"] == "ACTIVE" else faults

    def _latch_up_tick(self, met_s):
        """Phase 3's latch-up (S9, piece 6; the Director's approved phase-3 document, scenario C), after the
        tick's commands are applied. At onset, with the payload ON, HUGINN's own stuck-load term is set, its EPS
        definitions' power, the same step as PASS-3's stuck load, and it stays set until PLD_STATE turns OFF; the
        load then falls back to its base, and turning the payload on again does not bring it back. With the
        payload already OFF at onset there is no latch-up. If the payload is still ON damage_after_s of
        simulation time after onset, it is damaged; the simulator models no damaged payload afterwards. The truth
        file records each event, LATCH_UP: ONSET or NOT_EXERCISED, CLEARED, DAMAGED."""
        latch, payload_on = self.latch_up, self.spacecraft.eps.state.payload_on
        if latch["state"] == "WAITING" and met_s >= latch["onset_met_s"]:
            latch["state"] = "ACTIVE" if payload_on else "NOT_EXERCISED"
            self._latch_events.append("ONSET" if payload_on else "NOT_EXERCISED")
        elif latch["state"] == "ACTIVE" and not payload_on:
            latch["state"] = "CLEARED"
            self._latch_events.append("CLEARED")
        if latch["state"] == "ACTIVE" and not latch["damaged"] \
                and met_s >= latch["onset_met_s"] + latch["damage_after_s"]:
            latch["damaged"] = True
            self._latch_events.append("DAMAGED")

    def _apply(self, raw):
        """A command's bytes to the C&DH, as serve_sim.py applies them: an opcode the dictionary does
        not define is still received, and accounted as UNKNOWN_OPCODE (HUGINN's HUG-CMD-001)."""
        mnemonic, args = self._codec.decode(raw)
        if mnemonic is None:
            opcode = int.from_bytes(raw[:2], "big") if len(raw) >= 2 else -1
            accepted, reason = self.spacecraft.cdh.receive_opcode(opcode)
            return f"opcode {opcode}", accepted, reason
        accepted, reason = self.spacecraft.cdh.receive(mnemonic, args)
        return mnemonic, accepted, reason

    # -- the truth file ------------------------------------------------------------------------

    # One TRUE_STATE record per tick from the start of the run, the model's values whether or not a
    # frame was generated, and one FAULT_ONSET per fault, those the pre-roll passed through included
    # (the Director's ruling on U36, 27 October 2026). One SCRIPTED_COMMAND_DROPPED per scripted
    # command dropped (U35). log/truth_record.schema.json holds the bodies.

    def _fault_onset(self, fault, *, before_start):
        self.truth.append("FAULT_ONSET", {"onset_met_s": fault["t_s"], "fault": fault["fault"],
                                          "string": fault["string"], "source": "SCENARIO",
                                          "before_start": before_start})

    def _command_dropped(self, command, *, before_start):
        aos, los = next(window for window in self.windows if in_window(command["t_s"], [window]))
        self.truth.append("SCRIPTED_COMMAND_DROPPED", {
            "scheduled_met_s": command["t_s"], "command": command["mnemonic"], "parameters": command["args"],
            "source": "SCENARIO", "contact_window": {"aos_met_s": aos, "los_met_s": los},
            "before_start": before_start})

    def _true_state(self, generated, downlink):
        self.truth.append("TRUE_STATE", {"frame_generated": generated, "downlink": downlink, **self.true_state()})

    def true_state(self):
        """The model's values now, as TRUE_STATE holds them: what phase 3's feeds are built from (S9)."""
        craft = self.spacecraft
        eps, cdh, state = craft.eps, craft.cdh, craft.eps.state
        return {
            "eps": {"soc_pct": eps.soc_pct, "energy_wh": state.energy_wh, "battery_v": eps.battery_voltage_v,
                    "battery_i": state.battery_current_a, "bus_v": eps.bus_v, "load_i": state.load_current_a,
                    "string_i": list(state.string_currents_a), "mode": state.mode,
                    "illuminated": state.illuminated, "payload_on": state.payload_on,
                    "pld_rate_hz": state.pld_rate_hz},
            "cdh": {"hk_halted": cdh.hk_halted, "frame_count": cdh.frame_count, "acc_count": cdh.acc_count,
                    "rej_count": cdh.rej_count, "rej_reason": cdh.rej_reason},
            "faults_active": [f["fault"] for f in craft.scenario.faults_active_at(craft.t_s - craft.dt)]
            + (["latch_up"] if self.latch_up and self.latch_up["state"] == "ACTIVE" else [])}
