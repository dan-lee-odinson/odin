# PROC-001 — Nominal activation pass

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

A routine contact: pass setup, acquisition, state-of-health assessment, the commanding
window, final snapshot and the pass report. Commissioning's first payload activation is
this procedure (CONOPS Sec. 4.1).

At any point in the contact, a staleness line reading YELLOW or RED in CmdTlmServer's
Log Messages sends you to PROC-003. When PROC-003 is done, return here at the step after
the last one you completed.

## Roles

| Role | Who |
|---|---|
| **PLAN** | Ops Planner |
| **EPS** | EPS Officer |
| **FD** | Flight Director |

Every step below carries a stable identifier (HUG-OPS-001). **The completion
record is keyed by these identifiers**, one entry per step, with no exceptions
(HUG-OPS-002) — including the steps that turn out not to apply.

## Steps

### PROC-001-S01 — Ops Planner · AOS - 15 min

Review the pass plan: contact window, predicted elevation profile, eclipse timing
relative to the pass, planned commands, and the state of charge the plan predicts at
acquisition.

**Open:** campaign/CAMPAIGN_PLAN.md

**Run:**

```bash
python tools/gen_campaign.py
```

> `<pass-id>` — The pass identifier, form YYYY-MM-DD-Pn, read off campaign/CAMPAIGN_PLAN.md. The campaign's first pass is 2026-07-29-P1.

**You know it worked when:** The command prints a line like `19 contacts: 16 usable for commanding, 19 for telemetry` and `4 passes planned`. Open campaign/CAMPAIGN_PLAN.md, find the PASS-n section for the pass you are flying, and note the contact number it names. Then find that number's row in the computed-week table: it gives the contact's start second, its length above the mask, and whether commanding is allowed on it.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S01` and make it read: ```yaml - step: PROC-001-S01 role: PLAN operator: YOUR NAME state: completed records: predicted_soc_pct: 38 window_aos_utc: '2026-07-29T14:36:30Z' window_los_utc: '2026-07-29T14:44:00Z' ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** —
- **Records:** `predicted_soc_pct`, `window_aos_utc`, `window_los_utc`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

### PROC-001-S02 — EPS Officer · AOS - 5 min

Bring up the ground system and run the pre-pass configuration verification. This is the
step FM-GND-04 names as the detection and response for loaded- configuration drift, and
a mismatch is a no-go.

```bash
python tools/pass_setup.py --pass-id <pass-id>
```

**Open:** gnd/RUNBOOK.md

**Run:**

```bash
cd gnd/openc3 && docker compose up -d && cd ../..
python tools/pass_setup.py --pass-id <pass-id>
```

> `<pass-id>` — The pass identifier, form YYYY-MM-DD-Pn, read off campaign/CAMPAIGN_PLAN.md. The campaign's first pass is 2026-07-29-P1.

**You know it worked when:** `docker compose up -d` ends with the openc3-* containers reported Started or Running; give it a minute on a cold start. http://localhost:2910 then loads the COSMOS console. `pass_setup.py` prints four condition lines - identity vs dictionary, loaded vs repository, target inventory, configuration digest - each PASS or FAIL, then a final line reading `Verdict: GO` or `Verdict: NO-GO`.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S02` and make it read: ```yaml - step: PROC-001-S02 role: EPS operator: YOUR NAME state: completed records: pass_setup_verdict: GO identity_vs_dictionary_result: PASS loaded_vs_repository_result: PASS target_inventory_result: PASS ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** —
- **Records:** `pass_setup_verdict`, `identity_vs_dictionary_result`, `loaded_vs_repository_result`, `target_inventory_result`
- **May be re-run within the pass.** Record it as ONE completion entry carrying every attempt (`attempts:` and `earlier_attempts:`), never as a second entry. The attempt that failed is part of the record of the pass; only the final attempt's values go in `records:`.
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

### PROC-001-S03 — Flight Director · AOS - 5 min

Give go or no-go for commanding on this pass.

**Open:** campaign/CAMPAIGN_PLAN.md

**You know it worked when:** You are reading the verdict line PROC-001-S02 just printed. GO if it said `Verdict: GO`; NO-GO if it said NO-GO, and the failing condition is named on the line above it.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S03` and make it read: ```yaml - step: PROC-001-S03 role: FD operator: YOUR NAME state: completed branch: GO observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'GO', 'NO-GO'.

- **Checks:** —
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

**Decision — Is the loaded configuration the configuration of record?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `GO` | tools/pass_setup.py printed "Verdict: GO" and all four of its conditions read PASS. | Continue to PROC-001-S04. |
| `NO-GO` | tools/pass_setup.py printed "Verdict: NO-GO", naming at least one failed condition. | Commanding is not authorized. Reload the generated configuration and re-run PROC-001-S02 (FM-GND-04 note (e)). The no-go is procedural: no technical inhibit is armed, and commanding against it is a procedure violation to be dispositioned as an anomaly. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-001-S04 — EPS Officer · AOS

Confirm telemetry frame lock by recording CDH_FRAME_CNT in two consecutive housekeeping
frames. Record the two values, not "the monitor is green": green is the ABSENCE of an
annunciation and is produced identically by a healthy spacecraft and by a monitor that
cannot read at all. This build has already seen a staleness monitor annunciate a
textbook transcript while never once reading the counter, and a monitor blind since
start-up reads NO_READ rather than green.

**Open:** http://localhost:2910 - Packet Viewer, target HUGINN, packet HK

**You know it worked when:** CDH_FRAME_CNT shows a number that increases each time the packet updates. Read it twice, a second or so apart, and note both. The staleness annunciator is the newest staleness line in CmdTlmServer's Log Messages list (type staleness in its Search box); at frame lock it reads GREEN.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S04` and make it read: ```yaml - step: PROC-001-S04 role: EPS operator: YOUR NAME state: completed records: first_frame_utc: '2026-07-29T14:36:32Z' cdh_frame_cnt_first: 4471 cdh_frame_cnt_second: 4472 staleness_annunciator_state: GREEN ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_FRAME_CNT`
- **Records:** `first_frame_utc`, `cdh_frame_cnt_first`, `cdh_frame_cnt_second`, `staleness_annunciator_state`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

### PROC-001-S05 — EPS Officer · AOS

Determine whether telemetry has been acquired.

**Open:** http://localhost:2910 - Packet Viewer, target HUGINN, packet HK

**You know it worked when:** Acquired: the two CDH_FRAME_CNT readings from S04 differ and the annunciator is GREEN. Not acquired: the readings are identical, or no packet is updating at all.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S05` and make it read: ```yaml - step: PROC-001-S05 role: EPS operator: YOUR NAME state: completed branch: acquired observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'acquired', 'not acquired'.

- **Checks:** `CDH_FRAME_CNT`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

**Decision — Is CDH_FRAME_CNT advancing?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `acquired` | CDH_FRAME_CNT increases between two consecutive housekeeping frames and the ground-side staleness annunciator reads GREEN. | Continue to PROC-001-S06. |
| `not acquired` | CDH_FRAME_CNT does not advance for 10 s and the staleness annunciator reads YELLOW or RED. | Execute PROC-003. This pass's remaining steps are omitted or not applicable per their own conditions. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-001-S06 — EPS Officer · AOS + 2 min

Complete the state-of-health assessment: EPS panel, battery voltage and state of charge
against the plan, and both array-string currents against the illumination state.

**Open:** http://localhost:2910 - Packet Viewer, target HUGINN, packet HK

**You know it worked when:** All six points readable in one view: EPS_BATT_V, EPS_BATT_SOC, EPS_BATT_I, EPS_SA1_I, EPS_SA2_I, ADM_ECLIPSE. Compare EPS_BATT_SOC against the predicted_soc_pct you recorded at S01 and note the difference.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S06` and make it read: ```yaml - step: PROC-001-S06 role: EPS operator: YOUR NAME state: completed records: eps_batt_v_at_aos2: 7.31 soc_pct_at_aos2: 37.4 soc_delta_vs_plan_pct: -0.6 eps_sa1_i_at_aos2: 1.70 eps_sa2_i_at_aos2: 1.68 adm_eclipse_at_aos2: SUNLIT ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `EPS_BATT_V`, `EPS_BATT_SOC`, `EPS_SA1_I`, `EPS_SA2_I`, `ADM_ECLIPSE`, `EPS_MODE`
- **Records:** `eps_batt_v_at_aos2`, `soc_pct_at_aos2`, `soc_delta_vs_plan_pct`, `eps_sa1_i_at_aos2`, `eps_sa2_i_at_aos2`, `adm_eclipse_at_aos2`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

### PROC-001-S07 — Flight Director · AOS + 2 min

Determine whether the spacecraft is within its operating envelope.

**Open:** http://localhost:2910 - Packet Viewer; limit colours are shown beside each value

**You know it worked when:** Nominal: no value shown yellow or red, SoC above 35 %, EPS_BATT_I positive while ADM_ECLIPSE reads SUNLIT. Limit response required: any yellow or red, or EPS_MODE reading SAFE. Autonomous protection did not actuate: SoC below 30 % while EPS_MODE still reads NOMINAL.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S07` and make it read: ```yaml - step: PROC-001-S07 role: FD operator: YOUR NAME state: completed branch: nominal observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'nominal', 'limit response required', 'autonomous protection did not actuate'.

- **Checks:** `EPS_BATT_SOC`, `EPS_BATT_V`, `EPS_LOAD_I`, `EPS_MODE`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

**Decision — Is any alarmed limit violated, or the energy balance negative?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `nominal` | No annunciator reads YELLOW or RED, and EPS_BATT_I is non-negative or consistent with the illumination state. | Continue to PROC-001-S08. |
| `limit response required` | Any of EPS_BATT_SOC at or below 35 %, EPS_BATT_V at or below 7.2 V, EPS_LOAD_I at or above 1.5 A, or EPS_MODE reading SAFE. | Execute PROC-002. Return here only if PROC-002 closes with the spacecraft in a commanded stable configuration. |
| `autonomous protection did not actuate` | EPS_BATT_SOC below 30 % while EPS_MODE still reads NOMINAL. The ladder should already have entered LOW_POWER at 30 %; that it has not is the ground cross-check FM-EPS-10 names, and the yellow limit at 35 % exists to precede this point by design so the ground sees it coming. | Execute PROC-002 AND declare an anomaly: the spacecraft's autonomous protection is not acting. Do not assume the ladder will catch the next threshold — it did not catch this one. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-001-S08 — EPS Officer · commanding window

Confirm the payload activation inhibit is satisfied before requesting authorization.

**Open:** http://localhost:2910 - Packet Viewer, EPS_BATT_SOC

**You know it worked when:** A single reading of EPS_BATT_SOC, taken now rather than reused from S06 - the inhibit is checked against the value at the moment of commanding.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S08` and make it read: ```yaml - step: PROC-001-S08 role: EPS operator: YOUR NAME state: completed records: soc_pct_at_activation_check: 41.2 ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `EPS_BATT_SOC`
- **Records:** `soc_pct_at_activation_check`
- **Applicability:** Applicable when the pass plan includes a payload activation. Not applicable on a pass whose plan contains no activation — state that in the completion record as the basis.

### PROC-001-S09 — Flight Director · commanding window

Authorize or withhold the payload activation.

**Open:** http://localhost:2910 - Packet Viewer, EPS_BATT_SOC; and the reading you recorded at PROC-001-S08

**You know it worked when:** Authorized if the S08 reading is ABOVE 40 %. Withheld if it is at or below 40 % - the spacecraft would reject the command anyway (HUG-CMD-002), and sending it to watch it fail is not a test, it is a rejection you chose.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S09` and make it read: ```yaml - step: PROC-001-S09 role: FD operator: YOUR NAME state: completed branch: authorized observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'authorized', 'withheld'.

- **Checks:** `EPS_BATT_SOC`
- **Applicability:** Applicable when the pass plan includes a payload activation.

**Decision — Is EPS_BATT_SOC above the 40 % activation inhibit?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `authorized` | EPS_BATT_SOC reads above 40 % in the frame checked at PROC-001-S08. | Continue to PROC-001-S10. |
| `withheld` | EPS_BATT_SOC reads at or below 40 % in that frame. | Do not send the activation. PROC-001-S10 through PROC-001-S14 are not applicable for this pass; record the withheld observation as their basis. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-001-S10 — EPS Officer · commanding window

Send CMD_PLD_SET_STATE with state ON.

**Open:** http://localhost:2910 - Command Sender, target HUGINN, command CMD_PLD_SET_STATE

**You know it worked when:** Choose state = ON and send. The Command Sender shows the command as sent; it does not tell you the spacecraft accepted it, which is what S11 is for.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S10` and make it read: ```yaml - step: PROC-001-S10 role: EPS operator: YOUR NAME state: completed records: command_sent_utc: '2026-07-29T14:40:00Z' ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** —
- **Records:** `command_sent_utc`
- **May be re-run within the pass.** Record it as ONE completion entry carrying every attempt (`attempts:` and `earlier_attempts:`), never as a second entry. The attempt that failed is part of the record of the pass; only the final attempt's values go in `records:`.
- **Applicability:** Applicable when PROC-001-S09 selected the authorized branch.

### PROC-001-S11 — EPS Officer · commanding window

Verify the command by counter delta AND by its affected telemetry point. Either alone is
insufficient: a counter delta with no state change means the command was accounted and
did nothing.

**Open:** http://localhost:2910 - Packet Viewer, CDH_CMD_ACC_CNT and PLD_STATE

**You know it worked when:** CDH_CMD_ACC_CNT one higher than before the send, and PLD_STATE reading ON - both within one housekeeping frame, so about a second. Read the counter BEFORE you send as well as after; a delta needs two numbers.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S11` and make it read: ```yaml - step: PROC-001-S11 role: EPS operator: YOUR NAME state: completed records: acc_cnt_before: 4471 acc_cnt_after: 4472 pld_state_after: ON ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`, `PLD_STATE`
- **Records:** `acc_cnt_before`, `acc_cnt_after`, `pld_state_after`
- **May be re-run within the pass.** Record it as ONE completion entry carrying every attempt (`attempts:` and `earlier_attempts:`), never as a second entry. The attempt that failed is part of the record of the pass; only the final attempt's values go in `records:`.
- **Applicability:** Applicable when PROC-001-S10 was executed.

### PROC-001-S12 — EPS Officer · commanding window

Determine the outcome of the command.

**Open:** http://localhost:2910 - Packet Viewer, CDH_CMD_ACC_CNT, CDH_CMD_REJ_CNT, CDH_REJ_REASON

**You know it worked when:** Accepted: accept counter +1 and PLD_STATE ON. Rejected: REJECT counter +1, and CDH_REJ_REASON names the cause. Unacknowledged: NEITHER counter moved within 10 s of the send - that is the threshold, count it.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S12` and make it read: ```yaml - step: PROC-001-S12 role: EPS operator: YOUR NAME state: completed branch: accepted observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'accepted', 'rejected', 'unacknowledged'.

- **Checks:** `CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`, `CDH_REJ_REASON`, `PLD_STATE`
- **May be re-run within the pass.** Record it as ONE completion entry carrying every attempt (`attempts:` and `earlier_attempts:`), never as a second entry. The attempt that failed is part of the record of the pass; only the final attempt's values go in `records:`.
- **Applicability:** Applicable when PROC-001-S10 was executed.

**Decision — Was the command accepted, rejected, or unacknowledged?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `accepted` | CDH_CMD_ACC_CNT incremented by exactly one and PLD_STATE reads ON, both no later than the next housekeeping frame. | Continue to PROC-001-S13. |
| `rejected` | CDH_CMD_REJ_CNT incremented by exactly one; read CDH_REJ_REASON for the cause. | Do not retry blindly. If the reason is MODE_INHIBIT, execute PROC-002. If ARG_RANGE, correct the argument against the dictionary and re-send. |
| `unacknowledged` | Neither counter changed within 10 s of the verified send (HUG-CMD-007). | Execute PROC-003, command-path branch. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

### PROC-001-S13 — EPS Officer · commanding window

Set the payload sampling rate with CMD_PLD_SET_RATE, in the dictionary range 0.1 to 10
Hz.

**Open:** http://localhost:2910 - Command Sender, command CMD_PLD_SET_RATE

**You know it worked when:** Set rate to a value in 0.1-10 Hz (the pass plan names the one to use) and send. Outside that range the spacecraft rejects with ARG_RANGE, which is the dictionary working, not a fault.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S13` and make it read: ```yaml - step: PROC-001-S13 role: EPS operator: YOUR NAME state: completed records: commanded_rate_hz: 0 ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** —
- **Records:** `commanded_rate_hz`
- **Applicability:** Applicable when PROC-001-S12 selected the accepted branch.

### PROC-001-S14 — EPS Officer · commanding window

Verify the rate command by counter delta and affected point.

**Open:** http://localhost:2910 - Packet Viewer, CDH_CMD_ACC_CNT and PLD_RATE_HZ

**You know it worked when:** Accept counter one higher again, and PLD_RATE_HZ reading the value you sent, within one frame.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S14` and make it read: ```yaml - step: PROC-001-S14 role: EPS operator: YOUR NAME state: completed records: pld_rate_after: CHANGE-ME ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_CMD_ACC_CNT`, `PLD_RATE`
- **Records:** `pld_rate_after`
- **Applicability:** Applicable when PROC-001-S13 was executed.

### PROC-001-S15 — EPS Officer · LOS - 2 min

Take the final state snapshot: mode, state of charge, load current, and the trend
against plan.

**Open:** http://localhost:2910 - Packet Viewer, target HUGINN, packet HK

**You know it worked when:** One final read of the whole HK packet, two minutes before LOS. This is the last state anyone will have until the next contact, which is why the step exists and why omitting it is an anomaly rather than a shrug.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S15` and make it read: ```yaml - step: PROC-001-S15 role: EPS operator: YOUR NAME state: completed records: soc_pct_at_los: CHANGE-ME mode_at_los: CHANGE-ME ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `EPS_MODE`, `EPS_BATT_SOC`, `EPS_LOAD_I`, `EPS_BATT_V`
- **Records:** `soc_pct_at_los`, `mode_at_los`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

### PROC-001-S16 — Ops Planner · LOS

Close the contact and open the pass report. Record the observed LOS against the computed
window: "began the report" is an act with no observable, and a step whose completion is
an assertion is one nobody can review.

**Open:** campaign/CAMPAIGN_PLAN.md - the contact row for this pass

**You know it worked when:** Telemetry stops updating: the contact has ended. Compare the wall-clock time it stopped against the LOS in the plan; they should agree within a few seconds.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S16` and make it read: ```yaml - step: PROC-001-S16 role: PLAN operator: YOUR NAME state: completed records: observed_los_utc: '2026-07-29T14:44:02Z' computed_los_utc: '2026-07-29T14:44:00Z' last_cdh_frame_cnt: 4515 ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** `CDH_FRAME_CNT`
- **Records:** `observed_los_utc`, `computed_los_utc`, `last_cdh_frame_cnt`
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

### PROC-001-S17 — Ops Planner · LOS + 30 min

File the pass report to docs/pass_reports/, containing the pass plan, event timeline,
limit violations, actions with procedure step references, the per-step completion
record, and the disposition of anomalies (HUG-OPS-002).

```bash
python tools/pass_report.py --validate docs/pass_reports/<pass-id>/report.yaml
```

**Open:** docs/pass_reports/<pass-id>/report.yaml

**Run:**

```bash
python tools/pass_report.py --validate docs/pass_reports/<pass-id>/report.yaml
```

> `<pass-id>` — The pass identifier, form YYYY-MM-DD-Pn, read off campaign/CAMPAIGN_PLAN.md. The campaign's first pass is 2026-07-29-P1.

**You know it worked when:** `[PASS]` and a line confirming the record accounts for all 18 steps. If it prints findings, each names the step and what is missing - fix those entries and run it again. A report is filed when it validates, not when you have stopped typing.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S17` and make it read: ```yaml - step: PROC-001-S17 role: PLAN operator: YOUR NAME state: completed ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed.

- **Checks:** —
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

### PROC-001-S18 — Ops Planner · post-pass

Review the completion record against this procedure. A step with no entry, or an
applicable step without a completed or omitted entry, is an omission finding — record
and disposition it as an anomaly with corrective action.

**Open:** procedures/PROC-001.md - this document, beside your completed report

**Run:**

```bash
python tools/pass_report.py --validate docs/pass_reports/<pass-id>/report.yaml
```

> `<pass-id>` — The pass identifier, form YYYY-MM-DD-Pn, read off campaign/CAMPAIGN_PLAN.md. The campaign's first pass is 2026-07-29-P1.

**You know it worked when:** Read your record against this procedure, step by step. Any step with no entry, or an entry that claims more than you observed, is an omission finding and is recorded as one - `state: omitted` with an `anomaly:` reference, never deleted and never quietly upgraded.

**Write it down:** In your report, find the block that begins `- step: PROC-001-S18` and make it read: ```yaml - step: PROC-001-S18 role: PLAN operator: YOUR NAME state: completed branch: complete observation: what you saw that made you choose that branch ``` The values above are EXAMPLES showing the shape. Replace each with what you actually observed. `branch:` must be one of: 'complete', 'omission finding'.

- **Checks:** —
- **Applicability:** always. A completion record entry reading `not_applicable` for this step is itself a finding.

**Decision — Does the completion record account for every step of the governing procedure?**

| Outcome | The observation that selects it | Then |
|---|---|---|
| `complete` | tools/pass_report.py --validate exits zero: exactly one entry per step, every not-applicable entry carrying a basis, every completed decision step carrying its branch-selecting observation. | File the report. Post-pass review is closed. |
| `omission finding` | The validator names at least one step with no entry, a duplicate entry, a missing basis, or a decision entry with no branch-selecting observation. | Record the omission truthfully as an omitted entry — it is permanent for this pass and is never rewritten to completed. Disposition it as an anomaly with corrective action: re-execution at the next opportunity, recorded as a completed entry for the re-executed step and referenced from the omitted entry, or an explicit owner risk acceptance approved by the design authority and referenced from the omitted entry. |

> A completed entry for this step must record **which branch was taken and the observation that selected it**. An omitted entry must record that no observation was made and no branch was selected — those are different facts and the record keeps them apart (HUG-OPS-002).

