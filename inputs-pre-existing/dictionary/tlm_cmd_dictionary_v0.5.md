# HUGINN: CubeSat Mission Operations Simulator
## Telemetry & Command Dictionary, v0.5

**Status:** v0.5, HUG-G001-16 fix revision per Director disposition 2026-07-29 (accept/product, G001-16 F-02): note 2 now distinguishes the two overcharge-protection layers — charge taper as the modeled design protection, and the EPS_BATT_V voltage-high alarm (YH 8.3 V / RH 8.5 V) as the operational alarm receiving the generic contingency response (CONOPS §4.4); only a dedicated procedure step is absent in v0.1. All limit values and previously ratified content unchanged. Prior revision v0.4, HUG-G001 fix revision per owner dispositions of Sol findings 2026-07-25 (accept/product): F-04 → CMD_SYS_RESET counter-epoch acknowledgement defined; F-05 → command accounting bound to the HUG-CMD-007 contract (ledger item 6). This markdown file is the drafting surface; before build, definitions move to `defs/tlm_cmd.yaml` as the single source, from which both the OpenC3 configuration (`tools/gen_openc3_config.py`) and this document (`tools/gen_dictionary.py`) are generated. After that point, editing this file directly is prohibited.

**Limit provenance rule:** limits are authoritative within the simulation and derive from the EPS design envelope defined in this project. Any value borrowed from a public CubeSat reference is cited inline.

---

## 1. Telemetry (16 points, nominal 1 Hz housekeeping frame)

### EPS

| Mnemonic | Description | Type | Units | Limits (RL / YL / YH / RH) |
|---|---|---|---|---|
| EPS_BATT_V | Battery voltage (2S Li-ion) | float | V | 6.8 / 7.2 / 8.3 / 8.5 |
| EPS_BATT_I | Battery current (+charge / −discharge) | float | A | −2.5 / −2.0 / 2.0 / 2.5 |
| EPS_BATT_SOC | Battery state of charge | float | % | 20 / 35 / n/a / n/a |
| EPS_SA1_I | Solar-array string 1 current | float | A | n/a (context-dependent; monitored, not alarmed) |
| EPS_SA2_I | Solar-array string 2 current | float | A | n/a (context-dependent; monitored, not alarmed) |
| EPS_BUS_V | Regulated bus voltage | float | V | 4.75 / 4.90 / 5.10 / 5.25 |
| EPS_LOAD_I | Total load current | float | A | n/a / n/a / 1.5 / 2.0 |
| EPS_MODE | EPS mode | enum {NOMINAL, LOW_POWER, SAFE} | n/a | state-based: SAFE annunciates |

### Environment / dynamics

| Mnemonic | Description | Type | Units | Limits |
|---|---|---|---|---|
| ADM_ECLIPSE | Illumination state | enum {SUNLIT, ECLIPSE} | n/a | none (context) |

### Payload

| Mnemonic | Description | Type | Units | Limits |
|---|---|---|---|---|
| PLD_STATE | Payload power state | enum {OFF, ON} | n/a | none |
| PLD_RATE | Payload sampling rate | float | Hz | valid range 0.1-10 |

### C&DH / commanding

| Mnemonic | Description | Type | Units | Limits |
|---|---|---|---|---|
| CDH_MET | Mission elapsed time | uint32 | s | none |
| CDH_FRAME_CNT | Telemetry frame counter | uint16 (wraps) | n/a | staleness: no advance for 10 s → YL; 30 s → RL (ground-computed derived check) |
| CDH_CMD_ACC_CNT | Commands accepted counter | uint16 | n/a | none |
| CDH_CMD_REJ_CNT | Commands rejected counter | uint16 | n/a | delta > 0 annunciates yellow |
| CDH_REJ_REASON | Last reject reason | enum {NONE, UNKNOWN_OPCODE, ARG_RANGE, MODE_INHIBIT} | n/a | none |

Notes:

1. Staleness on CDH_FRAME_CNT is a ground-side derived monitor (OpenC3 derived telemetry), since a halted counter cannot alarm itself. This is the detection path PROC-003 depends on.
2. SoC has no high limits. Overcharge protection has two distinct layers in v0.1 (G001-16 F-02): charge taper at full charge is the modeled design protection, and the EPS_BATT_V voltage-high alarm (YH 8.3 V / RH 8.5 V) is the operational alarm, whose response is the generic contingency path (CONOPS §4.4). The accepted v0.1 limitation is the absence of a dedicated battery-voltage-high procedure step (FMEA §8 item 5), not of alarm coverage.
3. Battery temperature is deliberately absent: thermal is excluded from v0.1 scope. It is the first candidate telemetry addition in v0.2.

## 2. Commands (5)

| Mnemonic | Arguments | Validation / inhibit rules | Nominal effect |
|---|---|---|---|
| CMD_PLD_SET_STATE | state: {OFF, ON} | ON rejected (MODE_INHIBIT) if EPS_MODE = SAFE or EPS_BATT_SOC < 40% | Switches payload load; PLD_STATE follows |
| CMD_PLD_SET_RATE | rate: float Hz | Rejected (ARG_RANGE) outside 0.1-10 Hz; rejected (MODE_INHIBIT) if PLD_STATE = OFF | Sets PLD_RATE |
| CMD_SAFE_ENTER | none | Always accepted (HUG-CMD-004); flagged hazardous in OpenC3 → two-step confirmation on the ground side | EPS_MODE → SAFE; payload shed |
| CMD_SYS_RESET | none | Flagged hazardous; two-step confirmation | Clears stale-telemetry fault; reinitializes command counters to zero and then applies its own acceptance, so the first post-reset frame reads CDH_CMD_ACC_CNT = 1 / CDH_CMD_REJ_CNT = 0 — that epoch IS the reset acknowledgement; preserves SoC (HUG-CMD-005) |
| CMD_MODE_SET | target: {NOMINAL, LOW_POWER} | Rejected (ARG_RANGE) for any other target (SAFE entry is CMD_SAFE_ENTER's function); rejected (MODE_INHIBIT) if EPS_BATT_SOC < 35% for NOMINAL or < 25% for LOW_POWER; flagged hazardous → two-step confirmation (HUG-CMD-006) | EPS_MODE → target. Transition to LOW_POWER sheds the payload load (consistent with HUG-EPS-003); transition to NOMINAL does not re-enable the payload (re-activation via CMD_PLD_SET_STATE, subject to its inhibits) |

Command accounting (contract per HUG-CMD-007): exactly-once — each received command increments exactly one of CDH_CMD_ACC_CNT / CDH_CMD_REJ_CNT by exactly one, with the increment and any commanded effect visible no later than the next housekeeping frame (≤ 1 s at the nominal rate). Rejections additionally set CDH_REJ_REASON. Operators verify effect by counter delta plus the affected telemetry point, per procedure steps. CMD_SYS_RESET is the sole exception to simple delta arithmetic: its acknowledgement is the post-reset counter epoch (ACC = 1, REJ = 0). No counter delta within 10 s of a verified send = the loss-of-commandability declaration threshold for PROC-003.

Mode-authority rule (FMEA REC-01 resolution): autonomous mode transitions are downward only (NOMINAL → LOW_POWER → SAFE, per HUG-EPS-003); every upward transition is a deliberate ground act via CMD_MODE_SET. The recovery floors (35%/25%) sit 5 points above the autonomous entry thresholds (30%/20%) so a commanded recovery cannot immediately re-trip the ladder.

## 3. Packet structure (v0.1)

One housekeeping packet, 1 Hz, all 16 points above, CCSDS-like framing kept minimal: sync marker, length, MET timestamp, points in dictionary order. Exact byte layout lives in `defs/tlm_cmd.yaml` once authored; this document never specifies bytes by hand.

## 4. Disposition ledger (all items resolved by owner, 2026-07-24)

1. Resolved: 2S battery configuration and all limits ratified as drafted. Build-time check retained as a verification item: each limit must catch its fault case (string failure eventually crosses the SoC yellow; stuck-on load crosses EPS_LOAD_I yellow before red).
2. Resolved: 16 points confirmed as the v0.1 set. Deliberately excluded until v0.2: battery temperature (thermal excluded), per-load current breakdown, ground-side uplink counters.
3. Resolved: staleness thresholds 10 s yellow / 30 s red, married to PROC-003 decision points.
4. Ground station named GS-RAVENSROOST (fictional single terminal, central Florida coordinates recorded in the repo).
5. Resolved (2026-07-25, FMEA v0.2 REC-01): CMD_MODE_SET added as the fifth command with the mode-authority rule above; recovery floors 35% (NOMINAL) / 25% (LOW_POWER) ratified with the FMEA disposition.
6. Resolved (2026-07-25, HUG-G001 F-04/F-05, owner: accept/product): CMD_SYS_RESET post-reset counter epoch (ACC=1/REJ=0) defined as the reset acknowledgement; command accounting bound to the HUG-CMD-007 exactly-once contract with ≤1-frame visibility and the 10 s PROC-003 threshold.
