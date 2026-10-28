"""Launching ODIN's process (the Director's ruling on U38, 27 October 2026).

ODIN holds no ground-system credential (CONTRACT.md §9). COSMOS's credentials are the Director's user
environment variables, ODIN_COSMOS_*, and COSMOS's own settings are OPENC3_*, so ODIN's process starts
with this process's environment less every variable under either prefix. Windows compares environment
variable names without regard to case, so neither does this.
"""

import os
import subprocess

WITHHELD_PREFIXES = ("ODIN_COSMOS_", "OPENC3_")


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
