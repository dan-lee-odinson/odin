"""The results notebook, notebooks/odin_results.ipynb (the Director's word of 2 November 2026): it was saved run top
to bottom with its outputs, its saved totals are what S8's code gives from the records in runs/scored/, and it
imports nothing that calls a model or the network. The notebook is read as JSON with the standard library, so these
tests need none of its own packages and never skip.

S8's own code imports ODIN's Spark adapters while it scores, for the answer formats the runs were given
(eval/set_aside.py, format_met), and never calls them; the runs are scored here with the network refused, so a
connection would fail the test."""

import ast
import json
import socket

import pytest

from eval.phase3 import load_checks
from eval.results import score_run, totals
from tests.repo_checks import REPO_ROOT

NOTEBOOK = REPO_ROOT / "notebooks" / "odin_results.ipynb"
SCORED = REPO_ROOT / "runs" / "scored"

# What the notebook's code may import: the standard library's plain modules, IPython's display, matplotlib's plotting,
# and the repository's scoring, event log and request-signature check, with the key loader BALDUR-0 uses.
ALLOWED = {"json", "statistics", "sys", "collections", "pathlib", "hashlib", "IPython.display", "matplotlib.pyplot",
           "eval", "eval.phase3", "eval.results", "log.event_log", "gateway.decision",
           "cryptography.hazmat.primitives.serialization"}
# What calls a model or the network: never imported, whatever ALLOWED says.
MODEL_OR_NETWORK = {"socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp", "websocket",
                    "websockets", "ftplib", "smtplib", "xmlrpc", "openai", "anthropic", "modal", "odin", "harness",
                    "connector"}


def notebook():
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def code_cells():
    return [cell for cell in notebook()["cells"] if cell["cell_type"] == "code"]


def saved_lines(tag):
    """{name: value} from the printed lines of the cell tagged so, as saved."""
    [cell] = [c for c in code_cells() if tag in c["metadata"].get("tags", [])]
    text = "".join("".join(o["text"]) for o in cell["outputs"] if o["output_type"] == "stream" and o["name"] == "stdout")
    return dict(line.split(": ", 1) for line in text.splitlines() if ": " in line)


def as_printed(found):
    return {"scored": str(found["scored"]), "successes": str(found["successes"]), "clean": str(found["clean"]),
            "set aside by ruling": ", ".join(found["set_aside_by_ruling"]) or "none"}


def refuse(*args, **kwargs):
    raise AssertionError(f"scoring tried to reach the network: {args[1:2]!r}")


@pytest.fixture(scope="module")
def no_network():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, "connect", refuse)
        patch.setattr(socket.socket, "connect_ex", refuse)
        patch.setattr(socket, "create_connection", refuse)
        patch.setattr(socket, "getaddrinfo", refuse)
        yield


@pytest.fixture(scope="module")
def phase3_runs(no_network):
    checks = load_checks(REPO_ROOT / "phase3" / "checks")
    return [score_run(folder, checks=checks) for folder in sorted(SCORED.glob("PH3-*"))]


@pytest.fixture(scope="module")
def phase2_runs(no_network):
    return [score_run(folder) for folder in sorted(SCORED.glob("PH2-*"))]


def test_the_notebook_was_run_top_to_bottom_and_saved_with_its_outputs():
    cells = code_cells()
    assert [c["execution_count"] for c in cells] == list(range(1, len(cells) + 1))
    outputs = [o for c in cells for o in c["outputs"]]
    assert [o for o in outputs if o["output_type"] == "error"] == []
    assert [o for o in outputs if o["output_type"] == "stream" and o["name"] == "stderr"] == []
    assert any("image/png" in o.get("data", {}) for o in outputs)


def test_the_saved_phase_3_totals_are_what_s8_gives_from_the_records(phase3_runs):
    assert saved_lines("phase3-totals") == as_printed(totals(phase3_runs))


def test_the_saved_phase_2_totals_are_what_s8_gives_from_the_records(phase2_runs):
    assert saved_lines("phase2-totals") == as_printed(totals(phase2_runs))


def imported(source):
    """Each module a cell's code imports, and each way it could load or run one unseen."""
    found, unseen = [], []
    for number, line in enumerate(source.splitlines(), 1):
        if line.lstrip().startswith(("%", "!")):
            unseen.append(f"line {number}: an IPython magic or shell command")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
        elif isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) in {
                "__import__", "import_module", "exec", "eval", "run_path", "run_module"}:
            unseen.append(f"line {node.lineno}: a call that loads or runs code by name")
    return found, unseen


def test_the_notebook_imports_nothing_that_calls_a_model_or_the_network():
    found, unseen = [], []
    for cell in code_cells():
        modules, ways = imported("".join(cell["source"]))
        found += modules
        unseen += [f"cell {cell['id']}, {way}" for way in ways]
    assert unseen == []
    assert sorted({m for m in found if m.split(".")[0] in MODEL_OR_NETWORK}) == []
    assert sorted(set(found) - ALLOWED) == []
