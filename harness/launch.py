"""Launching ODIN's process (the Director's ruling on U38, 27 October 2026), and flying a run with it (M8).

ODIN holds no ground-system credential (CONTRACT.md §9). COSMOS's credentials are the Director's user
environment variables, ODIN_COSMOS_*, and COSMOS's own settings are OPENC3_*, so ODIN's process starts
with this process's environment less every variable under either prefix. Windows compares environment
variable names without regard to case, so neither does this.

ODIN's process is Muse Code's start command, python -m odin.run_odin <model> (MC-M8-01), given the run's
model. It reads the harness's, BALDUR-0's and the log's addresses from config/ports.yaml and keeps its inputs
under the repository's runs/<run_id>/inputs/, so a run it flies serves on those addresses with its folder at
the repository's root. The harness waits for it to exit and ends the run by its exit code (the Director's
word of 28 October 2026): 0 comes only once ODIN was told run_complete, when RUN_END is already COMPLETE; 4,
after a spend stop, ends the run as SPEND_STOP; any other exit ends it as ERROR, with the exit and ODIN's
last line of output as RUN_END's detail. ODIN's standard output and error are kept apart, and can be kept for
every run whatever its exit (the Director's ruling of 29 October 2026): tools/scored_run.py keeps them beside
the run folder in runs/odin-output/, which git ignores, since a traceback carries private paths.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WITHHELD_PREFIXES = ("ODIN_COSMOS_", "OPENC3_")
ODIN_START = ("-m", "odin.run_odin")
# Muse Code's exit codes (MC-M8-01) other than 0, and how each ends the run.
EXITS = {2: "refused at start", 3: "the harness was unreachable", 4: "after a spend stop",
         5: "stopped before run_complete"}
ENDS = {4: "SPEND_STOP"}   # every other exit but 0 ends the run as ERROR


def withheld(name):
    return name.upper().startswith(WITHHELD_PREFIXES)


def odin_environment(environ=None):
    """The environment ODIN's process starts with: environ, os.environ by default, less every
    ODIN_COSMOS_* and OPENC3_* variable."""
    environ = os.environ if environ is None else environ
    return {name: value for name, value in environ.items() if not withheld(name)}


def launch_odin(command, *, environ=None, **popen):
    """Start ODIN's process with odin_environment(environ). Any env given in popen is refused, so no
    caller can pass a credential back in."""
    if "env" in popen:
        raise ValueError("ODIN's environment is odin_environment()'s; pass environ= to change its source")
    return subprocess.Popen(command, env=odin_environment(environ), **popen)


def odin_command(model_config):
    """Muse Code's start command for the run's model."""
    return [sys.executable, *ODIN_START, model_config]


def keep_output(folder, output, errors):
    """ODIN's standard output and error, as stdout.txt and stderr.txt in folder, byte for byte."""
    if folder is None:
        return
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stdout.txt").write_bytes(output or b"")
    (folder / "stderr.txt").write_bytes(errors or b"")


def fly(run, *, environ=None, command=None, timeout_s=None, output_dir=None):
    """Start the run, launch ODIN as its own process with the run's model, wait for it to exit, and stop
    the run by ODIN's exit code. Returns the exit code, or None if the run did not start, when no ODIN is
    launched. timeout_s: how long ODIN may run; one still running then is stopped, and the run ends as
    ERROR. command: in place of Muse Code's, for tests. output_dir: where to keep ODIN's standard output and
    error, whatever its exit."""
    if not run.start():
        return None
    process = launch_odin(command or odin_command(run.config["model_config"]), environ=environ, cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        output, errors = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        process.kill()
        output, errors = process.communicate()
        keep_output(output_dir, output, errors)
        run.stop("ERROR", detail=f"ODIN did not exit within {timeout_s} s")
        return process.returncode
    keep_output(output_dir, output, errors)
    code = process.returncode
    if code == 0:
        run.stop("COMPLETE")
    else:
        lines = (output.strip() or errors).decode("utf-8", "replace").strip().splitlines()
        meaning = EXITS.get(code, "an exit Muse Code's command does not give")
        run.stop(ENDS.get(code, "ERROR"), detail=f"ODIN exited {code} ({meaning}): {lines[-1] if lines else ''}")
    return code
