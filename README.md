# ODIN

ODIN is Project AESIR's operational intelligence. In this build it flies a simulated CubeSat, HUGINN, through OpenC3 COSMOS. It acts inside an authority that deterministic code enforces (BALDUR-0, the gateway) and records that ODIN cannot write. Built for the Meta hackathon, 26 October to 4 November 2026.

> **Status: stage S1, the contract schemas.** This README is a stub. The full README, with reproduction instructions and the held-out wording, comes at stage S10.

The build contract is [`CONTRACT.md`](CONTRACT.md) (v0.6, 26 October 2026).

## Built Oct 26–Nov 4

Everything in this table is new, written from 26 October 2026 on. Rows are added as each stage lands.

| What | Where | Built by |
|---|---|---|
| Repository skeleton: folder layout, configuration, keys, licenses | repository root, `config/`, `keys/` | Claude Code |
| Repository tests: contract and rules hashes, signer fingerprint, HUGINN guard, secret scan, schema conformance, no unsettled schema field | `tests/` | Claude Code |
| Contract schemas: JSON Schema for the records and messages of the contract's §4–§9 and §16 and Addendum A-1, with examples | `contract/schemas/` | Claude Code |

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
