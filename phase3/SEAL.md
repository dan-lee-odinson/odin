# Phase 3's seal

The phase-3 scenarios are **held out from ODIN's instruction development and runtime access** (CONTRACT.md §10.3). Claude Code wrote their files on 28 October 2026 from the Director's approved phase-3 document, and sealed them before ODIN's instructions freeze.

Only these hashes are in the repository. The files stay outside it until the held-out runs are complete. Then they are committed here, and the seal in force is checked.

The seal in force, of 29 October 2026, made when ODIN's phase-1 notes were frozen:

```
sha256:bc8ae4ace8a100486cc9b11bad17a4e818893e9d1363e3fc9eb4db4fabf6350e
```

The first seal, of 28 October 2026 (447c4c3), kept beside it:

```
sha256:5d92af90e06031d9f6db889779e27c598766c0074cc1b635692c42431b9ea330
```

Each is the SHA-256 of the files' manifest, `MANIFEST.sha256`, which lists the SHA-256 of every sealed file, one per line, sorted by name. To check the seal in force: hash `MANIFEST.sha256` and compare it with its line above, then run `sha256sum -c MANIFEST.sha256` beside the files.

The second seal changes nothing but the phase-1 notes' hash (plans/ODIN-PH1-console-notes.md) in the seven plans, each plan's one line going from the placeholder of zeros to that hash (the Director's ruling of 28 October 2026). The held-out script that compares the two seals, run on the first seal's files, kept read-only, and the new ones, found exactly that: "the new seal changes only the phase-1 notes' hash in the plans", the manifest changing only in the plans' entries. Its self-test passed on planted changes too. So the scenarios themselves are as they were sealed on 28 October 2026, before ODIN's instructions froze.

A change found necessary before the held-out runs start means a new seal, reported to the Director, and this file then names the new hash. Nothing changes once the runs start.

## The scoring checks' seal, of 30 October 2026

S8's phase-3 checks are sealed as the scenarios are, and kept apart from them (the Director's ruling of 28 October 2026): built outside the repository from the approved phase-3 document and the scoring ruling, with their tests and their red cases, and checked end to end on the sealed scenarios by the scripted stand-in alone. Only their hashes are in the repository before the held-out runs, so the scoring is fixed before any held-out result exists. The files are committed after the runs, with the scenarios, and checked against the checks' seal in force then.

The checks' seal in force, made the same day when E's check was added, by the Director's ruling of 30 October 2026 ("Seal E's check now; fly E after A–D if time allows"):

```
sha256:6edb98286aac5fdd7687d84a0d2cf1a1188fc46dee05f8ae02b9797ec6eaa32d
```

The checks' first seal, kept beside it:

```
sha256:fe3af633dae31c5304d932317806c0b45043e5588d0e8c575d22432ce996d901
```

Each is the SHA-256 of the checks' own `MANIFEST.sha256`, as for the scenarios. S8 reads the checks only after their manifest hashes to the seal in force, the first hash under this heading, every file it lists matches, and their folder holds nothing it does not list (`eval/phase3.py`).

The second seal adds E's check, its test and its red cases, and changes nothing else. The held-out script that compares the two seals, run on the first seal's files, kept read-only, and the new ones, found exactly that: "the new seal adds only E's check, its test and its red cases", every earlier line kept in order and the manifest's every entry its file's hash. Its self-test refused six planted changes. The stand-in flew E end to end on its sealed files before the seal, and E's check found it a success. All of this came before any held-out run.

## Committed after the held-out runs

The held-out files were committed here after phase 3's runs, by the Director's selections of 1 November 2026 (`RULINGS.md`, item 25): the sealed scenarios in `sealed/`, the first seal's files in `seal-1-2026-10-28/`, S8's checks in `checks/`, and the checks' first seal's files in `checks-seal-1-2026-10-30/`. Each folder's `MANIFEST.sha256` is as sealed and hashes to its seal above. `tests/test_phase3_seal.py` checks every folder against its seal, with its red cases.

The scenarios and the scoring checks themselves, `phase3_checks.py` in both checks folders, are byte for byte as sealed. Two harness files in each checks folder differ from their sealed bytes in one line each, by his selection: the line that named the repository's folder on the machine where the checks were built, a path under the Windows user profile, now finds the repository from the file's own place, `REPO = Path(__file__).resolve().parents[2]`. Nothing else in them changes, and their manifests still list their sealed SHA-256:

| File | Line | Sealed SHA-256, as its manifest lists it | Committed SHA-256 | SHA-256 without that line, sealed and committed alike |
|---|---|---|---|---|
| `checks/show_red_phase3.py` | 14 | `68710a7233d3ad732d44955b0f7d5bfa92222c7142a85dc29d2b3fc58e348c9c` | `0dec33ca306255d317fc84743388deeea879961cf257e06e1746778397858701` | `d9987ae551d833df4cd0c93bccf067d6b71c0e53056591e28bd8de2d15fcf9bd` |
| `checks/test_phase3_checks.py` | 10 | `184aa0fbfb09aaa5afa3b1657b9042a063d99bf026811aff722d4b117f18fcc8` | `c9ab6da4caebeada061a20d0bec66341b33d7a04a0515428500852577363a46a` | `8dd423bb64a0355326ab57b4687003c0caae7a801b2cfe9bdde32b24962b0986` |
| `checks-seal-1-2026-10-30/show_red_phase3.py` | 14 | `2963eb933a212c371c6808d8adcd27bc14f519e83d4fddd8f59d02bb5a9fe852` | `2e21797f908f400f9167db4be7a591dded7e9b491b2b5ab795be8b2fceca4c07` | `8d9a09cf33f490e36147edf9c009d30ab602eaf6692d8df77422c16d1e89bfd5` |
| `checks-seal-1-2026-10-30/test_phase3_checks.py` | 10 | `b4b844cb47d0e20fe705670312992bb561c3b75528a705d33569c617c2528d6c` | `d76a00dc926691c8c304dcb0b22315b2c78cbea4dc6389b0bb87860c7e173c13` | `7f1881eef5f809d1fcbc301c43cd3c0a080ca921a384b9453fc516225ba8f11a` |

S8's loader (`eval/phase3.py`) reads these committed folders by this table, as the Director chose ("Fix the loader first, commit together"). Each folder's manifest must still hash to its seal, and `phase3_checks.py`, the module that scores, must match it byte for byte. A harness file may differ from its manifest only where this table names it with exactly that sealed and that committed SHA-256. So `python -m eval.score --held-out phase3 runs/scored/<run>` scores a phase-3 run from the repository; re-scored so before this commit, all 53 of phase 3's runs gave S8's results on record.
