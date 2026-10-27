# AR-001 — Array-string loss, HUGINN, 2026-09-20

**Anomaly report.** Spans two contacts and two pass records. Opened on detection,
carried through response, closed to the next gate with the spacecraft energy-negative.

> **Naming note for the Director.** `ANOM-nnn` is already in use inside pass reports for
> *procedure omissions* (ANOM-001 on `2026-08-03-P1`, ANOM-002 inside `2026-09-20-P2b`).
> A spacecraft anomaly is a different kind of record and needs its own series, so this
> file uses `AR-` provisionally. Rename it if you want a different prefix — real programs
> use SOAR, DR, PR and ISA for this artefact and none of them is universal.

| Field | Value |
|---|---|
| Id | AR-001 |
| Title | Array-string loss — EPS_SA1_I to zero, string 1 |
| Opened | 2026-09-20T21:44:59Z, contact A |
| Status | **Open** — responded, not resolved. Spacecraft handed over still energy-negative |
| Fault class | HUG-EPS-004(a), single array-string output forced to zero |
| FMEA | FM-EPS-01 |
| Scenario | `sim/scenarios/P2_array_string_loss.yaml`, fault at MET 600 |
| Contacts | `2026-09-20-P2a` (detection), `2026-09-20-P2b` (response) |
| Operator | Dan Lee-Odinson |

---

## 1. Why this record exists separately from the pass reports

D-015 ruled that a pass may span two contacts. The Director ruled on 2026-09-20 that
such a pass is **filed as two pass records threaded by one anomaly record**, following
the practice that a pass report describes one acquisition while an anomaly record spans
however many contacts the investigation takes.

This is that record. Neither pass report tells the whole story; this one does.

## 2. Contact A — detection

`2026-09-20-P2a` · MET 2190 → 2520 · 330 s · SUNLIT · uncommanded · 329 frames received

The fault was already established at acquisition, having been injected at MET 600, 1590 s
before the contact opened. The operator arrived to a standing condition rather than
watching a collapse, which is the ordinary case in flight.

```
EPS_SA1_I   0.00 A        for all 329 frames
EPS_SA2_I   1.70 A        for all 329 frames
EPS_BATT_SOC   61.075 → 61.417 %   RISING
EPS_BATT_I     +0.197 A            CHARGING
EPS_MODE  NOMINAL    ADM_ECLIPSE  SUNLIT    no limit of any colour
```

**The asymmetry is unmistakable and no procedure step catches it.** PROC-001-S07 checks
four alarmed limits — state of charge, battery voltage, load current, mode — and every
one of them reads nominal, correctly. State of charge is *rising*, because one surviving
string at 1.70 A exceeds the 1.40 A load while sunlit.

The operator therefore detected a dead solar string and had no procedural authority to
act on it. PROC-001-S07 was recorded `nominal`, knowingly, with the asymmetry stated in
its observation field. This is OF-017 demonstrated on recorded data.

The command extract over contact A's window returned **no rows**, confirming an
uncommanded contact.

## 3. Between contacts

Roughly 19,300 seconds of mission — about five and a half hours — passed unobserved. The
spacecraft entered eclipse at MET 20940 and the state of charge fell from 61.4% to 35.5%
with one string generating nothing.

## 4. Contact B — response

`2026-09-20-P2b` · MET 21800 → 22230 · 430 s · ECLIPSE · one command · 428 frames received

```
AOS         MET 21800   SoC 35.492 %   both strings 0.00 A
+94 s       MET 21894   SoC 34.996 %   EPS_BATT_SOC crosses 35 % — YELLOW
+120 s      MET 21920   SoC 34.856 %   PROC-001-S07 → limit response required → PROC-002
+206 s      MET 22006                  CMD_PLD_SET_STATE state OFF sent
LOS         MET 22229   SoC 33.709 %   still discharging, EPS_MODE NOMINAL
```

**Eclipse hides the fault's own signature.** Both string currents read 0.00 A for all 428
frames, so PROC-002-S03 — which identifies the cause by comparing the two strings — is
unanswerable from this contact alone. It was answered from contact A's observation, under
the Director's cross-contact ruling of 2026-09-20.

That is the operational justification for the two-contact pattern. It is not a scheduling
convenience: **no single 430 s window anywhere in this 23,040 s scenario contains both the
asymmetry and the limit crossing**, because the asymmetry is visible only in sunlight and
the limit is reached only in eclipse.

### The commanded response

| | MET 22005 | MET 22006 |
|---|---|---|
| `PLD_STATE` | ON | **OFF** |
| `CDH_CMD_ACC_CNT` | 1 | **2** |
| `CDH_CMD_REJ_CNT` | 0 | **0** |
| `EPS_LOAD_I` | 1.400 A | **0.800 A** |
| `EPS_BATT_I` | −0.9631 A | **−0.5504 A** |

Command left the ground at **22:09:51.046687Z**; the frame carrying its effect arrived at
**22:09:51.103693Z** — **57 ms**, against a contract allowing one second. Attested
independently by the telemetry extract and by the ground command log, which records
exactly one command for the contact.

Discharge cut by **43%**.

## 5. Outcome — responded, not resolved

The shed slowed the discharge and could not reverse it. In eclipse both strings generate
nothing, so no load reduction can make generation exceed load. `EPS_BATT_I` held at
−0.55 A to loss of signal and PROC-002-S06 was recorded `still negative`.

The spacecraft was handed over at **SoC 33.709%, EPS_MODE NOMINAL, still energy-negative**,
to a contact that does not exist in this mission.

**Generation cannot be restored from the ground.** The string is dead; the only response
available was load management, and it has been taken.

## 6. Findings raised by this anomaly

Four, none of them previously in the register. All want entries of their own.

1. **The campaign plan records PASS-2 as `Commanded: no`** and justifies its contact on
   not needing commanding margin. PROC-002-S04 commands a shed whenever S03 selects
   array-string failure, which is exactly what this pass is built to produce. The pass is
   commanded. The plan is wrong. Registered as OF-019.

2. **PROC-002-S02's branch criteria are both unreachable in this scenario.** It selects
   `negative beyond eclipse` on discharging-while-sunlit (physically impossible here — the
   surviving string carries 1.70 A against a 1.40 A load, so the battery charges whenever
   sunlit) or on discharge deeper than the eclipse plan predicts (no predicted profile
   exists anywhere in the build; `pass_setup.py` produces configuration verification only).
   Registered as OF-021.

3. **No predicted state-of-charge profile exists for any contact.** The only predicted
   value the build produces is the scenario's initial state of charge at MET 0, which is
   what both pass records carry in `predicted_soc_pct`. The `soc_delta_vs_plan_pct` fields
   in both records are therefore artefacts of comparing two different mission times, not
   variances. This makes PROC-002-S02's second criterion unusable and PROC-001-S06's delta
   meaningless. Registered as OF-020.

4. **No pass in the v0.1 campaign ever fires the autonomous mode ladder.** Measured:

   | Scenario | Lowest state of charge | Mode ladder |
   |---|---|---|
   | `P2_array_string_loss`, as flown | 31.216 % | never actuates |
   | `P2_array_string_loss`, had no shed been sent | 29.330 % | LOW_POWER at MET 22822 |
   | `P3_stuck_load` | 60.009 % | never actuates |
   | `P4_hk_generation_halt` | 65.009 % | never actuates |

   LOW_POWER at 30% and SAFE at 20% are specified by HUG-EPS-003, asserted in the
   dictionary's disposition ledger, and depended on by PROC-002-S07, S08, S09 and S10.
   Nothing in the campaign demonstrates any of it. Registered as OF-022.

   Note the second row. **The operator's correct response is what removed the condition.**
   Had the shed not been sent, the ladder would have fired at MET 22822. Shedding the
   payload kept the battery above 30% for the rest of the mission — so the steps that
   exist to record the ladder became permanently uncompletable *because the response
   worked*. That is why ANOM-002 inside `2026-09-20-P2b` disposes by owner risk
   acceptance rather than re-execution: there is no pass in v0.1 to re-execute on.

## 7. Evidence

| Artefact | What it is |
|---|---|
| `docs/pass_reports/2026-09-20-P2a/report.yaml` | contact A record, validator `[PASS]` |
| `docs/pass_reports/2026-09-20-P2a/telemetry_hk.csv` | 329 frames, MET 2191–2519, no gaps |
| `docs/pass_reports/2026-09-20-P2a/pass_setup.md` | pre-pass verification, GO |
| `docs/pass_reports/2026-09-20-P2b/report.yaml` | contact B record, validator `[PASS]` |
| `docs/pass_reports/2026-09-20-P2b/telemetry_hk.csv` | 428 frames, MET 21802–22229, no gaps |
| `docs/pass_reports/2026-09-20-P2b/commands.csv` | exactly one command, the shed |
| `docs/pass_reports/2026-09-20-P2b/pass_setup.md` | pre-pass verification, GO |

Contact A's command extract returned no rows and produced no file. The absence is stated
in that pass record rather than represented by an empty artefact, because a file created
by hand is not evidence of anything.

**Frames received versus sent.** Contact A transmitted 330 and the ground received 329;
contact B transmitted 430 and received 428. In both cases the simulator began transmitting
a fraction of a second before COSMOS completed its TCP connection. `RECEIVED_COUNT` runs
unbroken 10001 → 10757 across both contacts and neither extract has an internal gap, so
this is acquisition latency rather than data loss in the pass.

## 8. Status

**Open.** Responded, not resolved. Carried to the next gate with findings 1 through 4
above, and with the spacecraft, at last contact, discharging in eclipse on one solar
string with its payload shed.
