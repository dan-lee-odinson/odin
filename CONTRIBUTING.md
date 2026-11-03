# Contributing

Thanks for looking. This file says how the project is run, when a change can be merged, what it needs first, and what a pull request cannot change.

## How decisions are made

The Director, Dan Lee-Odinson, directs this project and dispositions every design question; the code is written to his decisions, by Claude Code, by Muse Code and by contributors. For anything beyond a bug fix, open an issue first and say what you want to change and why. You will get a yes, a no, or a question, and a yes before you write the code saves both of us a rewrite.

## When pull requests are merged

Issues are welcome now. No pull request is merged before the live final on 9 November 2026, so the repository stays as it was submitted while it is judged.

## Setting up

Follow the README's "Reproducing the results": clone with HUGINN as a submodule, make a virtual environment, and install `requirements-dev.txt`. That is everything the tests need. They call no model, need no key, and never start COSMOS. The notebook in `notebooks/` has its own packages, pinned in `notebooks/requirements.txt`; the tests don't need them.

## Testing

Every change comes with tests, and the suite and the dry run must both be green before a pull request is opened:

    python -m pytest
    python tests/show_red.py

The suite takes about 15 minutes, and the dry run about 70. In a fresh clone three tests skip, each for something the repository does not hold, as the README says. One of them is the check of phase 1's dictionary against OpenC3's demo plugin, so its case in the dry run cannot fail there and is reported as not caught. That one report is expected in a clone without the plugin.

Three rules for tests, taken from how the project was built:

- A check is a callable that can fail. Verify by running it, never by reading the code it checks.
- Every check has a red case, seen failing before the check is trusted: a planted change that makes it fail, listed in `tests/show_red.py`.
- The dry run proves them. It plants each red case in the working tree, runs its test, which must fail, puts the tree back byte for byte and runs the test again. It exits 0 only if every case behaves.

## What a pull request needs

- An issue reference for anything that is not a plain bug fix.
- Tests with their red cases, a green suite and a green dry run.
- No secrets, keys or tokens, no user names and no private paths anywhere in the diff, the tests or the fixtures. Secrets come from environment variables only. The secret scan is part of the suite. Run the identity scan, `python tools/identity_scan.py`, on every file you add or change; it must find nothing.

By submitting a pull request you agree that your contribution is licensed as the README's License section says: code under the Apache License 2.0, as section 5 of the license provides; the animation scripts in `render/` under the GNU GPL, version 3 or later (`render/LICENSE.md`); and documentation under CC BY 4.0 (`LICENSE-docs`).

## What won't change in a pull request

Some behavior is the point of the project and is not up for change in a pull request:

- Every command passes BALDUR-0, and nothing commands the spacecraft directly.
- Mission plans and arming acts are signed by the Director.
- The event log is hash-chained, and ODIN cannot write to it.
- The tests call no model and need no key.

A change that weakens any of these will be declined. If you think one of them is wrong, open an issue and make the case.

## Reporting a security problem

Do not open a public issue. [`SECURITY.md`](SECURITY.md) says what counts and how to report it.
