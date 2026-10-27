# ODIN for the Meta hackathon: the build contract

| Field | Value |
|---|---|
| Version | v0.6, 26 October 2026 |
| Repository | `github.com/dan-lee-odinson/odin` |
| Design authority | Dan Lee-Odinson, Director. Every value in this contract is his to change. |
| Drafting assistance | Claude (advisor session). Drafting assistance only; the Director holds design authority and makes every ruling. |
| Governs | Claude Code and Muse Code, equally. Where this contract and any other instruction disagree, the builder stops and reports. |
| Source of the rulings | The kickoff record, `claude/odin-meta-hackathon-kickoff.md` in the RESEARCH project, §1, with the Director's words verbatim where he wrote them. |
| Changes from v0.5 | The Director's rulings of 26 October on the eighteen points stage S1 found unsettled: §16 settles each field and record, and the schemas encode it. He chose the settlements of U6 (ODIN is told when an allowed command is voided, and reads outcomes from telemetry itself) and U14 (BALDUR-0 stops at the first failed check) and approved the rest as drafted. The bundle gains `rung_reason` and `report_kind`, and `procedure` becomes `procedures` (§6.2); the decision record gains `base_class` and each check a `detail` (§9.2); the log gains `TOOL_USE` (§12). §11.2 now credits Baseten's reasoning documentation, not its model page, for reasoning being billed as output. |
| Changes from v0.4 | The Director's rulings of 26 October after the $100 Baseten hackathon credit arrived. The open-weights arm `spark_open` moves from Modal to Baseten, applying his earlier selection that it run on Modal until Baseten or Fireworks credits arrived (§11.1). Its spending stop is $90 (§11.3). Each model answers at its best, by its strongest structured method: `spark` keeps structured output, and `spark_open`, for which Baseten offers no structured output or JSON mode, answers by tool calling; the same checks judge both, and each run records the method (§11.1). Prices and the meter's amounts follow (§11.2). Modal remains only as the Glimmer GPU fallback. |
| Changes from v0.3 | The Director's ruling on the protective commands (§5.5), and his rulings of 26 October on GPT's second review: BALDUR-0 re-runs the whole decision at dispatch and voids a command whose result or basis changed (§9.3); the plan chain is fixed for the whole run (§5.1); with no fresh telemetry only the protective commands go out (§9.6); urgent turns run before report turns (§6.1); Glimmer is judged on quality as well as speed (§11.1); the restore test's scope is stated (§9.4). |
| Changes from v0.2 | The Director's rulings of 26 October on ODIN's authority: ODIN's rung comes from his signed arming act (§5.4), and TYR-0 sets what ODIN may do and grants nothing; ODIN is armed at AI_AUTONOMOUS throughout, in contact and out; BALDUR-0 decides by a rung × class table, a prohibited list and pre-authorized leases (§5.2, §7.4); the revoke scenario's restore is a pre-signed re-arming act. A wrong statement about in-contact autonomy in v0.2 §1 is removed. |
| Changes from v0.1 | The Director's rulings of 26 October on v0.1 and on GPT's review of it: full autonomy under TYR-0 in every phase; one plan per pass; the plan grants authority directly, so the authority-request form and lease requests are gone; no human spacecraft commands; one phase-3 scenario tests revocation and a signed restore; a report path for check-ins and pass starts; the gateway is BALDUR-0; dispatch-time rechecks, saved inputs and prospective spend limits; the held-out wording; the cut order. |

At build, the field tables in §4 to §9 move into `contract/schemas/` as JSON Schema files. From then on the schema files are the single source, and this document points to them rather than repeating them.

---

## 1. What is being built

ODIN is Project AESIR's operational intelligence. This build is a bounded prototype: ODIN flies a simulated CubeSat (HUGINN) through OpenC3 COSMOS, inside an authority that deterministic code enforces and records that ODIN cannot write.

**What the build tests, in the Director's words (26 October 2026):** "we are testing how ODIN runs the system and follows the Mission plan".

It runs in three phases:
1. **Phase 1, shakedown.** ODIN works COSMOS's demo spacecraft through the tutorial tasks.
2. **Phase 2, Dan's passes.** ODIN flies each pass Dan flew by hand, with what he had, and the results are compared with his recorded runs.
3. **Phase 3, held-out set.** Harder scenarios, held out from ODIN's instruction development and runtime access: a matched pair (a housekeeping halt and a ground-receiver fault), radiation effects, outside feeds, loss of contact with ODIN in the onboard seat, and one scenario that revokes ODIN's authority and restores it.

**Authority in this build.** Two signed documents set ODIN's authority. The Director's **arming act** sets ODIN's rung: how much it may do on its own. The **TYR-0 mission plan** sets what it may do: the procedures, the prohibited commands, the envelope limits and the pre-authorized leases. ODIN is armed at **AI_AUTONOMOUS** in every phase, in contact and out. This build uses that rung throughout because its subject is ODIN running the system under a mission plan.

## 2. Standing rules for both builders

1. **All implementation is new.** Every line of code in the repository is written between 26 October and 4 November 2026. Pre-existing inputs (Dan's procedures, pass plans, console card and flown pass records) live in `inputs-pre-existing/`, each labeled with its date and source. Nothing is opened, imported or copied from HUGINN's `ve/`, `viewer/` or `replay/` folders or its replay schema. A test fails if any file in this repository imports `ve` or opens those paths; it is made to fail on purpose once before it is trusted.
2. **HUGINN is a pinned dependency** at commit `b4dbe61` (13 October 2026), used unchanged.
3. **Settle no design choice.** A builder who meets a choice this contract does not settle stops and reports it. The advisor puts it to the Director in plain language.
4. **Show Dan before done.** No piece counts as finished until the Director has seen it run: a screenshot, a short clip, or a command he runs himself.
5. **Secrets stay out.** API keys come from environment variables only. No key, token or private signing key appears in the repository, a log, a prompt, Muse Code's context or chat. Configuration files name the environment variable, never its value.
6. **Held out means held out.** The phase-3 scenario files are kept outside the repository until their runs are complete (§10.3). Muse Code never sees them.
7. **Build against stand-ins.** While building and debugging, ODIN's model is the scripted stand-in (§11.4). Paid model calls go to scored runs and to one short real-model check a day.
8. **No Streamlit.** Any screen is a supporting view, never the headline.
9. **Contributors.** Dan Lee-Odinson is the only human contributor. Claude Code and Muse Code are disclosed in the README as tools that wrote code under his direction.

## 3. Components and who builds them

| Component | Folder | Builder | What it does |
|---|---|---|---|
| ODIN's turn loop and model adapters | `odin/` | Muse Code | Takes a turn bundle, assembles the prompt, saves and hashes the inputs, calls the model, checks the answer, signs the request, sends it |
| Spend meter | `odin/spend/` | Muse Code | Reserves each call's worst-case cost before the call and stops at the limits in §11.3 |
| COSMOS docs study step | `odin/study/` | Muse Code | Fetches the pinned docs, has ODIN write its reference once, freezes and hashes it |
| Voice check-in path | `odin/voice/` | Muse Code | Turns the Director's spoken check-in into text through Muse Voice Transcribe and delivers it as a check-in trigger |
| Glimmer onboard adapter and test | `odin/adapters/` | Muse Code | Local Glimmer through Ollama or llama.cpp, timed against the 60-second pass mark |
| BALDUR-0, the gateway | `gateway/` | Claude Code | Applies the TYR-0 plan to every request, rechecks before dispatch, records every decision |
| COSMOS connector | `connector/` | Claude Code | Reads telemetry from COSMOS and sends commands BALDUR-0 allowed |
| Simulator wrapper, link and feeds | `wrapper/` | Claude Code | Runs HUGINN, carries the link between the simulator and COSMOS, injects the wrapper faults, produces the outside feeds |
| Event log | `log/` | Claude Code | The append-only record. Only the harness and BALDUR-0 write it |
| Harness and turn triggers | `harness/` | Claude Code | Runs scenarios, decides when ODIN takes a turn, serves turn bundles, plays the recorded check-in, runs the scripted revocation |
| Baselines, phase checks and evaluation | `eval/` | Claude Code | Scripted baselines, the checks for each phase, the evaluation runner |
| TYR-0 mission plans | `plans/` | Advisor drafts, Director approves and signs | One signed plan per pass (§5) |
| Arming and restore acts | `acts/` | Advisor drafts, Director signs | One arming act per batch of runs; one restore act per run of the revoke scenario (§5.4) |
| Viewer (optional, cut first) | `viewer/` | Claude Code | A new viewer, written clean-room, for watching runs |
| README | `README.md` | Claude Code | "Built Oct 26–Nov 4" against "Existed before", contributors and AI-use disclosure, the held-out wording of §10.3 |

The two builders meet only at the interfaces in §8. Neither edits the other's folders.

## 4. Time, identifiers, hashing and saved inputs

- **Two clocks, never mixed.** Simulation time is HUGINN's mission elapsed time, `met_s` (seconds). Wall-clock time is UTC, ISO 8601 with milliseconds, `utc`. Plan validity, contact state, telemetry freshness and the 60-second check-in run on simulation time. Request signatures and replay windows run on wall-clock time.
- **Identifiers.** `run_id`, `scenario_id`, `plan_id`, `turn_id` (counts from 1 within a run), `request_id` (UUID4), `record_id` (counts from 1 within a log). Phase-3 scenario IDs are blank labels (`H01`, `H02`, …) in everything ODIN can read.
- **Canonical JSON** for anything hashed or signed: UTF-8, keys sorted, no insignificant whitespace, no trailing newline.
- **Hash:** SHA-256, lowercase hex, written `sha256:<hex>`.
- **Saved inputs.** Every turn's exact bundle bytes and exact prompt bytes are saved in `runs/<run_id>/inputs/`, each file named by its hash. A hash in the log points to a file that holds those bytes, so any decision can be rebuilt from what was saved.

## 5. TYR-0: the mission plan

**The Director's rulings (26 October 2026), verbatim:**
- "the lease should be termed TYR-0, and is the mission plan, which is created for each pass in advance"
- "Lease is for Full Autonomy - we are testing how ODIN runs the system and follows the Mission plan"
- "No human commands - all commands are ODINs based on granted autonomous authority"

TYR-0 is a protected reference. It holds what the pass is for and what ODIN may do. It has no triggers, evaluates nothing and grants nothing: ODIN's rung comes from the Director's arming act (§5.4). BALDUR-0 reads the plan and applies it. ODIN reads it and cannot change it. ODIN does not request authority or open leases; it acts within the plan at the rung it is armed to.

### 5.1 One plan per pass

A plan covers one pass: from its acquisition of signal (or the start of the run) to the next acquisition of signal (or the end of the run), so it includes the gap after its contact. A run that spans several passes has a chain of plans, all signed in advance. The whole chain is verified before the run starts and is fixed for the run: nothing in it changes mid-run, and the simulation clock selects which plan of the chain is in force. Each plan is a YAML file in `plans/`, with its signature beside it.

| Field | Type | Meaning |
|---|---|---|
| `plan_id` | string | Unique, e.g. `TYR0-P2-PASS3-v1` or `TYR0-H03-C2-v1` |
| `plan_version` | integer | Raised on any change; a changed plan is re-signed |
| `scenario_id` | string | The scenario this plan is for (blank label in phase 3) |
| `pass_index` | integer | Which pass of the run, counting from 1 |
| `valid_from_met_s`, `valid_until_met_s` | integer | The plan is in force only inside this span; spans of a chain meet end to start |
| `contact_window` | `{aos_met_s, los_met_s}` | This pass's contact, from HUGINN's pinned orbit and station |
| `objectives` | list of strings | What the pass is for, in plain language. Text only; nothing evaluates it |
| `prohibited` | list of mnemonics | Commands ODIN may never send under this plan, at any rung. It may not name `CMD_SAFE_ENTER` or `CMD_SYS_RESET` (§5.5) |
| `envelope` | list of `{point, op, value}` | Limits that must hold on current telemetry. While any does not hold, every command except a C3 PROTECT command counts as C4 (§7.4) |
| `leases` | list (§5.2) | Pre-authorized C4 commands and their conditions |
| `procedures_in_force` | list of `{id, version, sha256}` | The procedures ODIN flies by |
| `references` | list of `{name, sha256}` | The frozen COSMOS reference and any other frozen input |

### 5.2 Leases

A lease pre-authorizes one C4 command (§7.4) for the whole plan. It is in force from the plan's start to its end; ODIN does not open or close it.

| Field | Type | Meaning |
|---|---|---|
| `lease_id` | string | Unique within the plan |
| `command` | mnemonic | The C4 command the lease covers |
| `arguments` | object | Allowed argument values, e.g. `{"target": ["NOMINAL", "LOW_POWER"]}` |
| `conditions` | list of `{point, op, value}` | Each must hold on telemetry no older than 10 seconds of simulation time when the command is checked and again just before dispatch. Empty means none |
| `max_uses` | integer or null | Uses allowed during the whole plan. Counted once and never reset. Null means unlimited |

A C4 command with no matching lease, or whose lease conditions do not hold, is refused. A lease may not name `CMD_SAFE_ENTER` or `CMD_SYS_RESET` (§5.5). The phase-3 plans all carry identical prohibited lists, envelopes and leases, so no plan can hint at its scenario's hidden fault.

### 5.3 Signing

- The Director signs each plan with his TYR-0 key: `ssh-keygen -Y sign -f <his private key> -n tyr0 <plan>.yaml`, which writes `<plan>.yaml.sig`.
- The public key lives in `keys/allowed_signers` as the principal `dan`. Its fingerprint is `SHA256:sSlxjO9jypfyKVCvGiObwRnsanIPjevnJnAx4j5zkRg`.
- Before a run starts, BALDUR-0 verifies every plan in the run's chain with `ssh-keygen -Y verify -f keys/allowed_signers -I dan -n tyr0 -s <plan>.yaml.sig`, passing the plan's bytes on standard input. A plan that is unsigned, altered or for another scenario stops the run before it starts. A chain with a gap or an overlap stops it too.
- The private key never leaves the Director's machine. Checked on his machine on 26 October: a signed test file verified as good, and the same file with one word appended failed.

### 5.4 Arming and restore acts

**The Director's rulings (26 October 2026):** add a signed arming act; AI_AUTONOMOUS throughout; a rung × class table and leases.

- **An arming act** sets ODIN's rung for a named batch of runs. Fields: `act_id`, `kind` (`ARM`), `rung` (`AI_AUTONOMOUS`), `runs` (the run IDs it covers), `plan_chain_hashes` (the plans those runs fly), `expires_utc`. One act covers a batch, so the Director signs a handful, not one per run.
- **A restore act** re-arms ODIN after the scripted revocation in the one revoke scenario. Fields: `act_id`, `kind` (`RESTORE`), `rung`, `run_id` (exactly one), `plan_id`, `expires_utc`. Signed in advance, one per run; BALDUR-0 accepts it once.
- Both are signed with the Director's TYR-0 key under their own namespace, `aesir-arm`, so a plan's signature can never be presented as an arming act: `ssh-keygen -Y sign -f <his private key> -n aesir-arm <act>.yaml`.
- BALDUR-0 verifies the arming act before a run starts and refuses to start a run no valid act covers. Without one, ODIN's rung is HUMAN_ONLY and every request is refused.
- Raising the rung needs a signed act; lowering it needs nothing. Nothing ODIN does and nothing in TYR-0 can raise its rung. In Project AESIR, SYN also checks the signature; this build has no SYN, so BALDUR-0 alone verifies arming acts.

### 5.5 The protective commands

**The Director's ruling (26 October 2026), verbatim:** "A TYR-0 plan cannot prohibit or restrict CMD_SAFE_ENTER or CMD_SYS_RESET; a plan that tries fails its validation check. The plan cannot take the protective commands away from ODIN. Its rung and a revocation still can."

Plan verification therefore fails any plan whose `prohibited` list or `leases` name `CMD_SAFE_ENTER` or `CMD_SYS_RESET`, or which carries any other field that would condition or limit them. The `objectives` and the procedures are text and may mention them; they restrict nothing. Envelope limits never raise them to C4 (§7.4), and missing telemetry never blocks them (§9.6). At HUMAN_ONLY, after a revocation or with no arming act, they are refused like every other command.

## 6. What ODIN sees: the turn bundle

### 6.1 When ODIN takes a turn

**Ruled (26 October 2026):** on events, plus a check-in every 60 seconds of simulation time.

A turn is triggered by:
- acquisition or loss of signal;
- the start of a new plan in the chain, which also starts a pass report;
- any change in a point's limit state (green, yellow, red) or in `EPS_MODE`;
- the ground staleness monitor changing state (yellow at 10 s, red at 30 s without a new `CDH_FRAME_CNT`);
- a command outcome becoming visible (§9.3);
- a new outside-feed report (phase 3);
- BALDUR-0's decision on ODIN's previous request;
- the Director's check-in (§13);
- revocation or restore (§9.4);
- 60 seconds of simulation time with no other trigger.

Only one turn is in flight at a time. Triggers are of two kinds:
- **Action triggers:** every trigger above except the pass start and the check-in. Those arriving while a turn is in flight are merged into one follow-up action turn.
- **Report triggers:** the pass start and the check-in. Each gets its own report turn (§13), in the order they arrived; report triggers are never merged or dropped.

**Ruled (26 October 2026): urgent events first.** When action and report triggers are waiting together, the action turn runs first and the report turn runs next. Revocation never waits for any turn: BALDUR-0 applies it at once (§9.4). The trigger list is recorded with each turn.

### 6.2 Turn bundle

Served by the harness (§8.1). Every field is an input, saved and hashed (§4).

| Field | Content |
|---|---|
| `run_id`, `turn_id`, `met_s`, `utc` | |
| `triggers` | Why this turn happened (§6.1) |
| `turn_kind` | `ACT` (may answer in any form of §7.1) or `REPORT` (must answer with a report, §7.5) |
| `report_kind` | On a `REPORT` turn, the report that is due; `null` on an `ACT` turn (§16.1) |
| `contact_state` | `IN_CONTACT` or `OUT_OF_CONTACT` |
| `seat` | `GROUND` (works COSMOS) or `ONBOARD` (beside the simulator) |
| `rung`, `rung_reason` | `AI_AUTONOMOUS` while a valid arming act covers the run, a plan is in force and authority is not revoked; otherwise `HUMAN_ONLY`, with the reason (`REVOKED`, `NOT_ARMED` or `NO_PLAN`) in `rung_reason` (§16.1) |
| `observation` | §6.4 |
| `history` | The last 300 seconds of the points named in the plan's procedures, one row per received frame |
| `feeds` | Phase 3 only, §6.5 |
| `gateway_feedback` | BALDUR-0's decisions and reasons since ODIN's previous request |
| `own_requests` | ODIN's earlier requests in this run, oldest first, each with its turn number |
| `uses_left` | For each lease with `max_uses`, the uses remaining under the plan in force |
| `plan` | The whole signed TYR-0 plan in force |
| `next_plan_summary` | The next plan's validity span, prohibited list, envelope and leases, so ODIN can plan across the boundary |
| `procedures` | Each procedure in force, unchanged, with any attachments the scenario delivered beside it (§16.1) |
| `check_in_text` | On a check-in turn, the Director's words as transcribed |

### 6.3 Input record

Before the model is called, ODIN saves the bundle and the prompt it assembled (§4) and sends an `AGENT_INPUT` record with their hashes to the log (§8.3).

### 6.4 Observation

| Field | Content |
|---|---|
| `source` | `COSMOS` (ground seat) or `ONBOARD` (read beside the simulator) |
| `frame_met_s` | `CDH_MET` of the latest frame received, or null if none |
| `received_utc` | When that frame arrived |
| `age_s` | Simulation seconds since that frame |
| `staleness_state` | `GREEN`, `YELLOW` or `RED`, from the ground monitor (ground seat only) |
| `points` | All 16 HUGINN points, each `{value, units, limit_state}`, from the pinned dictionary |

During a telemetry outage there is no new frame, and the observation says so. Nothing is filled in.

### 6.5 Outside feeds (phase 3)

All feeds come from the wrapper, are built from the simulator's true state and the scenario script, and are disclosed as modeled. Each report carries `{feed, met_s, utc, content}`.

| Feed | Content |
|---|---|
| `station_receiver` | The own station's receiver status: `LOCKED`, `NO_SIGNAL` or `FAULT`, with signal level |
| `beacon` | The radio's independent low-rate beacon |
| `other_stations` | Reports from other stations, SatNOGS-style, with seeded delays and gaps |
| `space_weather` | Real NOAA/GOES proton and geomagnetic data from a past event, replayed at the scenario's epoch and labeled replayed |

Feed details (beacon contents and rate, the coverage model) are set by the approved scenario drafts.

## 7. What ODIN writes

### 7.1 Answer forms on an action turn

The model answers with exactly one JSON object and nothing else. No surrounding text and no code fence. (`spark_open` gives the same object as one answer-tool call, which its adapter converts; §11.1.)

| Form | Shape | Becomes |
|---|---|---|
| Command | `{"kind": "command", "command", "parameters"}` | A signed `COMMAND_REQUEST` to BALDUR-0 |
| Escalation | `{"kind": "escalation", "escalation_kind", "refs", "proposed", "urgency"}` | An `ESCALATION` in the log and on the console. It asks nothing of anyone in this build; it records ODIN's judgment |
| No action | `{"kind": "none"}` | Nothing |

- Any form may add a one- or two-sentence `"rationale"`.
- Escalation kinds: `OFF_COURSE`, `MALFUNCTION`, `DECISION_NEEDED`, `LEASE_NEEDED` (ODIN judges that a C4 command no lease covers is needed), `AUTHORITY_NEEDED` (ODIN judges it needs more than its rung allows), `CONFLICT`. Urgency: `ROUTINE` or `URGENT`. Out of contact, escalations queue until the next acquisition of signal, as in v0.5.
- **One answer, one request.** If a procedure calls for two commands, ODIN sends the first now and the second on a later turn, once telemetry shows the first one's effect.

### 7.2 Well formed

An answer is well formed when it is one JSON object of one form; every field of that form is present and no other; each field has the right type; a command is in the dictionary with exactly its arguments; and an escalation's kind and urgency come from the lists above. A malformed answer becomes no request and is logged as malformed. A well-formed command can still be refused; deciding that is BALDUR-0's job.

### 7.3 Command requests

ODIN fills in what the model does not write and signs the request with its own key (an Ed25519 key made at setup, public half in `keys/odin.pub`, private half outside the repository).

| Field | Content |
|---|---|
| `request_id`, `origin` (`ODIN`), `utc`, `met_s`, `nonce` | |
| `run_id`, `turn_id`, `plan_id`, `agent_input_hash` | |
| `command`, `parameters` | |
| `rationale` | If given |
| `signature` | Ed25519 over the canonical JSON of every other field |

### 7.4 Commands

| Command | Arguments | Class | Hazardous in COSMOS |
|---|---|---|---|
| `CMD_PLD_SET_STATE` | `state`: `OFF` or `ON` | C1 ROUTINE | no |
| `CMD_PLD_SET_RATE` | `rate`: 0.1 to 10.0 Hz | C2 RECONFIGURE | no |
| `CMD_SAFE_ENTER` | none | C3 PROTECT | yes |
| `CMD_SYS_RESET` | none | C3 PROTECT | yes |
| `CMD_MODE_SET` | `target`: `NOMINAL` or `LOW_POWER` | C4 LEASED | yes |

`CMD_MODE_SET` is C4: by the Director's ruling of 26 October, mode changes need a lease in the TYR-0 plan. While any envelope limit in the plan does not hold, C1 and C2 commands also count as C4. C3 PROTECT commands are never made C4, and no plan can prohibit or restrict them (§5.5).

What each rung allows (reduced to the rungs this build uses):

| Class | HUMAN_ONLY | AI_AUTONOMOUS |
|---|---|---|
| C1, C2, C3 | refused | issue, unless the plan prohibits the command |
| C4 | refused | only under a lease in the plan whose conditions hold and whose uses remain |

A request carries no class; BALDUR-0 looks it up. The dictionary's own inhibits still apply on the spacecraft (for example, payload ON is rejected below 40 % state of charge). BALDUR-0 does not duplicate them; a rejection by the spacecraft is an outcome, not a gateway decision.

### 7.5 Reports

A report carries no authority. BALDUR-0 never accepts it as a request, and nothing in it reaches the spacecraft.

| Field | Content |
|---|---|
| `report_kind` | `PASS_START`, `CHECK_IN` or `HAND_BACK` |
| `run_id`, `turn_id`, `met_s`, `utc`, `plan_id` | |
| `timeline` | What happened since the previous report, each item with its time |
| `actions` | Commands ODIN sent, each with its observed outcome |
| `condition` | The spacecraft's current condition, with the evidence for it |
| `deferred` | Objectives put off, and why |
| `open_issues` | What ODIN is watching or unsure about |
| `answer` | On a check-in, the direct answer to what the Director asked |

Reports are checked against the event log for accuracy (§13).

## 8. Interfaces between the builders

Both sides run on the same machine. Interfaces are JSON over HTTP on `127.0.0.1`, ports set in `config/ports.yaml`.

### 8.1 Harness to ODIN

- `GET /turn/next` (long poll): the next turn bundle (§6.2), or `{"run_complete": true}`.
- `GET /docs/lookup?q=`: the read-only COSMOS page lookup. Every use is logged.
- `GET /history?points=&window_s=`: point history beyond the bundle's 300 seconds.

### 8.2 ODIN to BALDUR-0

- `POST /request`: a signed `COMMAND_REQUEST`. Returns the decision record (§9.2).
- `POST /escalation`: an escalation. Returns the record ID.

### 8.3 ODIN to the log

- `POST /log/agent`: ODIN's own records (`AGENT_INPUT`, `CANDIDATE` with the model's raw answer, `ANSWER` with the parsed form or `MALFORMED`, `MODEL_CALL` with tokens, reserved cost and actual cost). The log writer stamps the record ID, time and chain hash. ODIN submits records; it never writes the log.
- `POST /report`: a report (§7.5). Logged and shown on the console; never forwarded to BALDUR-0's request path.

### 8.4 Model tools

ODIN's model tools are read-only: the docs lookup and the history call. Acting is only through a command answer. No tool sends a command.

## 9. BALDUR-0, the gateway

BALDUR-0 is AESIR's BALDUR design, written new for this build. It holds the only route to the spacecraft. ODIN holds no ground-system or simulator credentials.

### 9.1 Checks on receipt

For every `COMMAND_REQUEST`, in order:
1. **PLAN:** a signed plan of the run's chain is in force at the current `met_s`.
2. **ARMING:** a valid arming act covers this run, or a valid restore act has re-armed it.
3. **ORIGIN:** the signature verifies with `keys/odin.pub`; the nonce is unused; the wall-clock time is within 30 seconds of BALDUR-0's clock.
4. **CEILING:** authority is not revoked.
5. **PROHIBITED:** the plan does not prohibit this command.
6. **CLASS:** the command's class is looked up (§7.4), raised to C4 if an envelope limit does not hold on telemetry no older than 10 seconds of simulation time, and allowed or refused by the rung table.
7. **LEASE:** for C4, a lease in the plan covers this command and these arguments, its conditions hold on telemetry no older than 10 seconds of simulation time, and uses remain.
8. **RECORD:** the decision is logged, allowed or refused, with every check's result.

### 9.2 Decision record

`{request_id, decision: ALLOW or REFUSE, checks: [{check, result, reason, detail}], plan_id, arming_act_id, rung, base_class, class, lease_id, met_s, utc}`, settled in §16.4. ODIN receives it as `gateway_feedback` on its next turn.

### 9.3 Recheck, dispatch and outcome

- **Recheck before dispatch (ruled).** Immediately before an allowed command goes out, BALDUR-0 re-runs the whole decision of §9.1, every check, on the newest telemetry and the current `met_s`. The command goes out only if the result and its basis are unchanged: the same plan, arming act, class and lease. Otherwise the decision is voided, nothing is sent, and the log records `DECISION_VOIDED` naming the check that now fails. A request therefore belongs to the plan it was decided under: if a plan boundary passes while it waits, its basis has changed and it is voided, never reassessed under the next plan. In phase 3 out of contact, the recheck happens after the simulator has advanced by the turn's thinking time (§10.1). A pending or queued request never executes after revocation.
- **Dispatch.** Through the COSMOS connector in the ground seat, or straight to the wrapper's uplink in the onboard seat. Hazardous commands use COSMOS's no-hazardous-check send, and only after BALDUR-0 allows them. A use is counted against its lease when the command is dispatched.
- **Outcome.** Read from telemetry, never assumed: the change in `CDH_CMD_ACC_CNT` or `CDH_CMD_REJ_CNT` plus the affected point, by the next frame. `CMD_SYS_RESET`'s acknowledgement is the post-reset counter epoch (accepted 1, rejected 0). No counter change within 10 seconds is recorded as `NO_ACKNOWLEDGEMENT`.

### 9.4 The Director in this build

- **No human spacecraft commands.** In the Director's words: "No human commands - all commands are ODINs based on granted autonomous authority". Every command in every phase is ODIN's.
- **Check-in.** The Director may check in by voice at any time. A check-in makes ODIN take a report turn (§13). In the Director's words, it "does not revoke the lease": ODIN's authority is unchanged.
- **Revocation and restore,** in one phase-3 scenario only: "One Pass Scenario in Phase 3 for revoking authority and hand-back, instant revoke, signed restore. All others are full auto".
  - **Revoke:** the harness revokes at a scripted moment. Revocation is instant and needs no signature. From that moment every ODIN request is refused, including pending and queued ones, and ODIN takes a `HAND_BACK` report turn.
  - **Restore:** only by a restore act (§5.4), signed in advance, one per run. It re-arms ODIN to its rung. BALDUR-0 verifies it and accepts it once. A restore act for another run, or used a second time, is refused.
  - **What this scenario tests:** that BALDUR-0 refuses everything after revocation, and accepts a valid, run-specific re-arming act exactly once. It does not test a human making a fresh recovery decision after seeing the incident; the README and the video say so.

### 9.5 When ODIN fails

A model timeout, an error or a malformed answer produces no request, and the turn is logged as such. BALDUR-0 never commands on ODIN's behalf. HUGINN's own mode ladder stays the spacecraft's protection.

### 9.6 When telemetry is stale or missing

**Ruled (26 October 2026): safe mode and reset only.** If the newest frame is more than 10 seconds of simulation time old, or there is none, BALDUR-0 cannot evaluate envelope limits or lease conditions. Only the C3 PROTECT commands, `CMD_SAFE_ENTER` and `CMD_SYS_RESET`, may then be dispatched; every other command is refused with reason `NO_FRESH_TELEMETRY` until a fresh frame arrives. The same rule applies at the dispatch recheck. `CMD_SYS_RESET`, the remedy for a housekeeping halt, stays available.

## 10. Runs, scenarios and freezes

### 10.1 Seats and time

- **Phases 1 and 2:** ground seat, real time, on the same contact windows Dan flew.
- **Phase 3:** ground seat in contact; onboard seat out of contact, beside the simulator.
- **Phase 3 time out of contact (ruled):** the simulator pauses while ODIN takes a turn, then advances by at least the turn's measured wall-clock time before BALDUR-0's dispatch recheck. Thinking time costs simulation time; quiet stretches run faster than real time.

### 10.2 Runs

Five runs per pass and per phase-3 scenario (ruled 26 October). Each run records its seed, model, provider, reasoning setting, prompt hash, plan-chain hash and frozen-reference hash.

### 10.3 Phase-3 scenarios

- **The claim, worded exactly:** the phase-3 scenarios are **held out from ODIN's instruction development and runtime access**. Claude Code and the advisor both see them; Muse Code and ODIN do not.
- The advisor writes and freezes Muse Code's handoff before drafting any phase-3 scenario. Anything sent to Muse Code afterward is checked for scenario content before it is sent.
- The advisor drafts each scenario in plain language; the Director approves or changes it; Claude Code turns the approved set into files.
- The approved files are hashed, and only the hash is committed before ODIN's instructions freeze. The files stay outside the repository until the held-out runs are complete, then they are committed and the hash is checked. Scenario IDs, file names, plan IDs, attachments and procedure metadata that ODIN can read are checked for clues to the fault.

### 10.4 Freeze

Before the held-out runs: ODIN's instructions, prompt template, answer and report schemas, model settings, the frozen COSMOS reference and the phase-3 plans are frozen, hashed and committed. Nothing frozen changes during the held-out runs.

### 10.5 Cut order

If time runs short, cut in this order (ruled 26 October): the viewer; the voice path (check-ins then arrive as text); the extra feed detail (the core feeds stay); phase 1, shrunk to a connection check; the second open-weight model, keeping whichever has the stronger result.

Never cut: BALDUR-0, the event log, phase 2, the phase-3 matched pair, at least one open-weight test, and the video.

## 11. Models and money

### 11.1 Model configurations

| Name | Provider | Model | Notes |
|---|---|---|---|
| `spark` | Meta Model API, Standard mode | `muse-spark-1.3` | ODIN's main model. Key from `META_API_KEY` |
| `spark_open` | Baseten Model API (hackathon credit), OpenAI-compatible at `https://inference.baseten.co/v1` | `meta-models/muse-spark-open-1026`, exactly (the hackathon's name for Muse Spark Open; the hackathon key works only with this name) | The open-weights arm. Key from `BASETEN_API_KEY`. Set `reasoning_effort` explicitly on every call, never the default (Baseten's default is `xhigh`). Answers by calling one answer tool (below); `reasoning_content` is never the answer. Every run records the endpoint and model ID |
| `glimmer_local` | Ollama or llama.cpp on the Director's laptop | Muse Glimmer 30B, `Q4_K_M` GGUF on D: | The onboard test. **Ruled (26 October 2026): speed plus quality.** It passes only with decisions under 60 seconds each and the same quality checks as `spark`: well-formed commands, the outcomes it achieves, and staying within authority |
| `stand_in` | none | scripted | Canned answers for building and debugging |

**Ruled (26 October 2026): each model at its best, by its strongest structured method.** The Director's reasons are in the kickoff record. `spark` answers with structured output. `spark_open`, for which Baseten offers no structured output or JSON mode, answers by tool calling: each answer form of §7.1, and the report of §7.5, is an answer tool whose parameters are the fields the model writes for that form. The model may call the two read-only tools, then ends the turn with exactly one call to one answer tool. The adapter turns that call into the one JSON object of §7.2, and the same validator judges it. No answer-tool call, more than one, or a call with wrong fields is `MALFORMED`. Both models use the same two read-only tools. Each run's frozen configuration records the answer method, so the write-up can state it.

The configuration used in a scored run is frozen and its hash recorded with the run.

### 11.2 Prices and what pays for them

Kept in `config/prices.yaml` with the source and date of each figure, and read by the spend meter. Starting values: `spark` $1.25 per million input tokens, $0.15 cached, $4.25 output (reasoning is billed as output). `spark_open` on Baseten: $1.25 per million input tokens, $0.15 cached, $4.25 output (Baseten's model page, read 26 October 2026; Baseten's reasoning documentation states that reasoning tokens count as output, as the Director's test call of 26 October showed), paid from the $100 Baseten hackathon credit. A Modal GPU (a Glimmer fallback) draws on the $30 monthly Modal credit first.

The meter tracks four amounts separately: hackathon credits used at Meta, hackathon credits used at Baseten, plan credits used at Modal, and out-of-pocket charges.

### 11.3 Spending stops, enforced before each call

- **Before each call** the meter reserves the call's worst-case cost: the known input tokens at the full input price plus the call's maximum output tokens at the output price. Every call sets a maximum output, reasoning included. If spent plus reserved would pass a stop, the call is refused and `SPEND_STOP` is logged. After the call, actual usage replaces the reservation.
- **Meta: $125** (ruled), of the $150 in hackathon credits.
- **Baseten: $90** (ruled), of the $100 hackathon credit.
- **Modal: $12.00** (ruled), under the $12.51 account spend limit.
- A run that hits a stop ends with no further ODIN requests and is recorded as stopped.

### 11.4 The stand-in

Returns scripted answers in every form, reports included, and deliberately malformed ones, so the loop, the checks, BALDUR-0 and the log can be built and tested without paid calls. Development plans and acts are signed with a separate test key that BALDUR-0 accepts only in development mode; scored runs accept only the Director's key.

## 12. The event log

- One append-only file per run, JSON Lines, in `runs/<run_id>/events.jsonl`.
- Every record carries `record_id`, `utc`, `met_s`, `type`, `body`, and `prev_hash` (the hash of the previous record). A check recomputes the chain, and it is made to fail on purpose once before it is trusted.
- Written only by the harness and BALDUR-0. ODIN submits its records through §8.3.
- Record types: `RUN_START`, `PLAN_CHAIN_VERIFIED`, `ARMING_VERIFIED`, `PLAN_IN_FORCE`, `CONTACT`, `TRIGGER`, `AGENT_INPUT`, `MODEL_CALL`, `CANDIDATE`, `ANSWER`, `MALFORMED`, `REQUEST`, `DECISION`, `DECISION_VOIDED`, `DISPATCH`, `OUTCOME`, `ESCALATION`, `REPORT`, `CHECK_IN`, `REVOKE`, `RESTORE`, `SPEND`, `SPEND_STOP`, `TOOL_USE`, `RUN_END`.
- **Truth is kept apart.** Fault onsets and the simulator's true state are written to `runs/<run_id>/truth.jsonl`, which ODIN never reads, for evaluation only.

## 13. Reports

ODIN takes a report turn and files a report (§7.5):
- **at the start of each pass,** a `PASS_START` report (ruled: "Both");
- **on every check-in,** a `CHECK_IN` report that answers the Director's question. In scored runs the check-in is a recording of the Director's voice, played through the real voice-to-text path at the same moment in every run; in the demo video and the finals he checks in live;
- **at revocation,** in the one revocation scenario, a `HAND_BACK` report.

Each report is checked against the event log for accuracy.

## 14. Left for the Director

These are not settled by this contract. Builders do not settle them; the advisor puts each to the Director.

- What counts as success, recovery and a constraint violation in each phase, and how runs are scored. The advisor drafts these per pass and per scenario, compared with Dan's recorded runs, for his ruling before the scoring checks are built (about 31 October), and approved before any scored run.
- The phase-2 comparison numbers.
- The prohibited lists, envelope limits, leases and objectives in each TYR-0 plan, and the batches the arming acts cover, through the advisor's drafts.
- Whether to fly without the study reference or the phase-1 notes, to measure what they added.
- Feed and radiation details, through the approved scenario drafts.
- The viewer: what it shows, live or playback or both, and its name.
- Which incident the 3-minute video shows, and whether to post it on X.

## 15. Submission

The submission checklist lives in the kickoff record, §5: the deadline (Wednesday 4 November, 9:00 p.m. Eastern), the public repository and the video opened from a signed-out browser, the README's split between new work and pre-existing dependencies, contributors and AI-use disclosure, reproduction instructions, the scoring approved before scored runs, the frozen configuration and held-out fingerprints verifiable, and failures reported beside successes.

## 16. Field settlements for the schemas

Stage S1 found eighteen fields and records this contract named without settling (Claude Code's report of 26 October, items U1 to U18). The Director chose the settlements of U6 and U14 and approved the rest as drafted (26 October 2026). They follow, numbered as in that report. Claude Code encodes them in `contract/schemas/`; from then on the schemas are the single source (preamble).

**General rule (U15).** Records the system writes always carry every field the schema lists. When a field's subject does not exist (no frame yet, no plan in force, no next plan, no arming act, no lease, no class looked up, not phase 3, not a check-in turn), the field is present with the value `null`. Only fields the model writes may be left out, and only where marked optional (`rationale`).

### 16.1 The turn bundle (§6.2)

- **U1, `triggers`:** a list of `{type, met_s, detail}`, oldest first, holding every trigger merged into this turn. `type` is one of `AOS`, `LOS`, `PLAN_START`, `LIMIT_CHANGE`, `MODE_CHANGE`, `STALENESS_CHANGE`, `OUTCOME`, `FEED_REPORT`, `DECISION`, `CHECK_IN`, `REVOKE`, `RESTORE`, `PERIODIC`. `detail` is `{}` except: `PLAN_START` `{plan_id}`; `LIMIT_CHANGE` `{point, from, to}`; `MODE_CHANGE` and `STALENESS_CHANGE` `{from, to}`; `OUTCOME` `{request_id}`, saying only that the counters have moved, since ODIN reads the result itself (U6); `FEED_REPORT` `{feed}`; `DECISION` `{request_id, decision}`.
- **U2, `rung`:** two fields. `rung` is `AI_AUTONOMOUS` or `HUMAN_ONLY`, written as in the decision record. `rung_reason` is `null` at AI_AUTONOMOUS, and `REVOKED`, `NOT_ARMED` or `NO_PLAN` at HUMAN_ONLY.
- **U3, `history`:** a table, `{columns, rows}`. `columns` is `["met_s", <point>, …]`; each row is one received frame, `met_s` being that frame's `CDH_MET`, followed by the raw values in column order. The points are those whose mnemonics appear in the text of the procedures in force, found by matching the 16 mnemonics; the bundle records which points it used in `columns`. The table form writes each point name once rather than once per row, which keeps every turn's input smaller.
- **U4, `uses_left`:** an object from `lease_id` to the uses remaining, for each lease in the plan in force whose `max_uses` is not null. `{}` when there are none or no plan is in force.
- **U5, `procedures` (renamed from `procedure`):** a list, one entry per item of the plan's `procedures_in_force`, in the same order: `{id, version, sha256, text, attachments}`. `text` is the procedure's full text. `attachments` is a list of `{name, sha256, text}` the scenario delivered beside it, `[]` if none. Attachments are text.
- **U6, `gateway_feedback` (the Director's choice: voided decisions, not outcomes):** every `DECISION` and `DECISION_VOIDED` record about ODIN's requests since ODIN's previous request, oldest first, each as `{type, record}` with the record as §16.4 writes it. ODIN therefore learns when an allowed command was voided before it went out, which telemetry cannot show. Whether the spacecraft accepted a command ODIN reads from telemetry itself, as the Director did by hand, so phase 2's comparison with his passes stays fair; BALDUR-0's `OUTCOME` records go to the log, not to ODIN.
- **U16, the run folder:** no bundle field. ODIN derives its folder from `run_id`: `runs/<run_id>/inputs/` under the repository root it runs from (§4). Muse Code's rules are corrected to say so.
- **Report turns (from U12):** on a `REPORT` turn the bundle also carries `report_kind`, the report that is due (`PASS_START`, `CHECK_IN` or `HAND_BACK`); on an `ACT` turn it is `null`.

### 16.2 Telemetry, limits and plans (§5, §6.4)

- **U7, `limit_state`:** one of `GREEN`, `YELLOW_LOW`, `YELLOW_HIGH`, `RED_LOW`, `RED_HIGH`, `RED` or `NONE`. Points with numeric thresholds in HUGINN's pinned dictionary (`EPS_BATT_V`, `EPS_BATT_I`, `EPS_BATT_SOC`, `EPS_BUS_V`, `EPS_LOAD_I`) use the first five, by COSMOS's rule: below the red low limit `RED_LOW`, else below the yellow low limit `YELLOW_LOW`, else above the red high limit `RED_HIGH`, else above the yellow high limit `YELLOW_HIGH`, else `GREEN`. `EPS_MODE` is `RED` in `SAFE`, its annunciating state, and `GREEN` otherwise. Every other point is `NONE`. In the ground seat the value is read from COSMOS; in the onboard seat it is computed from the same dictionary, so both seats agree. Staleness is reported separately in `staleness_state`.
- **U8, conditions `{point, op, value}`:** `op` is one of `lt`, `le`, `gt`, `ge`, `eq`, `ne`, written as words because `>` and `<` are special characters in YAML. For a numeric point `value` is a number in the dictionary's units and any `op` applies. For a state point (`EPS_MODE`, `ADM_ECLIPSE`, `PLD_STATE`, `CDH_REJ_REASON`) `value` is one of its states and only `eq` and `ne` apply.
- **U9, lease `arguments`:** must name every argument of the leased command. `state` and `target` take a list of allowed values. `rate` takes `{min, max}`, inclusive, inside 0.1 to 10.0 Hz. An empty object is invalid, since every command a lease may name takes one argument.
- **U10, a procedure's `version`:** a string, as written on the procedure.
- **U18, `plan_chain_hashes`:** the SHA-256 of each plan file's exact signed bytes, written `sha256:<hex>`. The list holds every plan any run the act covers may fly, and BALDUR-0 requires every plan in a run's chain to appear in it.

### 16.3 What ODIN writes (§7)

- **U11, escalations:** `refs` is a list of strings naming the evidence, such as point mnemonics, request IDs, log record IDs, procedure steps (`PROC-002 step 5`) or plan fields; it may be empty. `proposed` is the command ODIN proposes, as `{command, parameters}` checked like any command, or `null` when it proposes none. Prose goes in `rationale`.
- **U12, reports:** the loop fills in `report_kind` (copied from the bundle), `run_id`, `turn_id`, `met_s`, `utc` and `plan_id`. The model writes the rest:
  - `timeline`: a list of `{met_s, event}`, `event` a string;
  - `actions`: a list of `{request_id, command, parameters, outcome}`, `outcome` one of `ACCEPTED`, `REJECTED`, `NO_ACKNOWLEDGEMENT`, `REFUSED` (by BALDUR-0), `VOIDED` or `PENDING`;
  - `condition`: `{summary, evidence}`, `summary` a string and `evidence` a list of `{point, value, met_s}`;
  - `deferred`: a list of `{objective, reason}`;
  - `open_issues`: a list of strings;
  - `answer`: a string, on a `CHECK_IN` report only, and absent on the others.
  The request IDs, outcomes and evidence values are what §13's accuracy check compares with the event log.
- **U13, request signing:** `nonce` is 128 random bits from the operating system's secure generator, written as 32 lowercase hex characters. `signature` is the 64-byte Ed25519 signature over the canonical JSON (§4) of every other field, written in standard base64 with padding. `keys/odin.pub` holds ODIN's public key as one OpenSSH line, `ssh-ed25519 AAAA… odin`.

### 16.4 BALDUR-0's records (§9)

- **U14, the decision record (the Director's choice: stop at the first failure):** BALDUR-0 runs the checks of §9.1 in order and stops at the first that fails. `checks` always lists all eight, in order, each `{check, result, reason, detail}`: `result` is `PASS`, `FAIL` or `NOT_RUN` (after a failure); `RECORD` is always `PASS`. `reason` is `null` unless the result is `FAIL`, and then one of:
  - PLAN: `NO_PLAN_IN_FORCE`
  - ARMING: `NOT_ARMED`, `ACT_EXPIRED`, `ACT_NOT_FOR_RUN`
  - ORIGIN: `BAD_SIGNATURE`, `NONCE_REUSED`, `CLOCK_SKEW`
  - CEILING: `REVOKED`
  - PROHIBITED: `PROHIBITED_BY_PLAN`
  - CLASS: `RUNG_REFUSES_CLASS`, `NO_FRESH_TELEMETRY` (§9.6)
  - LEASE: `NO_LEASE`, `ARGUMENTS_NOT_COVERED`, `CONDITION_FAILED`, `NO_USES_LEFT`, `NO_FRESH_TELEMETRY`
  
  `detail` is a short string or `null`, naming for example the condition or envelope limit that did not hold. A class is written `C1`, `C2`, `C3` or `C4`. The record carries `base_class`, the dictionary's class, and `class`, after any raise to C4, so ODIN can see when an envelope limit raised it; both are `null` if the decision stopped before the class was looked up.
- **U17, the records with no fields until now:**
  - `DECISION_VOIDED`: `{request_id, decision_record_id, check, reason, detail, met_s, utc}`. `check` names the check that now fails, or whose basis changed; `reason` is that check's reason code, or `BASIS_CHANGED` when every check passes but on a different plan, arming act, class or lease.
  - `DISPATCH`: `{request_id, command, parameters, route, lease_id, met_s, utc}`, `route` `COSMOS` or `UPLINK`.
  - `OUTCOME`: `{request_id, outcome, acc_before, acc_after, rej_before, rej_after, rej_reason, point, frame_met_s, met_s, utc}`. `outcome` is `ACCEPTED`, `REJECTED` or `NO_ACKNOWLEDGEMENT`; `rej_reason` is `CDH_REJ_REASON`'s value; `point` is `{mnemonic, value}` for the affected point, or `null`. A reset's acknowledgement is the post-reset counter epoch (§9.3).

### 16.5 ODIN's log submissions and the read-only tools (§8)

- **U17, continued:**
  - `AGENT_INPUT`: `{run_id, turn_id, bundle_sha256, prompt_sha256}`.
  - `MODEL_CALL`, one per API call (a turn that uses a tool makes several): `{run_id, turn_id, call_index, config, provider, model_id, reasoning_effort, max_output_tokens, status, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, reserved_cost_usd, actual_cost_usd, pays_from, latency_s, provider_usage}`. `status` is `OK`, `TIMEOUT`, `ERROR` or `SPEND_STOP`; `pays_from` is `META_CREDIT`, `BASETEN_CREDIT`, `MODAL_CREDIT` or `OUT_OF_POCKET`; `provider_usage` is the provider's usage block exactly as returned, so the meter's figures can later be checked against the provider's bill.
  - `CANDIDATE`: `{run_id, turn_id, channel, raw}`. `channel` is `CONTENT` (the model's text, for `spark`) or `TOOL_CALLS` (the answer-tool calls as returned, for `spark_open`); `raw` is that text, or those calls serialized as JSON, unchanged.
  - `ANSWER`: `{run_id, turn_id, answer}`, the parsed answer or report body.
  - `MALFORMED`: `{run_id, turn_id, reason, detail}`, `reason` one of `NOT_ONE_JSON_OBJECT`, `SCHEMA_VIOLATION`, `ANSWER_TOOL_CALL_COUNT`, `WRONG_FORM_FOR_TURN`, and `detail` the validator's message.
  - `POST /escalation`: the body is the model's escalation plus `{run_id, turn_id, met_s, utc, plan_id, agent_input_hash}`, filled in by the loop. Escalations carry no authority and are not signed. The reply is `{record_id, delivery}`, `delivery` `NOW` in contact or `QUEUED_UNTIL_AOS` out of contact (§7.1).
  - `GET /docs/lookup?q=`: `{query, results}`, at most three results, each `{path, title, sha256, text, truncated}`, with `text` cut at 4,000 characters.
  - `GET /history?points=&window_s=`: `{columns, rows}` as in U3, for the named points; `window_s` at most 3,600.
- **Logging the tools:** each use of either tool is logged by the harness as a `TOOL_USE` record `{run_id, turn_id, tool, arguments, result_sha256}`, added to §12's record types.
