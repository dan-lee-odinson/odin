"""Nothing in this repository imports HUGINN's ve or opens its ve/, viewer/ or replay/ folders
or its replay schema (CONTRACT.md §2.1, 00_HANDOFF.md §3.3).

HUGINN itself, in deps/, is not scanned: it is used unchanged, and its own
tools/demonstrate.py imports ve.
"""

import pytest

from tests.repo_checks import REPO_ROOT, check_no_forbidden_huginn_paths, check_no_ve_import


def test_no_file_imports_ve():
    assert check_no_ve_import(REPO_ROOT) == []


def test_no_file_opens_forbidden_huginn_paths():
    assert check_no_forbidden_huginn_paths(REPO_ROOT) == []


# Red cases: each defect planted in a scratch tree. The planted text is assembled at run
# time so that this file does not trip its own scan.

VE = "ve"
H = "huginn"
SCHEMA = "replay" + "_schema"

IMPORT_FORMS = {
    "import ve": f"import {VE}\n",
    "import ve.core": f"import {VE}.core\n",
    "import os, ve": f"import os, {VE}\n",
    "from ve import name": f"from {VE} import thing\n",
    "from ve.core import name": f"from {VE}.core import thing\n",
    "from huginn import ve": f"from {H} import {VE}\n",
    "import deps.huginn.ve": f"import deps.{H}.{VE}\n",
    "relative import": f"from . import {VE}\n",
    "importlib.import_module": f"import importlib\nimportlib.import_module('{VE}')\n",
    "__import__": f"__import__('{VE}.core')\n",
    "inside a function": f"def run():\n    import {VE}\n",
    "in a file that does not parse": f"import {VE}\ndef broken(:\n",
}


@pytest.mark.parametrize("form", IMPORT_FORMS)
def test_red_ve_import_is_caught(tmp_path, form):
    (tmp_path / "harness").mkdir()
    (tmp_path / "harness" / "probe.py").write_text(IMPORT_FORMS[form], encoding="utf-8")
    assert check_no_ve_import(tmp_path) != []


def test_red_script_running_ve_as_a_module_is_caught(tmp_path):
    (tmp_path / "run.ps1").write_text(f"python -m {VE}\n", encoding="utf-8")
    assert check_no_ve_import(tmp_path) != []


PATH_FORMS = {
    "ve folder in Python": ("probe.py", f"open('deps/{H}/{VE}/__init__.py')\n"),
    "viewer folder with backslashes": ("probe.py", f"p = r'deps\\{H}\\viewer\\index.html'\n"),
    "replay folder in YAML": ("probe.yaml", f"source: deps/{H}/replay/\n"),
    "replay schema in JSON": ("probe.json", f'{{"schema": "deps/{H}/defs/{SCHEMA}.yaml"}}\n'),
    "replay schema in PowerShell": ("probe.ps1", f"Get-Content defs\\{SCHEMA}.md\n"),
}


@pytest.mark.parametrize("form", PATH_FORMS)
def test_red_forbidden_path_is_caught(tmp_path, form):
    name, text = PATH_FORMS[form]
    (tmp_path / name).write_text(text, encoding="utf-8")
    assert check_no_forbidden_huginn_paths(tmp_path) != []


# Scope: what the guard deliberately leaves alone.

def test_names_that_only_contain_ve_pass(tmp_path):
    (tmp_path / "probe.py").write_text(
        f"import venv\nfrom vector import x\nimport eve\nfrom {H}.sim import vehicle\n"
        f"# we've checked\n", encoding="utf-8")
    assert check_no_ve_import(tmp_path) == []


def test_huginn_itself_is_not_scanned(tmp_path):
    tools = tmp_path / "deps" / H / "tools"
    tools.mkdir(parents=True)
    (tools / "demonstrate.py").write_text(f"import {VE}\n", encoding="utf-8")
    assert check_no_ve_import(tmp_path) == []


def test_prose_that_names_the_folders_passes(tmp_path):
    (tmp_path / "README.md").write_text(f"Nothing opens deps/{H}/{VE}/.\n", encoding="utf-8")
    assert check_no_forbidden_huginn_paths(tmp_path) == []
