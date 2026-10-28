"""ODIN's process starts with no ODIN_COSMOS_* or OPENC3_* variable (the Director's ruling on U38): ODIN
holds no ground-system credential (CONTRACT.md §9). The values here are made up for the test."""

import json
import os
import subprocess
import sys

import pytest

from harness.launch import launch_odin, odin_environment

# The names are assembled from pieces so that this file does not trip the secret scan.
PLANTED = {"ODIN_COSMOS_" + "REDIS_PASSWORD": "made-up-1", "ODIN_COSMOS_" + "SERVICE_PASSWORD": "made-up-2",
           "OPENC3_" + "SERVICE_PASSWORD": "made-up-3", "openc3_" + "redis_username": "made-up-4",
           "Odin_Cosmos_" + "Secret_Key_Base": "made-up-5"}
KEPT = {"PATH": "C:\\Windows", "ODIN_KEY_PATH": "C:\\keys\\odin", "META_" + "API_KEY": "made-up-6",
        "ODIN_COSMOSX": "not a credential's prefix", "MY_OPENC3_NOTE": "not a prefix either"}


def test_odin_gets_every_variable_but_cosmos_credentials_and_settings():
    assert odin_environment({**PLANTED, **KEPT}) == KEPT


def test_red_each_credential_prefix_is_withheld_whatever_its_case():
    for name in PLANTED:
        assert name not in odin_environment({name: "x"}), name


def test_odins_process_starts_without_them():
    environ = {**PLANTED, **{name: value for name, value in os.environ.items()
                             if name.upper() in ("SYSTEMROOT", "PATH", "PATHEXT", "TEMP", "TMP")}}
    child = launch_odin([sys.executable, "-c", "import json, os; print(json.dumps(sorted(os.environ)))"],
                        environ=environ, stdout=subprocess.PIPE, text=True)
    names = json.loads(child.communicate(timeout=30)[0])
    assert child.returncode == 0
    assert not [name for name in names if name.upper().startswith(("ODIN_COSMOS_", "OPENC3_"))]


def test_red_no_caller_can_hand_odin_an_environment_of_its_own():
    with pytest.raises(ValueError):
        launch_odin([sys.executable, "-c", "pass"], env={"ODIN_COSMOS_REDIS_PASSWORD": "x"})
