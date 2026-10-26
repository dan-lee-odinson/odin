"""No key, token or private signing key anywhere in the repository (CONTRACT.md §2.5,
00_HANDOFF.md §3.5). Configuration names an environment variable, never its value."""

import shutil
import subprocess
import zipfile

import pytest

from tests.repo_checks import REPO_ROOT, check_no_secrets


def test_repository_has_no_secrets():
    assert check_no_secrets(REPO_ROOT) == []


# Red cases: each kind of secret planted in a scratch tree. The values are assembled at run
# time so that this file does not trip its own scan; none of them is a real credential.

def _fake(n):
    return ("Q7xR2mK9pL4vT8nW" * 4)[:n]


PLANTED = {
    "OpenSSH private key": "-----BEGIN " + "OPENSSH PRIVATE KEY-----\n" + _fake(40)
                           + "\n-----END " + "OPENSSH PRIVATE KEY-----\n",
    "PEM private key": "-----BEGIN " + "PRIVATE KEY-----\n" + _fake(40) + "\n",
    "META_API_KEY with a value": "META_API_KEY" + "=" + _fake(32) + "\n",
    "Modal token secret in YAML": "MODAL_PROXY_TOKEN_SECRET" + ": " + "ws-" + _fake(24) + "\n",
    "Modal token id": "token_id = " + "ak-" + _fake(22) + "\n",
    "sk- style key": "client(key=" + "sk-" + _fake(40) + ")\n",
    "GitHub token": "GH = " + "ghp_" + _fake(36) + "\n",
    "AWS access key": "aws = " + "AKIA" + "Q7XR2MK9PL4VT8NW" + "\n",
    "bearer token": "Authorization: " + "Bearer " + _fake(40) + "\n",
    "quoted secret assignment": "api_key = " + "'" + _fake(24) + "'\n",
}


@pytest.mark.parametrize("kind", PLANTED)
def test_red_planted_secret_is_caught(tmp_path, kind):
    (tmp_path / "runs" / "dev").mkdir(parents=True)
    (tmp_path / "runs" / "dev" / "events.jsonl").write_text(PLANTED[kind], encoding="utf-8")
    problems = check_no_secrets(tmp_path)
    assert problems != []
    assert not any(_fake(16) in problem for problem in problems), "a finding echoed the secret"


def test_red_secret_inside_a_deposit_zip_is_caught(tmp_path):
    (tmp_path / "deposits").mkdir()
    with zipfile.ZipFile(tmp_path / "deposits" / "MC-M1-01.zip", "w") as archive:
        archive.writestr("odin/adapters/spark.py", PLANTED["META_API_KEY with a value"])
    assert check_no_secrets(tmp_path) != []


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen not on PATH")
def test_red_real_ed25519_private_key_is_caught(tmp_path):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "red-case",
                    "-f", str(tmp_path / "key")], check=True)
    assert check_no_secrets(tmp_path) != []


# Scope: naming a variable, reading it from the environment, and public keys all pass.

def test_naming_secrets_and_public_keys_pass(tmp_path):
    (tmp_path / "config.yaml").write_text("api_key_env: META_API_KEY\n", encoding="utf-8")
    (tmp_path / "adapter.py").write_text(
        'import os\nMETA_API_KEY = os.environ["META_API_KEY"]\n'
        'token = os.getenv("MODAL_PROXY_TOKEN_SECRET")\n', encoding="utf-8")
    shutil.copy(REPO_ROOT / "keys" / "dev-test.pub", tmp_path / "dev-test.pub")
    shutil.copy(REPO_ROOT / "keys" / "allowed_signers", tmp_path / "allowed_signers")
    assert check_no_secrets(tmp_path) == []
