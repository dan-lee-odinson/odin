# The Director's pre-existing inputs

Placed 27 October 2026 by the Director's rulings of that day, section 4, each copied byte for byte from
the source named and scanned first for private identity details (`tools/identity_scan.py`), which found
none. HUGINN's command and telemetry dictionary was added on 28 October 2026 by the Director's ruling of
that day. ODIN sees these through its turn bundles: the procedures as the plans in force name them, and
the pass plans, the console card and the dictionary as the plans' references list them. A file's date is
the date of the record, or of the commit that last changed it at the source.

| File | Dated | Source | SHA-256 |
|---|---|---|---|
| `procedures/v0.1/PROC-001.md` | 2026-08-09 | the Director's private HUGINN repository, commit 5b49075, procedures/PROC-001.md | `sha256:d4ca4b3464fa1f7b1499fd7ba11368d2ec035b8771926e619d35a70898e35746` |
| `procedures/v0.1/PROC-002.md` | 2026-08-09 | the Director's private HUGINN repository, commit 5b49075, procedures/PROC-002.md | `sha256:894affab98219145c58bf8bf588f564085cee10d3233cac4589ab467615e384e` |
| `procedures/v0.1/PROC-003.md` | 2026-08-09 | the Director's private HUGINN repository, commit 5b49075, procedures/PROC-003.md | `sha256:3c5b94823ab160e8f4da7fdb28c849237b5e3b2edbd9ec6e082f95227defa609` |
| `procedures/v0.2/PROC-001.md` | 2026-10-11 | the Director's private HUGINN repository, commit 552231e, procedures/PROC-001.md | `sha256:f4cba5ccdedbf2da02237bb680667aa4645ea4f68757c03c4f704347b7f95d2d` |
| `procedures/v0.2/PROC-002.md` | 2026-10-11 | the Director's private HUGINN repository, commit 552231e, procedures/PROC-002.md | `sha256:433e406984f38d5d9a91f2aece7176ad4eb22f94ffe7b13286271fe255eee013` |
| `procedures/v0.2/PROC-003.md` | 2026-10-11 | the Director's private HUGINN repository, commit 552231e, procedures/PROC-003.md | `sha256:45627e4a449dfd283d307f3ec7d44c7c4acc448b1d3646b4af325a21a2e9ba6f` |
| `procedures/v0.3/PROC-001.md` | 2026-10-11 | HUGINN e75569f, procedures/PROC-001.md | `sha256:b3948ee03d483f6d949290e42ea0f3264d8a94921c559406c23b68b40a4cd498` |
| `procedures/v0.3/PROC-002.md` | 2026-10-11 | HUGINN e75569f, procedures/PROC-002.md | `sha256:69de35f8724665f84ca709f0019b11488bcc21585ab2b395af8025d108af9241` |
| `procedures/v0.3/PROC-003.md` | 2026-10-11 | HUGINN e75569f, procedures/PROC-003.md | `sha256:5f8f776aec2c7a3082e99097d428607c5b4b84204b8a062cb367cbd8433caeab` |
| `pass-plans/2026-10-11-P3_pass_plan.md` | 2026-10-11 | HUGINN e75569f, docs/pass_reports/2026-10-11-P3/pass_plan.md | `sha256:d6c934ff1193f9a7ca1ec443a68918f6edb65e525422dd0796fdefcffaabd87d` |
| `pass-plans/2026-10-11-P4_pass_plan.md` | 2026-10-11 | HUGINN e75569f, docs/pass_reports/2026-10-11-P4/pass_plan.md | `sha256:fd915c96e9dde5428d3d7720f736284f553d60963ac2d2a1ffebd99db6eacbdf` |
| `dictionary/tlm_cmd_dictionary_v0.5.md` | 2026-07-29 | pre-existing: HUGINN dictionary v0.5 of 29 July 2026, HUGINN b4dbe61, docs/tlm_cmd_dictionary.md | `sha256:985105875e6e41c4896cd635efbd15fe037349da228027261cc7ce059c930648` |
| `console-card/HUGINN_CONSOLE_CARD_2026-10-11.html` | 2026-10-11 | the Director's kept copy, ODIN\console-card\ | `sha256:c063de2c646ddc41ed751df8413cf052beb5b52ac10819b9c8f1e348e7ecb083` |

Procedures v0.1 and v0.2 come from the Director's private HUGINN repository, by his ruling of 27 October
2026: his D: backup did not hold them. Each file was read with `git show` at the commit named, with no
checkout, and is the version in force when its passes were flown, the last commit to change the
procedures before each pass record's `executed_utc`:

| Passes | `executed_utc` | Last change before it | Version line |
|---|---|---|---|
| 2026-09-13-P1, 2026-09-20-P2a, 2026-09-20-P2b | 2026-09-13T18:58:06Z to 2026-09-20T21:38:31Z | 5b49075a49325b76bbd3063c7edf06d75ef7bf67, 2026-08-09T22:46:50-04:00 | 0.1 |
| 2026-10-11-P3 | 2026-10-11T16:58:41Z | 552231e8592e142893c9a36334df4783afaf6de3, 2026-10-11T12:17:59-04:00 | 0.2 |
| 2026-10-11-P4 | 2026-10-11T19:58:29Z | f6cd7d390bd389cdf046c428c4fd1f839bbae2e4, 2026-10-11T15:16:16-04:00 | 0.3 |

PASS-3's and PASS-4's records name their procedures version, and PASS-2B's names the v0.1 campaign;
PASS-1's and PASS-2A's name none and flew the same files as PASS-2B. Every file names the dictionary
digest the five records name, 5e1c2750ef9e0d54. v0.2's PROC-002-S02 carries the D-017 red-line PASS-3's
record names: a load alarm on EPS_LOAD_I goes to S03. The v0.3 in force for PASS-4 is byte for byte the
v0.3 above from HUGINN e75569f. No other branch of the repository changes the procedures.

Not here, by the rulings:
- **The console card of 27 October** goes nowhere in the repository: it carries PASS-3's and PASS-4's
  faults and their answers.
- **The Director's pass reports, flown records and AR-001 to AR-003** are in
  `comparison-only/`, used only to score ODIN, and never shown to ODIN or Muse Code.
