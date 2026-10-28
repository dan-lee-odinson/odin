# ODIN

ODIN is Project AESIR's operational intelligence. In this build it flies a simulated CubeSat, HUGINN, through OpenC3 COSMOS. It acts inside an authority that deterministic code enforces (BALDUR-0, the gateway) and records that ODIN cannot write. Built for the Meta hackathon, 26 October to 4 November 2026.

> **Status: stage S6, the harness, done against Muse Code's stand-in on 27 October 2026; its ground seat waits for S5, the COSMOS connector. S4 closed the same day after its live pass against ODIN's COSMOS.** This README is a stub. The full README, with reproduction instructions and the held-out wording, comes at stage S10.

The build contract is [`CONTRACT.md`](CONTRACT.md) (v0.6, 26 October 2026).

## Built Oct 26–Nov 4

Everything in this table is new, written from 26 October 2026 on. Rows are added as each stage lands.

| What | Where | Built by |
|---|---|---|
| Repository skeleton: folder layout, configuration, keys, licenses | repository root, `config/`, `keys/` | Claude Code |
| Repository tests: contract and rules hashes, signer fingerprint, HUGINN guard, secret scan, schema conformance, no unsettled schema field, canonical JSON vectors, event log chain and head file, the log's endpoints, truth file kept apart, each Muse Code deposit committed as deposited, BALDUR-0's checks, recheck, revocation and restore, plan and act signatures in each mode, and its endpoints with ODIN's own signed requests; HUGINN unchanged and stepped frame for frame, the link, the onboard tap, HUGINN's scripted commands kept before a pass and dropped during one, the truth file's schema and compression, the run clock, and ODIN's COSMOS project; the Director's pre-existing inputs, the phase-2 plans and the arming acts; the harness's triggers, bundles, attachments, tools, check-ins, revocation, run folders and launcher, BALDUR-0's outcomes read from telemetry, and a stand-in run of a full pass with Muse Code's turn loop | `tests/` | Claude Code |
| Contract schemas: JSON Schema for the records and messages of the contract's §4–§9 and §16 and Addendum A-1, with examples, and the code that checks documents against them | `contract/` | Claude Code |
| Event log: each run's append-only, hash-chained record with its head file, its chain check, canonical JSON, the log's two HTTP endpoints, and the truth file kept apart, with its schema and a scored run's gzip compression | `log/` | Claude Code |
| BALDUR-0, the gateway: verifies a run's plan chain and arming act with `ssh-keygen -Y verify`, decides each command request by the eight checks of the contract's §9.1, decides again before dispatch, applies revocation and the signed restore act, reads each command's outcome from telemetry, and serves POST /request and POST /escalation | `gateway/` | Claude Code |
| The simulator wrapper and link: HUGINN stepped unchanged one tick at a time; the link COSMOS dials, carrying frames down and commands up inside contact windows and nothing outside them, with a ground receiver that can drop frames while COSMOS stays connected; the onboard tap; the truth file; HUGINN's scripted commands kept outside a run's contacts and dropped inside them; and the run clock, real time or phase 3's pause and charge | `wrapper/` | Claude Code |
| The harness: decides when ODIN takes a turn, the action turn first and a report waiting only behind the action triggers that arrived before it or with it; serves the turn bundles, with every reference a plan lists attached beside PROC-001; answers the docs lookup over Muse Code's cache and the history call; takes check-ins and plays recorded ones; runs the scripted revocation and restore; runs each run from its chain's first valid_from to its last valid_until and moves its folder to `runs/scored/` or `runs/dev/` when it stops; and launches ODIN with no COSMOS credential | `harness/` | Claude Code |
| ODIN's COSMOS: OpenC3 COSMOS 7.2.1 as its own Compose project, odin, with HUGINN's compose file and plugin unchanged, its credentials kept only as the Director's user environment variables. Local mode is the one setting where it differs from HUGINN's COSMOS: it is off, because HUGINN's plugin folder is read-only to ODIN's COSMOS and local mode would copy plugins and saved settings into it. Beside that, only its project name, address and ports differ | `connector/` | Claude Code |
| Workspace refresh: copies the shared files from main into Muse Code's workspace byte for byte and checks each copy by SHA-256; the identity scan the Director's records pass before they are added; and the generator of contact A's telemetry for PASS-2B | `tools/` | Claude Code |
| The phase-2 TYR-0 plans and the six arming acts for phases 1 and 2, unsigned until the Director signs them after phase 1; contact A's telemetry for PASS-2B, regenerated from HUGINN and frozen | `plans/`, `acts/` | The advisor drafted the plans and acts and the Director approved them; Claude Code placed them and made contact A's telemetry |
| ODIN's turn loop, answer check, input saving, request signing, model adapters, and a fake harness and fake BALDUR-0 for testing (milestone M1, deposit `MC-M1-01.zip`); the spend meter (milestone M2, deposit `MC-M2-01.zip` and its correction `MC-M2-02.zip`) | `odin/`, `keys/odin.pub` | Muse Code |

## Known limits

- **Secrets kept as user environment variables can be read by anything running as the Director.** COSMOS's credentials, the `ODIN_COSMOS_*` variables, are Windows user environment variables and are never written to a file. Muse Code's start command removes them from its own process, and whatever launches ODIN passes it no `ODIN_COSMOS_*` or `OPENC3_*` variable, so ODIN holds no ground-system credential (contract §9). But Windows keeps user variables in the registry, under `HKCU\Environment`, where any process running as the Director can read them, Muse Code's shell included. The same holds for the model API keys, `META_API_KEY` and `BASETEN_API_KEY`, when they are kept as user variables. The Director accepted this gap on 27 October 2026.
- **Recorded check-ins are transcribed once.** In scored runs each recorded check-in goes through Muse Code's real voice-to-text path once, and its transcript is frozen with its audio's hash and delivered at its MET in every run. The contract's §13 has the recording played through the voice path in every run; the Director ruled otherwise on 27 October 2026 (U44), so every run hears the same words. The demo video and the finals use the voice path live.

## Existed before

| What | Where | Version | Notes |
|---|---|---|---|
| HUGINN, a CubeSat mission operations simulator | `deps/huginn`, a git submodule of [dan-lee-odinson/huginn](https://github.com/dan-lee-odinson/huginn) | commit `b4dbe61`, 13 October 2026 | Used unchanged |
| OpenC3 COSMOS | Not in this repository | 7.2.1 | The ground system, run as its own Compose project |
| The Director's procedures, pass plans, console card and flown pass records | `inputs-pre-existing/` | Each file labeled with its date, source and SHA-256 in `SOURCES.md` | Added 27 October 2026 after an identity scan that found nothing: procedures v0.1, v0.2 and v0.3 as flown, the PASS-3 and PASS-4 pass plans and the console card of 11 October, which ODIN sees; the flown records, AR-001 to AR-003 and the learning log in `comparison-only/`, which it does not. Procedures v0.1 and v0.2 come from the Director's private HUGINN repository, v0.3 from HUGINN commit `e75569f` |

## Contributors

Dan Lee-Odinson is the only human contributor. Claude Code and Muse Code wrote code under his direction.

## License

Code: Apache License 2.0 ([`LICENSE`](LICENSE)). Documentation: CC BY 4.0 ([`LICENSE-docs`](LICENSE-docs)). See [`NOTICE`](NOTICE).
