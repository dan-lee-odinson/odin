# Phase 3's seal

The phase-3 scenarios are **held out from ODIN's instruction development and runtime access** (CONTRACT.md §10.3). Claude Code wrote their files on 28 October 2026 from the Director's approved phase-3 document, and sealed them before ODIN's instructions freeze.

Only these hashes are in the repository. The files stay outside it until the held-out runs are complete. Then they are committed here, and the seal in force is checked.

The seal in force, of 29 October 2026, made when ODIN's phase-1 notes were frozen:

```
sha256:bc8ae4ace8a100486cc9b11bad17a4e818893e9d1363e3fc9eb4db4fabf6350e
```

The first seal, of 28 October 2026 (a20ad3f), kept beside it:

```
sha256:5d92af90e06031d9f6db889779e27c598766c0074cc1b635692c42431b9ea330
```

Each is the SHA-256 of the files' manifest, `MANIFEST.sha256`, which lists the SHA-256 of every sealed file, one per line, sorted by name. To check the seal in force: hash `MANIFEST.sha256` and compare it with its line above, then run `sha256sum -c MANIFEST.sha256` beside the files.

The second seal changes nothing but the phase-1 notes' hash (plans/ODIN-PH1-console-notes.md) in the seven plans, each plan's one line going from the placeholder of zeros to that hash (the Director's ruling of 28 October 2026). The held-out script that compares the two seals, run on the first seal's files, kept read-only, and the new ones, found exactly that: "the new seal changes only the phase-1 notes' hash in the plans", the manifest changing only in the plans' entries. Its self-test passed on planted changes too. So the scenarios themselves are as they were sealed on 28 October 2026, before ODIN's instructions froze.

A change found necessary before the held-out runs start means a new seal, reported to the Director, and this file then names the new hash. Nothing changes once the runs start.
