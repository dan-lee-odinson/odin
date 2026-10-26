"""Show each S0 repository test failing on purpose in the real working tree, then put it back.

    python tests/show_red.py

For each case: run the real test (it passes), plant one defect, run it again (it must fail),
restore the tree, confirm the restored bytes, and run it a third time (it passes). Planted
files are named _red_probe* and are git-ignored. Exits 0 only if every case behaves.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def change_file(rel, change):
    path = ROOT / rel
    original = path.read_bytes()

    def plant():
        path.write_bytes(change(original))

    def restore():
        path.write_bytes(original)
        return path.read_bytes() == original

    return plant, restore


def add_file(rel, text):
    path = ROOT / rel

    def plant():
        if path.exists():
            sys.exit(f"{rel} already exists; remove it before running this")
        path.write_text(text, encoding="utf-8")

    def restore():
        path.unlink(missing_ok=True)
        return not path.exists()

    return plant, restore


def flip_one_key_character(data):
    principal, keytype, key, comment = data.decode("utf-8").split(" ", 3)
    swapped = "B" if key[30] != "B" else "C"
    return " ".join([principal, keytype, key[:30] + swapped + key[31:], comment]).encode("utf-8")


# The planted text is assembled from pieces so that this file does not trip the scans.
CASES = [
    ("CONTRACT.md with one byte appended",
     "tests/test_s0_hashes.py::test_contract_hash",
     change_file("CONTRACT.md", lambda b: b + b" ")),
    (".agents/AGENTS.md with one byte appended",
     "tests/test_s0_hashes.py::test_agents_rules_hash",
     change_file(".agents/AGENTS.md", lambda b: b + b" ")),
    ("keys/allowed_signers with one character of the Director's key changed",
     "tests/test_s0_signers.py::test_allowed_signers_fingerprint",
     change_file("keys/allowed_signers", flip_one_key_character)),
    ("a Python file in harness/ that imports ve",
     "tests/test_s0_huginn_guard.py::test_no_file_imports_ve",
     add_file("harness/_red_probe_ve.py", "import " + "ve\n")),
    ("a Python file in harness/ that opens HUGINN's replay folder",
     "tests/test_s0_huginn_guard.py::test_no_file_opens_forbidden_huginn_paths",
     add_file("harness/_red_probe_path.py", "open('deps/" + "huginn" + "/replay/x')\n")),
    ("a file in runs/scored/ holding a private key",
     "tests/test_s0_secrets.py::test_repository_has_no_secrets",
     add_file("runs/scored/_red_probe_secret.txt",
              "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nnot-a-real-key\n")),
]


def run_test(node):
    result = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "--no-header", "--tb=short",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True)
    reasons = [line[2:].strip() for line in result.stdout.splitlines()
               if line.startswith("E ") and line[2:].strip()]
    return result.returncode == 0, reasons


def main():
    all_good = True
    for number, (title, node, (plant, restore)) in enumerate(CASES, 1):
        print(f"[{number}/{len(CASES)}] {title}")
        print(f"      test: {node}")
        before, _ = run_test(node)
        print(f"      before:   {'passed' if before else 'FAILED (tree was not clean)'}")
        plant()
        try:
            planted, reasons = run_test(node)
        finally:
            restored_exactly = restore()
        print(f"      planted:  {'PASSED (the check did not catch it)' if planted else 'FAILED, as intended'}")
        for reason in reasons[:3]:
            print(f"                {reason}")
        after, _ = run_test(node)
        print(f"      restored: {'passed' if after else 'FAILED'}, "
              f"{'bytes identical to before' if restored_exactly else 'BYTES DIFFER'}")
        all_good = all_good and before and not planted and after and restored_exactly
        print()
    print("Every red case failed as intended and the tree is back as it was." if all_good
          else "AT LEAST ONE CASE DID NOT BEHAVE. See above.")
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
