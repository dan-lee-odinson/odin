# AR-003 — Housekeeping generation halt, HUGINN, 2026-10-11

**Anomaly report.** One contact, one pass record. Detected on the staleness alarm and
responded to under PROC-003 within the same contact. Telemetry was restored by the
scenario's scripted reset, 21.1 s before the operator's reset left the ground.

| Field | Value |
|---|---|
| Id | AR-003 |
| Title | Housekeeping generation halt — 120 s without frames on a connected link |
| Opened | 2026-10-11T20:04:11.899Z, the YELLOW staleness annunciation |
| Status | **Open** — recovered. Telemetry restored at MET 1320 and held to LOS; findings in section 5 |
| Fault class | HUG-EPS-004(c), housekeeping telemetry generation halt, latched until CMD_SYS_RESET |
| FMEA | FM-CDH-01 |
| Scenario | `sim/scenarios/P4_hk_generation_halt.yaml`, halt at MET 1200, scripted CMD_SYS_RESET at MET 1320 |
| Contact | `2026-10-11-P4` · MET 1100 → 1530 · 430 s · SUNLIT · one command · 308 frames received |
| Procedures | version 0.3, PROC-003 entered on the annunciation under D-018 ruling 2 |
| Operator | Dan Lee-Odinson |

---

## 1. Detection

The halt came 100 s into the contact. The counter froze, and the ground-side monitor
alarmed on schedule:

```
20:04:01.293Z   MET 1199   CDH_FRAME_CNT 1200   SoC 73.583 %   last frame before the halt
20:04:11.899Z              staleness YELLOW                      10.6 s after it
20:04:31.918Z              staleness RED                         30.6 s after it
20:06:02.682Z   MET 1320   CDH_FRAME_CNT 1201   SoC 74.424 %   first frame after the halt
20:06:03.020Z              staleness GREEN
```

**Yellow came before red, and neither NO_READ nor READ_FAULT was announced**, which is what
the campaign plan says the operator should see. `HUGINN_INT` read CONNECTED throughout, with
its received count frozen at 152: a halt on a live link, not a link drop.

The operator saw the counter frozen in Packet Viewer from 20:04:05Z and saw the YELLOW line
before RED appeared.

## 2. Response

PROC-003 was entered on the annunciation (D-018 ruling 2). The operator recorded the last
frame and the level (S01), determined spacecraft-side from the connected interface and its
frozen received count across 60 s of screens (S02), and sent CMD_SYS_RESET under the
two-step confirmation (S03).

| | |
|---|---|
| Command Sender opened on | `CMD_MODE_SET`, held from an earlier session; changed to `CMD_SYS_RESET` by 20:06:05Z |
| `CMD_SYS_RESET` left the ground | 20:06:23.790611Z, logged by CmdTlmServer as `cmd_no_hazardous_check` |
| Simulator | accepted at its next tick, MET 1342; "1 commands uplinked" |

After the reset the operator verified the counter epoch (S04), saw frames counting and the
annunciator GREEN (S05), and returned to PROC-001 at S06.

## 3. The scripted reset arrived first

D-018 ruling 3 kept the scenario's own CMD_SYS_RESET at MET 1320, so that the spacecraft
recovers without the operator if his reset is late. It restored telemetry at
20:06:02.682Z, **21.1 s before the operator's reset left the ground**. The operator had not
noticed the frames return; he was working in Command Sender.

| Interval | Seconds |
|---|---:|
| YELLOW to the scripted reset's first frame | 110.8 |
| YELLOW to the operator's send | 131.9 |

The operator's account, in his words: "I fell behind schedule just trying to read the
instructions in real time."

The reset's epoch check could not tell the two resets apart, or either from no reset.
`CDH_CMD_ACC_CNT` read 1 and `CDH_CMD_REJ_CNT` read 0 in every frame of the contact, as
OF-028 predicted. The operator's reset is evidenced by the ground command log and the
simulator's uplink count, and the scripted one by frames resuming.

## 4. Outcome

**Recovered.** Telemetry resumed at MET 1320 and held to LOS. The 120 frames for MET 1200
to 1319 were never generated, and the gap is preserved in `telemetry_hk.csv` rather than
filled.

**The halt cost no power.** State of charge matched the pass plan to within 0.001
percentage point at every 30 s sample received:

| MET | Actual SoC | Planned SoC |
|---:|---:|---:|
| 1190 | 73.521 % | 73.521 % |
| 1340 | 74.562 % | 74.563 % |
| 1460 | 75.396 % | 75.396 % |
| 1529 | 75.875 % | 75.875 % |

The spacecraft was handed over at **SoC 75.875 %, EPS_MODE NOMINAL, charging**, payload ON.

## 5. Findings raised by this anomaly

1. **The in-pass instructions cost the race against the scripted reset.** They were a
   736-word step list, two pages long, kept open beside the console. The operator's
   account is in section 3. The instructions are an operator aid outside the repository.
   Registered as OF-029 (D-019).

2. **Command Sender reopened on a hazardous packet.** It held `CMD_MODE_SET` from an
   earlier session, the packet sent by mistake on `2026-08-03-P1` (ANOM-001). The operator
   caught it this time, with the clock running. Registered as OF-030 (D-019).

3. **Command Sender shows two hazardous commands' descriptions as raw bytes.** The
   descriptions of `CMD_SYS_RESET` and `CMD_MODE_SET` displayed as
   `{"json_class":"String","raw":[...]}` arrays of numbers. The generated `cmd.txt`
   descriptions of both, and of `CMD_SAFE_ENTER`, contain non-ASCII characters, an em dash
   and a right arrow. The HK packet's description is plain ASCII and displays as text.
   Registered as OF-031 (D-019).

4. **OF-028 confirmed on flown data.** The post-reset epoch matched the counters before the
   halt, and this pass had two resets, both invisible to the epoch check.

5. **Two record keys name times the step no longer runs at.** D-018 ruling 2 returns the
   operator to PROC-001-S06 after PROC-003, so S06's `*_at_aos2` values were taken 357 s
   after AOS. S15 was taken 13 s before LOS against its LOS minus 2 minutes. Registered
   as OF-032 (D-019).

6. **PROC-003-S10 says the anomaly report is part of the pass report, not a separate
   document.** The campaign files its anomaly reports separately, as AR-001 and AR-002. This
   pass does both: a summary under `anomalies:` in the report, and this document. Registered
   as OF-033 (D-019).

## 6. Evidence

| Artifact | What it is |
|---|---|
| `docs/pass_reports/2026-10-11-P4/report.yaml` | the pass record, validator `[PASS]` |
| `docs/pass_reports/2026-10-11-P4/pass_plan.md` | the predicted, fault-free contact |
| `docs/pass_reports/2026-10-11-P4/pass_setup.md` | pre-pass verification, GO |
| `docs/pass_reports/2026-10-11-P4/telemetry_hk.csv` | 308 frames, MET 1102–1199 and 1320–1529 |
| `docs/pass_reports/2026-10-11-P4/commands.csv` | exactly one command, `CMD_SYS_RESET` |

**Frames received versus sent.** The simulator sent 310 frames and suppressed 120 under the
fault. The ground received 308: MET 1100 and 1101 were sent before COSMOS completed its
connection at 20:02:23.607Z, as on 2026-09-13-P1, both PASS-2 contacts and PASS-3. `RECEIVED_COUNT` and
`CDH_FRAME_CNT` both run unbroken through the extract. The counter does not advance while
generation is halted, so the halt shows only as the 120 s gap in `CDH_MET`.

The operator's screen recording, 127 captures at 5 s with timestamped notes, is in the
operations archive outside the repository.

## 7. Status

**Open.** Recovered. Carried to the next gate with findings 1, 2, 3, 5 and 6.
