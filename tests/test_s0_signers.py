"""keys/allowed_signers holds the Director's TYR-0 key as principal dan (00_HANDOFF.md §5)."""

from tests.repo_checks import REPO_ROOT, check_allowed_signer

# The Director's TYR-0 public key, from 00_HANDOFF.md §5 and CONTRACT.md §5.3.
DAN_FINGERPRINT = "SHA256:sSlxjO9jypfyKVCvGiObwRnsanIPjevnJnAx4j5zkRg"
SIGNERS = REPO_ROOT / "keys" / "allowed_signers"


def test_allowed_signers_fingerprint():
    assert check_allowed_signer(SIGNERS, "dan", DAN_FINGERPRINT) == []


# Red cases: the same check on a scratch copy with one defect planted.

def _scratch(tmp_path, text):
    path = tmp_path / "allowed_signers"
    path.write_text(text, encoding="utf-8")
    return path


def _dan_line():
    return SIGNERS.read_text(encoding="utf-8")


def test_red_one_key_character_changed(tmp_path):
    principal, keytype, key, comment = _dan_line().split(" ", 3)
    swapped = "B" if key[30] != "B" else "C"
    tampered = " ".join([principal, keytype, key[:30] + swapped + key[31:], comment])
    assert check_allowed_signer(_scratch(tmp_path, tampered), "dan", DAN_FINGERPRINT) != []


def test_red_principal_renamed(tmp_path):
    tampered = "dann" + _dan_line()[len("dan"):]
    assert check_allowed_signer(_scratch(tmp_path, tampered), "dan", DAN_FINGERPRINT) != []


def test_red_dev_test_key_added_as_dan(tmp_path):
    keytype, key, _ = (REPO_ROOT / "keys" / "dev-test.pub").read_text(encoding="utf-8").split(" ", 2)
    tampered = _dan_line() + f"dan {keytype} {key}\n"
    assert check_allowed_signer(_scratch(tmp_path, tampered), "dan", DAN_FINGERPRINT) != []


def test_red_dev_test_key_in_place_of_dan(tmp_path):
    keytype, key, _ = (REPO_ROOT / "keys" / "dev-test.pub").read_text(encoding="utf-8").split(" ", 2)
    tampered = f"dan {keytype} {key}\n"
    assert check_allowed_signer(_scratch(tmp_path, tampered), "dan", DAN_FINGERPRINT) != []
