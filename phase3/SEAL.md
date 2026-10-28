# Phase 3's seal

The phase-3 scenarios are **held out from ODIN's instruction development and runtime access** (CONTRACT.md §10.3). Claude Code wrote their files on 28 October 2026 from the Director's approved phase-3 document, and sealed them before ODIN's instructions freeze.

Only this hash is in the repository. The files stay outside it until the held-out runs are complete. Then they are committed here, and this hash is checked.

```
sha256:5d92af90e06031d9f6db889779e27c598766c0074cc1b635692c42431b9ea330
```

This is the SHA-256 of the files' manifest, `MANIFEST.sha256`, which lists the SHA-256 of every sealed file, one per line, sorted by name. To check it: hash `MANIFEST.sha256` and compare it with the line above, then run `sha256sum -c MANIFEST.sha256` beside the files.

A change found necessary before the held-out runs start means a new seal, reported to the Director, and this file then names the new hash. Nothing changes once the runs start.
