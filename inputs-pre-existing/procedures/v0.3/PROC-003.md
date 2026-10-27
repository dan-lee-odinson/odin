# PROC-003 — Loss of telemetry or commandability

GENERATED FILE — DO NOT EDIT. Source: `defs/procedures.yaml`
Procedures version: 0.3 · Dictionary sha256: 5e1c2750ef9e0d54…

> Edit the source and regenerate. A hand edit here would make the document the
> operator follows differ from the procedure `tools/pass_report.py` reviews the
> completion record against — and post-pass review would then pass a pass in
> which a step was never executed and never noticed (HUG-OPS-002).

## Before you start

You do not need to know this program to run this procedure. Everything each
step needs is named in the step; this section names the things every step
assumes.

### The console — what to open

The ground system is OpenC3 COSMOS. Its console is a WEB PAGE, not a desktop
application: open **http://localhost:2910** in a browser. That page is "the ground
system" wherever these procedures say it.

Navigation is the **menu sidebar on the left**. Four tools there are used below:

| Tool | Use it to |
|---|---|
| Packet Viewer | Read the current value of a telemetry point. Target HUGINN, packet HK. |
| Telemetry Grapher | Watch a point over time. Use this wherever a step says trend. |
| Command Sender | Send a command. Target HUGINN. |
| CmdTlmServer | See the link and the staleness alarm. The Interfaces tab shows HUGINN_INT's state and its Tlm pkts, the ground's received count. The Log Messages list at the bottom carries the staleness monitor's lines: type staleness in its Search box, and the newest line is the current level. |

### The terminal

Commands shown as `python tools/...` are typed in a terminal. On Windows use
PowerShell or Git Bash. The terminal's working directory must be the repository
root - the folder containing `BUILD_HANDOFF.md`.

If `python` is not found, or a command fails on a missing module, see
`gnd/RUNBOOK.md` under "Operator environment" for which interpreter to use and how
to install what is missing. To check the environment before you need it:

```
python tools/check_deps.py --preflight
```

### The pass plan

**The pass plan and the campaign plan are the same document.** It is
`campaign/CAMPAIGN_PLAN.md`. The pass plan is the part of it that concerns the pass
you are flying: the PASS-n section, plus the row for that pass's contact in the
computed-week table.

If the file is not there, produce it:

```
python tools/gen_campaign.py
```

### The pass identifier

Every pass has an identifier of the form `YYYY-MM-DD-Pn` - the UTC date of the
contact, then the pass number from the campaign plan. The campaign's first pass is
`2026-07-29-P1`.

You do not invent it; you read it off the campaign plan. Use the same string in
three places: the `pass_setup` command, the report directory name, and the
`pass_id:` field inside the report.

### Where recorded values go

Everything a step lists under **Records** goes into one file: your pass report.
Create it before the pass.

1. Open a terminal (PowerShell or Git Bash) and change to the repository root -
   the folder containing `BUILD_HANDOFF.md`.

2. Create the directory for this pass. Replace `2026-07-29-P1` with your pass
   identifier here and in every command that follows.

   ```
   mkdir -p docs/pass_reports/2026-07-29-P1
   ```

3. Create the report from the template. **This is one command on one line**; if it
   appears wrapped on your screen, it is still one line.

   ```
   python tools/pass_report.py --template PROC-001 > docs/pass_reports/2026-07-29-P1/report.yaml
   ```

4. Open `docs/pass_reports/2026-07-29-P1/report.yaml` in a text editor. It already
   contains one block per step, in order, each reading `state: CHANGE-ME`.

5. As you execute each step, find the block whose `step:` matches it and fill it in.
   Each step below shows you the exact lines to write.

Times are written in UTC, in quotes, ending in Z - `'2026-07-29T14:36:30Z'`. Numbers
are written without units.

### Checking your record

Check your report as often as you like, and always before filing it. **This is one
command on one line**, even if your screen wraps it:

```
python tools/pass_report.py --validate docs/pass_reports/2026-07-29-P1/report.yaml
```

It prints `[PASS]`, or it names every step whose block is missing, unfilled or
inconsistent. A report straight from the template FAILS - every step still reads
`CHANGE-ME` - so a report nobody filled in cannot be mistaken for one that was.

### Evidence

Do not copy files into `verification/evidence/` by hand. Demonstrations write there
as they run. If you find yourself moving a file into that directory, stop and ask -
a file placed there by hand will not verify.

## Governs

Two presentations of lost insight: telemetry stopped, and commands unacknowledged. They
share a procedure because the escalation is the same and because the two can be present
at once — uplink is independent of the housekeeping downlink (HUG-EPS-004(c)), which is
the whole reason an escalation path exists. Its telemetry steps are entered on the
staleness alarm at any point in a contact, not only at acquisition.

## Roles

| Role | Who |
|---|---|
| **EPS** | EPS Officer |
| **FD** | Flight Director |

Every step below carries a stable identifier (HUG-OPS-001). **The completion
record is keyed by these identifiers**, one entry per step, with no exceptions
(HUG-OPS-002) — including the steps that turn out not to apply.

## Steps

### PROC-003-S01 — EPS Officer · on staleness annunciation

Record the staleness annunciation and the last frame received. The ground-side monitor
annunciates YELLOW at 10 s and RED at 30 s of no advance; a halted counter cannot alarm
itself, which is why the monitor is ground-side.

**Open:** http://localhost:2910 - Packet Viewer, CDH_FRAME_CNT; and CmdTlmServer, Log Messages, searched for staleness

**You know it worked when:** The staleness annunciator reads YELLOW (10 s of no advance) or RED (30 s). Record the last frame counter value you saw and when you saw it - after this the number stops changing, so the time you noticed it is part of the record.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S01` and make it read: ```yaml - step: PROC-003-S01 role: EPS operator: YOUR NAME state: completed records: last_frame_utc: '2026-07-29T14:38:05Z' last_cdh_frame_cnt: 4515 staleness_level: RED ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_FRAME_CNT`
- **Records:** `last_frame_utc`, `last_cdh_frame_cnt`, `staleness_level`
- **Applicability:** Applicable on the telemetry presentation.

### PROC-003-S02 — EPS Officer · on staleness annunciation

Determine whether the staleness is a ground-side artifact before escalating to the
spacecraft. Escalating on a ground fault sends a hazardous command to a healthy vehicle.

**Open:** http://localhost:2910 - CmdTlmServer: the Interfaces tab for HUGINN_INT and its Tlm pkts, and Log Messages searched for staleness

**You know it worked when:** Spacecraft-side: the interface still reads CONNECTED and the annunciator reads a staleness LEVEL. Ground-side: the interface is not CONNECTED. Monitor read fault: the annunciator reads READ_FAULT or NO_READ - which is a statement about the ground segment, not about the spacecraft, and must not be read as staleness.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S02` and make it read: ```yaml - step: PROC-003-S02 role: EPS operator: YOUR NAME state: completed branch: spacecraft-side observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'spacecraft-side', 'ground-side', 'monitor read fault'.

- **Checks:** `CDH_FRAME_CNT`
- **Applicability:** Applicable on the telemetry presentation.

**Decision — Which of the three conditions that all present as "the counter is not advancing at the ground" is this?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `spacecraft-side` | The staleness annunciator reads YELLOW or RED, the ground system's interface reads CONNECTED, and its received count is frozen — an absence of frames on a live link. | Continue to PROC-003-S03. |
| `ground-side` | The interface reads other than CONNECTED, or its received count is advancing while the displayed counter is not. | Restore the ground path and re-run PROC-001-S02. Do not command the spacecraft: nothing observed says anything about it. |
| `monitor read fault` | The staleness annunciator reads READ_FAULT or NO_READ rather than YELLOW or RED. | The monitor is blind and its silence is about itself, not about the spacecraft. Restart the staleness monitor and re-acquire; escalating here would send a hazardous command to a vehicle nothing has observed. READ_FAULT means reads began failing after succeeding; NO_READ before AOS is the ordinary pre-acquisition state and is not an anomaly at all. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-003-S03 — Flight Director · on confirmed spacecraft-side loss

Authorize and send CMD_SYS_RESET. It is hazardous: the ground system requires the
two-step confirmation, and the second step is the resend that follows the caught
refusal.

**Open:** http://localhost:2910 - Command Sender, CMD_SYS_RESET

**You know it worked when:** CMD_SYS_RESET is HAZARDOUS: the Command Sender asks for confirmation before it sends. That two-step is deliberate (B7) - read the command back before confirming.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S03` and make it read: ```yaml - step: PROC-003-S03 role: FD operator: YOUR NAME state: completed records: reset_command_utc: '2026-07-29T14:39:44Z' ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** —
- **Records:** `reset_command_utc`
- **Applicability:** Applicable when PROC-003-S02 selected the spacecraft-side branch.

### PROC-003-S04 — EPS Officer · after reset

Verify the reset by its post-reset counter epoch, NOT by delta arithmetic. CMD_SYS_RESET
is the sole exception: it reinitializes the counters and then applies its own
acceptance, so the first post-reset frame reads CDH_CMD_ACC_CNT = 1 and CDH_CMD_REJ_CNT
= 0. That epoch IS the acknowledgement.

**Open:** http://localhost:2910 - Packet Viewer, CDH_CMD_ACC_CNT, CDH_CMD_REJ_CNT, EPS_BATT_SOC

**You know it worked when:** The post-reset epoch: CDH_CMD_ACC_CNT reads exactly 1 and CDH_CMD_REJ_CNT exactly 0 - NOT the previous values plus one. Reset is the sole exception to counter delta arithmetic, so do not compute a delta here. State of charge is preserved across the reset.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S04` and make it read: ```yaml - step: PROC-003-S04 role: EPS operator: YOUR NAME state: completed records: acc_cnt_post_reset: 1 rej_cnt_post_reset: 0 soc_pct_post_reset: 38.9 ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`, `CDH_FRAME_CNT`, `EPS_BATT_SOC`
- **Records:** `acc_cnt_post_reset`, `rej_cnt_post_reset`, `soc_pct_post_reset`
- **Applicability:** Applicable when PROC-003-S03 was executed.

### PROC-003-S05 — EPS Officer · after reset

Determine whether telemetry has been restored.

**Open:** http://localhost:2910 - Packet Viewer, CDH_FRAME_CNT; and CmdTlmServer, Log Messages, searched for staleness

**You know it worked when:** Restored: the frame counter is advancing again and the annunciator returns to GREEN. Not restored: it is still frozen after the reset, which escalates.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S05` and make it read: ```yaml - step: PROC-003-S05 role: EPS operator: YOUR NAME state: completed branch: restored observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'restored', 'not restored'.

- **Checks:** `CDH_FRAME_CNT`, `EPS_BATT_SOC`
- **Applicability:** Applicable when PROC-003-S03 was executed.

**Decision — Is CDH_FRAME_CNT advancing again, with state of charge preserved?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `restored` | CDH_FRAME_CNT advances across consecutive frames, the staleness annunciator returns to GREEN, and EPS_BATT_SOC is continuous with the value before the outage. | Return to PROC-001 at the step after the last one you completed there, and reassess state of health. When PROC-003 was entered from PROC-001-S05, that step is PROC-001-S06. |
| `not restored` | No frames after the reset command, or the staleness annunciator remains RED past 30 s. | Declare the anomaly (FD). Insight is not recoverable this pass; file the anomaly report and plan the next contact against the last known state. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-003-S06 — EPS Officer · on unacknowledged command

Establish that a verified send produced no accounting. Every received command increments
exactly one counter by exactly one, visible no later than the next housekeeping frame;
absence of any delta within 10 s of a verified send is the loss-of-commandability
declaration threshold (HUG-CMD-007).

**Open:** http://localhost:2910 - Command Sender, then Packet Viewer for both counters

**You know it worked when:** Read CDH_CMD_ACC_CNT and CDH_CMD_REJ_CNT before the send, send, then watch both for 10 s. Establishing that NEITHER moved is the observation; you cannot make it without the before-values.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S06` and make it read: ```yaml - step: PROC-003-S06 role: EPS operator: YOUR NAME state: completed records: send_utc: '2026-07-29T14:40:12Z' acc_cnt_at_send: 4472 rej_cnt_at_send: 0 elapsed_s: 10 ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`, `CDH_FRAME_CNT`
- **Records:** `send_utc`, `acc_cnt_at_send`, `rej_cnt_at_send`, `elapsed_s`
- **Applicability:** Applicable on the command presentation.

### PROC-003-S07 — EPS Officer · on unacknowledged command

Determine whether the command path is lost.

**Open:** http://localhost:2910 - Packet Viewer, both command counters

**You know it worked when:** Command path lost: neither counter moved within 10 s of a verified send. Not lost: either counter moved, and the command was received even if it was rejected.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S07` and make it read: ```yaml - step: PROC-003-S07 role: EPS operator: YOUR NAME state: completed branch: accounted late observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'accounted late', 'not accounted'.

- **Checks:** `CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`, `CDH_FRAME_CNT`
- **Applicability:** Applicable on the command presentation.

**Decision — Did either counter change within 10 s of the verified send?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `accounted late` | One counter incremented by exactly one within 10 s, later than the next frame but inside the threshold. | Not a loss of commandability. Record the latency in the pass report and continue the governing procedure. |
| `not accounted` | Neither counter changed within 10 s of the verified send, while CDH_FRAME_CNT continues to advance — telemetry is flowing and commands are not being accounted. | Continue to PROC-003-S08. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-003-S08 — EPS Officer · on unacknowledged command

Retry once within the pass. A single retry distinguishes a lost uplink frame from a lost
command path, and costs one command slot.

**Open:** http://localhost:2910 - Command Sender

**You know it worked when:** Send the same command once more. One retry distinguishes a lost uplink frame from a lost command path; a second and third tell you nothing the first did not.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S08` and make it read: ```yaml - step: PROC-003-S08 role: EPS operator: YOUR NAME state: completed records: retry_utc: '2026-07-29T14:40:31Z' retry_outcome: unacknowledged ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`
- **Records:** `retry_utc`, `retry_outcome`
- **Applicability:** Applicable when PROC-003-S07 selected the not-accounted branch.

### PROC-003-S09 — Flight Director · on failed retry

Determine whether to escalate to a reset.

**Open:** http://localhost:2910 - Packet Viewer, both command counters

**You know it worked when:** Escalate if the retry was also unacknowledged. Do not escalate if the retry was accounted - the path is there.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S09` and make it read: ```yaml - step: PROC-003-S09 role: FD operator: YOUR NAME state: completed branch: retry accounted observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'retry accounted', 'retry unaccounted'.

- **Checks:** `CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`, `CDH_FRAME_CNT`
- **Applicability:** Applicable when PROC-003-S08 was executed.

**Decision — Did the retry produce a counter delta?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `retry accounted` | One counter incremented by exactly one after the retry. | The command path is live. Return to the governing procedure and record the first send as an anomaly in the pass report. |
| `retry unaccounted` | Neither counter changed within 10 s of the retry, while CDH_FRAME_CNT continues to advance. | Escalate to PROC-003-S03: send CMD_SYS_RESET under two-step confirmation. Verify by the post-reset counter epoch at PROC-003-S04, not by delta. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-003-S10 — Flight Director · closeout

Declare the anomaly and file the anomaly report, whichever branch was taken. A recovered
outage is still an outage and is still reported.

**Open:** docs/pass_reports/<pass-id>/report.yaml - the anomalies: section

**Run:**

```bash
python tools/pass_report.py --validate docs/pass_reports/<pass-id>/report.yaml
```

> `<pass-id>` — The pass identifier, form YYYY-MM-DD-Pn, read off campaign/CAMPAIGN_PLAN.md. The campaign's first pass is 2026-07-29-P1.

**You know it worked when:** The anomaly report is part of the pass report, not a separate document. The validator names any anomaly entry missing its finding, feasibility or disposition.

**Write it down:** In your report, find the block that begins `- step: PROC-003-S10` and make it read: ```yaml - step: PROC-003-S10 role: FD operator: YOUR NAME state: completed ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `EPS_MODE`, `EPS_BATT_SOC`, `CDH_FRAME_CNT`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

