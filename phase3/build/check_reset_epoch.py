"""Held out: a reset in each sealed phase-3 scenario shows its acknowledgement epoch, (CDH_CMD_ACC_CNT,
CDH_CMD_REJ_CNT) = (1, 0) in the first frame after it, when sent at the first tick of each contact, before the
seat has any frame, and through each housekeeping halt (the Director's word of 28 October 2026, on S5's live
check). Runs the repository's own check, tests/test_s6_outcome.py's reset_epochs, on the sealed files; writes
nothing, and nothing of it goes into the repository or anywhere Muse Code can read.

    python check_reset_epoch.py
"""

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SEALED = HERE.parent / "sealed"
REPO = Path.home() / "Documents" / "odin-build" / "odin"
sys.path.insert(0, str(REPO))

from tests.test_s6_outcome import reset_epochs  # noqa: E402
import wrapper.huginn  # noqa: E402,F401  (puts HUGINN's sim on the path)
from sim.scenario import Scenario  # noqa: E402


def main():
    failed = 0
    for label in ("H01", "H02", "H03", "H04", "H05"):
        plans = sorted(SEALED.glob(f"TYR0-{label}-C*-v1.yaml"))
        windows = sorted((p["contact_window"]["aos_met_s"], p["contact_window"]["los_met_s"])
                         for p in (yaml.safe_load(path.read_text(encoding="utf-8")) for path in plans))
        sealed = yaml.safe_load((SEALED / f"{label}.scenario.yaml").read_text(encoding="utf-8"))
        found = reset_epochs(Scenario(sealed["huginn"]), windows)
        bad = [item for item in found if item[1] != (1, 0)]
        failed += bool(bad) or not found
        halts = [at for at, _ in found if at not in {aos for aos, _ in windows}]
        print(f"{label}: contacts {windows}; resets checked {len(found)} "
              f"({len(found) - len(halts)} at a contact's first tick, {len(halts)} in halts); "
              f"{'every one (1, 0)' if not bad else f'NOT (1, 0): {bad}'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
