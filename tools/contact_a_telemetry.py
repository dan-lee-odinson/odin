"""Contact A's telemetry for PASS-2B (the Director's rulings of 27 October 2026, section 2).

    python tools/contact_a_telemetry.py            write the frozen file, once; refuses to overwrite it
    python tools/contact_a_telemetry.py --check    regenerate and compare with the frozen file

The Director carried contact A's observation forward into PASS-2B's contact. ODIN gets the same: the
frames the ground would have received from P2_array_string_loss in contact A, MET 2190 to 2519, with
HUGINN's scripted commands split by the U35 rule. It is data with no interpretation, one row per frame,
the 16 points in the dictionary's order, as COSMOS reads them: each number the shortest decimal that
reads back as the same 32-bit float, each state by its name. The simulator is deterministic, so the file
is the same every time it is made, and its hash is listed in the PASS-2B plan's references.
"""

import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wrapper.frames import POINTS  # noqa: E402
from wrapper.huginn import load_scenario  # noqa: E402
from wrapper.simulator import Simulator  # noqa: E402

SCENARIO = "P2_array_string_loss"
CONTACT_A = (2190, 2520)   # PASS-2A's contact window, MET [2190, 2520)
FROZEN = REPO_ROOT / "plans" / "TYR0-P2-PASS2B-v1.contact-a-telemetry.csv"


def float32_text(value):
    """The shortest decimal that reads back as the same 32-bit float."""
    bits = struct.pack("<f", value)
    for digits in range(1, 10):
        text = f"{value:.{digits}g}"
        if struct.pack("<f", float(text)) == bits:
            return text
    return repr(value)


def cell(name, value):
    return float32_text(value) if POINTS[name]["type"] == "float" else str(value)


def generate():
    """The file's bytes: a header row, then one row per frame stamped inside contact A."""
    simulator = Simulator(load_scenario(SCENARIO), windows=[CONTACT_A])
    rows = [",".join(POINTS)]
    while simulator.spacecraft.t_s < CONTACT_A[1]:
        if simulator.step() is not None and simulator.met_s >= CONTACT_A[0]:
            frame = simulator.tap.latest()
            rows.append(",".join(cell(name, frame[name]) for name in POINTS))
    return ("\n".join(rows) + "\n").encode("utf-8")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data = generate()
    if "--check" in argv:
        same = FROZEN.is_file() and FROZEN.read_bytes() == data
        print(f"{FROZEN.name}: " + ("matches its regeneration" if same else "DOES NOT match its regeneration"))
        return 0 if same else 1
    if FROZEN.exists():
        sys.exit(f"{FROZEN} is frozen; nothing was written. Use --check to compare it.")
    FROZEN.write_bytes(data)
    import hashlib
    print(f"wrote {FROZEN.name}: {len(data)} bytes, sha256:{hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
