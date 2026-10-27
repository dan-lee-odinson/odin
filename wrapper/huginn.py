"""HUGINN, used unchanged as a library (CONTRACT.md §2.2; 00_HANDOFF.md §3.2).

HUGINN is the git submodule at deps/huginn, pinned at b4dbe61. Nothing here changes it, and nothing
opens its ve/, viewer/ or replay/ folders or its replay schema (§2.1). Its simulator package and its
definitions loader are imported from the submodule as they are. The wrapper steps the simulator one
tick at a time, as HUGINN's own tools/serve_sim.py does, which is what lets phase 3 pause it while
ODIN thinks (§10.1).
"""

import sys
from pathlib import Path

HUGINN = Path(__file__).resolve().parent.parent / "deps" / "huginn"
# Appended, not prepended, so that none of HUGINN's top-level names (it has a tests/ folder too)
# can shadow this repository's.
for _folder in (HUGINN, HUGINN / "tools"):
    if str(_folder) not in sys.path:
        sys.path.append(str(_folder))

# Imported without writing bytecode caches, which Python would otherwise put in HUGINN's folders. Every
# module the simulator uses is imported here, the orbit's too, so none is first imported later.
_writes_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    import hugdefs  # noqa: E402
    import sim.orbit  # noqa: E402, F401
    from sim.interface import CommandCodec, FrameCodec  # noqa: E402
    from sim.scenario import Scenario  # noqa: E402
    from sim.spacecraft import Spacecraft  # noqa: E402
finally:
    sys.dont_write_bytecode = _writes_bytecode

SCENARIOS = HUGINN / "sim" / "scenarios"
DICTIONARY = hugdefs.load_tlm_cmd()
EPS = hugdefs.load_eps()


def load_scenario(scenario):
    """A HUGINN scenario by its name in sim/scenarios/ (P1_nominal), or by a path to its file."""
    path = Path(scenario)
    if path.suffix != ".yaml":
        path = SCENARIOS / f"{scenario}.yaml"
    return Scenario.load(path)


def build(scenario):
    """The spacecraft under a scenario, built as HUGINN builds it."""
    return Spacecraft(EPS, DICTIONARY, scenario)
