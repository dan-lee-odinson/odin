# ODIN

ODIN is Project AESIR's operational intelligence. In this build it flies a simulated CubeSat, HUGINN, through OpenC3 COSMOS. It acts inside an authority that deterministic code enforces (BALDUR-0, the gateway) and records that ODIN cannot write. Built for the Meta hackathon, 26 October to 4 November 2026.

> **Status: stage S4, the wrapper and link.** This README is a stub. The full README, with reproduction instructions and the held-out wording, comes at stage S10.

The build contract is [`CONTRACT.md`](CONTRACT.md) (v0.6, 26 October 2026).

## Built Oct 26–Nov 4

Everything in this table is new, written from 26 October 2026 on. Rows are added as each stage lands.

| What | Where | Built by |
|---|---|---|
| Repository skeleton: folder layout, configuration, keys, licenses | repository root, `config/`, `keys/` | Claude Code |
| Repository tests: contract and rules hashes, signer fingerprint, HUGINN guard, secret scan, schema conformance, no unsettled schema field, canonical JSON vectors, event log chain and head file, the log's endpoints, truth file kept apart, each Muse Code deposit committed as deposited, BALDUR-0's checks, recheck, revocation and restore, plan and act signatures in each mode, and its endpoints with ODIN's own signed requests; HUGINN unchanged and stepped frame for frame, the link, the onboard tap, HUGINN's scripted commands kept before a pass and dropped during one, the truth file's schema and compression, the run clock, and ODIN's COSMOS project | `tests/` | Claude Code |
| Contract schemas: JSON Schema for the records and messages of the contract's §4–§9 and §16 and Addendum A-1, with examples, and the code that checks documents against them | `contract/` | Claude Code |
| Event log: each run's append-only, hash-chained record with its head file, its chain check, canonical JSON, the log's two HTTP endpoints, and the truth file kept apart, with its schema and a scored run's gzip compression | `log/` | Claude Code |
| BALDUR-0, the gateway: verifies a run's plan chain and arming act with `ssh-keygen -Y verify`, decides each command request by the eight checks of the contract's §9.1, decides again before dispatch, applies revocation and the signed restore act, and serves POST /request and POST /escalation | `gateway/` | Claude Code |
| The simulator wrapper and link: HUGINN stepped unchanged one tick at a time; the link COSMOS dials, carrying frames down and commands up inside contact windows and nothing outside them, with a ground receiver that can drop frames while COSMOS stays connected; the onboard tap; the truth file; HUGINN's scripted commands kept outside a run's contacts and dropped inside them; and the run clock, real time or phase 3's pause and charge | `wrapper/` | Claude Code |
| ODIN's COSMOS: OpenC3 COSMOS 7.2.1 as its own Compose project, odin, with HUGINN's compose file and plugin unchanged, its credentials kept only as the Director's user environment variables | `connector/` | Claude Code |
| Workspace refresh: copies the shared files from main into Muse Code's workspace byte for byte and checks each copy by SHA-256 | `tools/` | Claude Code |
| ODIN's turn loop, answer check, input saving, request signing, model adapters, and a fake harness and fake BALDUR-0 for testing (milestone M1, deposit `MC-M1-01.zip`); the spend meter (milestone M2, deposit `MC-M2-01.zip` and its correction `MC-M2-02.zip`) | `odin/`, `keys/odin.pub` | Muse Code |

## Known limits

- **Secrets kept as user environment variables can be read by anything running as the Director.** COSMOS's credentials, the `ODIN_COSMOS_*` variables, are Windows user environment variables and are never written to a file. Muse Code's start command removes them from its own process, and whatever launches ODIN passes it no `ODIN_COSMOS_*` or `OPENC3_*` variable, so ODIN holds no ground-system credential (contract §9). But Windows keeps user variables in the registry, under `HKCU\Environment`, where any process running as the Director can read them, Muse Code's shell included. The same holds for the model API keys, `META_API_KEY` and `BASETEN_API_KEY`, when they are kept as user variables. The Director accepted this gap on 27 October 2026.

## Existed before

| What | Where | Version | Notes |
|---|---|---|---|
| HUGINN, a CubeSat mission operations simulator | `deps/huginn`, a git submodule of [dan-lee-odinson/huginn](https://github.com/dan-lee-odinson/huginn) | commit `b4dbe61`, 13 October 2026 | Used unchanged |
| OpenC3 COSMOS | Not in this repository | 7.2.1 | The ground system, run as its own Compose project |
| The Director's procedures, pass plans, console card and flown pass records | `inputs-pre-existing/` | Each file labeled with its date and source | Not yet added |

## Contributors

Dan Lee-Odinson is the only human contributor. Claude Code and Muse Code wrote code under his direction.

## License

Code: Apache License 2.0 ([`LICENSE`](LICENSE)). Documentation: CC BY 4.0 ([`LICENSE-docs`](LICENSE-docs)). See [`NOTICE`](NOTICE).
