# PROC-002 — Low-battery and limit response

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

The response to a low state of charge, a low battery voltage, a load-current excursion,
or a SAFE annunciation. CONOPS Sec. 4.4 maps each alarmed limit to this procedure or to
the generic contingency response.

## Roles

| Role | Who |
|---|---|
| **EPS** | EPS Officer |
| **FD** | Flight Director |

Every step below carries a stable identifier (HUG-OPS-001). **The completion
record is keyed by these identifiers**, one entry per step, with no exceptions
(HUG-OPS-002) — including the steps that turn out not to apply.

## Steps

### PROC-002-S01 — EPS Officer · on annunciation

Confirm the annunciation: which point, which limit side, and the value read. Confirm it
against the dictionary of record rather than against memory.

**Open:** http://localhost:2910 - Packet Viewer; the annunciated point is the one shown yellow or red

**You know it worked when:** Read the point's mnemonic, its current value, and which limit side it crossed. The dictionary's limits are in docs/tlm_cmd_dictionary.md if you want the thresholds beside the reading.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S01` and make it read: ```yaml - step: PROC-002-S01 role: EPS operator: YOUR NAME state: completed records: annunciated_point: EPS_BATT_SOC annunciated_value: 34.6 annunciated_level: YELLOW ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `EPS_BATT_SOC`, `EPS_BATT_V`, `EPS_LOAD_I`, `EPS_BATT_I`, `EPS_MODE`
- **Records:** `annunciated_point`, `annunciated_value`, `annunciated_level`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

### PROC-002-S02 — EPS Officer · on annunciation

If the point you confirmed at S01 is EPS_LOAD_I, record branch load alarm and go to S03.
Otherwise, determine whether the energy balance is negative.

**Open:** http://localhost:2910 - Telemetry Grapher, EPS_BATT_I over the last few minutes

**You know it worked when:** Load alarm: the point you confirmed at S01 is EPS_LOAD_I. That alone selects the branch, whatever EPS_BATT_I reads. Otherwise, negative balance: EPS_BATT_I sits below zero (discharging) while ADM_ECLIPSE reads SUNLIT, or the SoC trace slopes down. A single reading cannot tell you this - it is a trend, which is what the grapher is for.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S02` and make it read: ```yaml - step: PROC-002-S02 role: EPS operator: YOUR NAME state: completed branch: negative beyond eclipse observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'load alarm', 'negative beyond eclipse', 'explained by eclipse'.

- **Checks:** `EPS_BATT_I`, `EPS_SA1_I`, `EPS_SA2_I`, `ADM_ECLIPSE`, `EPS_LOAD_I`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

**Decision — Was PROC-002 entered on a load alarm, and if not, is the spacecraft trending energy-negative beyond what the illumination state explains?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `load alarm` | The point recorded at PROC-002-S01 is EPS_LOAD_I, at or above 1.5 A. This selects the branch whatever EPS_BATT_I reads. | Continue to PROC-002-S03. A load alarm is diagnosed from the load itself and does not wait for the battery to discharge. |
| `negative beyond eclipse` | EPS_BATT_I is negative across three or more consecutive frames while ADM_ECLIPSE reads SUNLIT, or the discharge is deeper than the eclipse plan predicts. | Continue to PROC-002-S03. |
| `explained by eclipse` | EPS_BATT_I is negative while ADM_ECLIPSE reads ECLIPSE and the depth of discharge tracks the plan. | No shed action. Monitor to eclipse exit and confirm recovery; if state of charge does not recover after exit, return to PROC-002-S02. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-002-S03 — EPS Officer · on negative trend or load alarm

Identify the cause among the two the record anticipates.

**Open:** http://localhost:2910 - Packet Viewer, EPS_SA1_I and EPS_SA2_I side by side, and EPS_LOAD_I

**You know it worked when:** String loss: one array current near zero while the other holds - an ASYMMETRY. Stuck load: both strings normal but EPS_LOAD_I about 2 W higher than the plan expects. These are the two causes the record anticipates and they look different on the same screen.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S03` and make it read: ```yaml - step: PROC-002-S03 role: EPS operator: YOUR NAME state: completed branch: array-string failure observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'array-string failure', 'load excursion', 'neither'.

- **Checks:** `EPS_SA1_I`, `EPS_SA2_I`, `EPS_LOAD_I`
- **Applicability:** Applicable when PROC-002-S02 selected negative beyond eclipse or load alarm.

**Decision — Is generation down, or is load up?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `array-string failure` | EPS_SA1_I and EPS_SA2_I are asymmetric — one string at or near zero while the other carries its expected current for the illumination state. | Continue to PROC-002-S04. Generation cannot be restored from the ground; the response is load management. |
| `load excursion` | EPS_LOAD_I is at or above 1.5 A with both array strings symmetric and consistent with illumination. | Continue to PROC-002-S04, load-shed branch. |
| `neither` | Strings symmetric and EPS_LOAD_I below 1.5 A, yet the discharge persists. | Declare an anomaly (FD). The generic contingency response governs: safe the spacecraft by command if power integrity is threatened, and file an anomaly report. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-002-S04 — EPS Officer · on negative trend or load alarm

Shed the payload: send CMD_PLD_SET_STATE with state OFF. This is the only load the
ground can shed.

**Open:** http://localhost:2910 - Command Sender, CMD_PLD_SET_STATE, state OFF

**You know it worked when:** The command is sent. Note the time to the second; S05 verifies against it.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S04` and make it read: ```yaml - step: PROC-002-S04 role: EPS operator: YOUR NAME state: completed records: shed_command_utc: '2026-07-29T14:39:10Z' ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** —
- **Records:** `shed_command_utc`
- **Applicability:** Applicable when PROC-002-S03 selected array-string failure or load excursion. Not applicable when the payload is already OFF — state PLD_STATE as the basis.

### PROC-002-S05 — EPS Officer · after shed

Verify the shed by counter delta and affected point.

**Open:** http://localhost:2910 - Packet Viewer, PLD_STATE and EPS_LOAD_I

**You know it worked when:** PLD_STATE reads OFF and EPS_LOAD_I drops by roughly the payload load, within one frame. Read EPS_LOAD_I BEFORE the send too - the drop is the evidence, and a drop needs a before.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S05` and make it read: ```yaml - step: PROC-002-S05 role: EPS operator: YOUR NAME state: completed records: pld_state_after_shed: OFF load_i_after_shed: 0.62 ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_CMD_ACC_CNT`, `PLD_STATE`, `EPS_LOAD_I`
- **Records:** `pld_state_after_shed`, `load_i_after_shed`
- **Applicability:** Applicable when PROC-002-S04 was executed.

### PROC-002-S06 — EPS Officer · after shed

Determine whether shedding restored a non-negative balance.

**Open:** http://localhost:2910 - Telemetry Grapher, EPS_BATT_I

**You know it worked when:** Restored: EPS_BATT_I is at or above zero after the shed. Not restored: still negative, and the ladder will act on its own at 30 %.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S06` and make it read: ```yaml - step: PROC-002-S06 role: EPS operator: YOUR NAME state: completed branch: recovered observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'recovered', 'still negative'.

- **Checks:** `EPS_BATT_I`, `EPS_BATT_SOC`
- **Applicability:** Applicable when PROC-002-S04 was executed.

**Decision — Is EPS_BATT_I non-negative after the shed?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `recovered` | EPS_BATT_I is at or above zero across three or more consecutive frames while sunlit. | Continue to PROC-002-S09. The stuck-load case reaches here with the balance still negative and is handled by the next branch. |
| `still negative` | EPS_BATT_I remains negative across three or more consecutive frames after the shed was verified — the load did not go away when the payload did, which is the stuck-load presentation. | Continue to PROC-002-S07. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-002-S07 — Flight Director · on continued discharge

Do not fight the mode ladder. The spacecraft protects itself autonomously: LOW_POWER at
30 % and SAFE at 20 %, shedding the payload on entry. Commanding against a descending
ladder spends the margin the ladder exists to hold.

**Open:** http://localhost:2910 - Packet Viewer, EPS_MODE and EPS_BATT_SOC

**You know it worked when:** You are watching, not commanding. EPS_MODE changes to LOW_POWER at 30 % or SAFE at 20 % on its own. Record the mode it entered and the SoC when it did; commanding against a descending ladder spends the margin the ladder exists to hold.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S07` and make it read: ```yaml - step: PROC-002-S07 role: FD operator: YOUR NAME state: completed records: mode_entered: LOW_POWER soc_pct_at_entry: 29.8 ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `EPS_BATT_SOC`, `EPS_MODE`
- **Records:** `mode_entered`, `soc_pct_at_entry`
- **Applicability:** Applicable when PROC-002-S06 selected the still-negative branch. Not applicable when state of charge recovered before an autonomous entry — state the recovering SoC as the basis.

### PROC-002-S08 — Flight Director · on continued discharge

Determine whether the spacecraft must be safed by command.

**Open:** http://localhost:2910 - Packet Viewer, EPS_MODE and EPS_BATT_SOC

**You know it worked when:** Safe by command if the ladder has not acted and SoC continues to fall; hold if the ladder has already taken the spacecraft where you would have sent it.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S08` and make it read: ```yaml - step: PROC-002-S08 role: FD operator: YOUR NAME state: completed branch: safe by command observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'safe by command', 'ladder holds'.

- **Checks:** `EPS_BATT_SOC`, `EPS_BATT_V`, `EPS_BUS_V`, `EPS_MODE`
- **Applicability:** Applicable when PROC-002-S06 selected the still-negative branch.

**Decision — Is power integrity threatened beyond what the ladder will hold?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `safe by command` | EPS_BATT_SOC at or below 20 % with the ladder not yet in SAFE, or EPS_BUS_V outside 4.75 to 5.25 V. | Send CMD_SAFE_ENTER. It is hazardous: the ground system requires the two-step confirmation, and the second step is the resend that follows the caught refusal, never a bypass called on its own. |
| `ladder holds` | EPS_MODE has entered LOW_POWER or SAFE autonomously and EPS_BATT_SOC has stopped falling across three or more consecutive frames. | Continue to PROC-002-S09. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-002-S09 — Flight Director · on recovery

Recover the commanded mode. Recovery from LOW_POWER or SAFE is a deliberate ground act
and is gated on the recovery floor for the target mode, not on the autonomous entry
threshold — the floors sit above the entries so a recovery cannot immediately re-trip.

**Open:** http://localhost:2910 - Command Sender, CMD_MODE_SET

**You know it worked when:** Recovery has a FLOOR: the command is accepted only above the recovery floor for the target mode, and rejected with MODE_INHIBIT below it. A rejection here is the spacecraft protecting itself, not a failed command.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S09` and make it read: ```yaml - step: PROC-002-S09 role: FD operator: YOUR NAME state: completed branch: recover to NOMINAL observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'recover to NOMINAL', 'recover to LOW_POWER', 'hold'.

- **Checks:** `EPS_BATT_SOC`, `EPS_MODE`
- **Applicability:** Applicable when the spacecraft is in LOW_POWER or SAFE. Not applicable when EPS_MODE still reads NOMINAL — state that as the basis.

**Decision — Is state of charge at or above the recovery floor for the target mode?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `recover to NOMINAL` | EPS_BATT_SOC at or above 35 %. | Send CMD_MODE_SET with target NOMINAL, then PROC-002-S10. |
| `recover to LOW_POWER` | EPS_BATT_SOC at or above 25 % but below 35 %. | Send CMD_MODE_SET with target LOW_POWER, then PROC-002-S10. |
| `hold` | EPS_BATT_SOC below 25 %. | Do not command a recovery. Hold and monitor; a mode command below the floor is refused with MODE_INHIBIT and spends a command slot for nothing. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-002-S10 — EPS Officer · on recovery

Verify the mode change by counter delta and affected point.

**Open:** http://localhost:2910 - Packet Viewer, CDH_CMD_ACC_CNT and EPS_MODE

**You know it worked when:** Accept counter +1 and EPS_MODE reading the mode you commanded, within one frame.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S10` and make it read: ```yaml - step: PROC-002-S10 role: EPS operator: YOUR NAME state: completed records: mode_after_recovery: NOMINAL ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`, `CDH_REJ_REASON`, `EPS_MODE`
- **Records:** `mode_after_recovery`
- **Applicability:** Applicable when PROC-002-S09 sent a mode command.

### PROC-002-S11 — Flight Director · closeout

Declare the anomaly and file the anomaly report. Payload re-activation is not part of
this procedure: it is a PROC-001 commanding step on a later pass, subject to the 40 %
activation inhibit.

**Open:** docs/pass_reports/<pass-id>/report.yaml - the anomalies: section

**Run:**

```bash
python tools/pass_report.py --validate docs/pass_reports/<pass-id>/report.yaml
```

> `<pass-id>` — The pass identifier, form YYYY-MM-DD-Pn, read off campaign/CAMPAIGN_PLAN.md. The campaign's first pass is 2026-07-29-P1.

**You know it worked when:** Every anomaly entry needs an id, the step it arose at, the finding, a feasibility statement and a disposition. The validator names any that are incomplete.

**Write it down:** In your report, find the block that begins `- step: PROC-002-S11` and make it read: ```yaml - step: PROC-002-S11 role: FD operator: YOUR NAME state: completed ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `EPS_MODE`, `EPS_BATT_SOC`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

