# AR-002 — Stuck-on load, HUGINN, 2026-10-11

**Anomaly report.** One contact, one pass record. Opened on detection, responded within
the same contact, closed to the next gate with the spacecraft charging and the stuck load
still drawing.

| Field | Value |
|---|---|
| Id | AR-002 |
| Title | Stuck-on load — EPS_LOAD_I up 0.400 A, unsheddable |
| Opened | 2026-10-11T17:06:45Z, CDH_MET 900 |
| Status | **Open** — responded. Load back inside its limits; the stuck 2.0 W cannot be removed from the ground |
| Fault class | HUG-EPS-004(b), stuck-on load of 2.0 W |
| FMEA | FM-EPS-08 (the FMEA's fault-to-pass mapping and the scenario file; the campaign plan cites FM-EPS-02, see section 5) |
| Scenario | `sim/scenarios/P3_stuck_load.yaml`, fault at MET 900 |
| Contact | `2026-10-11-P3` · MET 800 → 1230 · 430 s · SUNLIT · one command · 427 frames received |
| Procedures | version 0.2, PROC-002-S02 as red-lined under D-017 |
| Operator | Dan Lee-Odinson |

---

## 1. Detection

The fault appeared 100 s into the contact, so the operator watched it arrive rather than
finding it established at acquisition.

```
MET 899   EPS_LOAD_I 1.400 A   EPS_BATT_I +1.3038 A   SoC 66.500 %   SUNLIT
MET 900   EPS_LOAD_I 1.800 A   EPS_BATT_I +1.0430 A   SoC 66.506 %   SUNLIT   YELLOW
```

`EPS_LOAD_I` crossed its 1.5 A yellow limit in a single frame and stopped at 1.800 A, short
of the 2.0 A red. **Yellow came before red**, which is the ordering the dictionary's
disposition ledger asserts for a stuck load, observed here on live telemetry.

Both array strings read 1.70 A throughout. The fault is in the load, and nothing about
generation looked wrong.

**The spacecraft stayed energy-positive.** The stuck load cost 0.26 A of charge current and
the battery kept charging. Against the pass plan, the fault-free mission, at the plan's own
sample times:

| MET | Actual SoC | Planned SoC | Difference |
|---:|---:|---:|---:|
| 890 | 66.438 % | 66.438 % | 0.000 pp, before the fault |
| 920 | 66.617 % | 66.646 % | −0.029 pp |
| 950 | 66.783 % | 66.854 % | −0.071 pp |

## 2. Response

PROC-001-S07 took the limit-response branch on load current, the first time in the
campaign. In PROC-002 the operator confirmed the point (S01), routed the load alarm to S03
(S02, under D-017), and identified a load excursion from symmetric strings and a load
above 1.5 A (S03).

| | MET 958 | MET 959 |
|---|---|---|
| `PLD_STATE` | ON | **OFF** |
| `CDH_CMD_ACC_CNT` | 1 | **2** |
| `CDH_CMD_REJ_CNT` | 0 | **0** |
| `EPS_LOAD_I` | 1.800 A | **1.200 A** |
| `EPS_BATT_I` | +1.0424 A | **+1.4333 A** |

The command left the ground at **17:07:43.660450Z**. The frame carrying its effect arrived
at **17:07:44.128422Z**, 468 ms later and inside the one-frame contract. The telemetry
extract and the ground command log agree; the log records exactly one command for the
contact.

## 3. What the shed could and could not do

**The load fell by exactly the payload's 0.600 A.** It fell to 1.200 A, which is below the
yellow limit, so the annunciation cleared 59 s after it appeared.

It did not fall to the 0.800 A a payload-off spacecraft draws. **The remaining 0.400 A is
the stuck load**, 2.0 W on the 5.0 V bus, and no ground command removes it.

With the payload off, the spacecraft draws 1.0 W less than the pass plan, which keeps the
payload on. State of charge therefore finished the contact **above** plan:

| MET | Actual SoC | Planned SoC | Difference |
|---:|---:|---:|---:|
| 1110 | 67.989 % | 67.965 % | +0.024 pp |
| 1229 | 68.898 % | 68.792 % | +0.106 pp |

PROC-002-S06 selected `recovered`: `EPS_BATT_I` stayed between +1.428 and +1.433 A for all
271 frames after the shed. EPS_MODE read NOMINAL for the whole contact.

Turning the payload back on would add its 0.600 A to the stuck load and return
`EPS_LOAD_I` to 1.800 A, over its yellow limit again.

## 4. Outcome

**Responded.** The commanded shed was sent, verified by counter and by point, and brought
the load back inside its limits. The spacecraft was handed over at **SoC 68.898 %, EPS_MODE
NOMINAL, charging**, with the payload off and the stuck 2.0 W still drawing.

## 5. Findings raised by this anomaly

1. **PROC-002-S06 expects the stuck load to arrive still negative.** It did not. Already
   recorded as OF-023, which this pass confirms on flown data.

2. **The campaign plan's PASS-3 section cites the wrong FMEA row and the wrong expected
   trend.** It names FM-EPS-02, total array output loss, where the FMEA's own fault-to-pass
   mapping, the scenario file and `defs/eps.yaml` all name FM-EPS-08, stuck-on load. It also
   tells the operator to expect `EPS_BATT_SOC` falling faster than the pass plan predicted.
   State of charge rose throughout the contact, a little slower than plan before the shed
   and faster after it. Registered as OF-024.

## 6. Evidence

| Artifact | What it is |
|---|---|
| `docs/pass_reports/2026-10-11-P3/report.yaml` | the pass record, validator `[PASS]` |
| `docs/pass_reports/2026-10-11-P3/pass_plan.md` | the predicted, fault-free contact |
| `docs/pass_reports/2026-10-11-P3/pass_setup.md` | pre-pass verification, GO |
| `docs/pass_reports/2026-10-11-P3/telemetry_hk.csv` | 427 frames, MET 803–1229, no gaps |
| `docs/pass_reports/2026-10-11-P3/commands.csv` | exactly one command, the shed |

**Frames received versus sent.** The contact transmitted 430 frames and the ground received
427. The simulator began transmitting before COSMOS completed its connection, so MET 800 to
802 never reached the ground. `CDH_FRAME_CNT` and `RECEIVED_COUNT` both run unbroken through
the extract, so this is acquisition latency, the same as on 2026-09-13-P1 and both PASS-2
contacts, and not data loss in the pass.

## 7. Status

**Open.** Responded. Carried to the next gate with finding 2 above, and with the
spacecraft, at last contact, charging in sunlight with its payload shed and an unsheddable
2.0 W load still on the bus.
