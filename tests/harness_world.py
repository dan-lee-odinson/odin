"""A scratch run for the harness's tests: P3's pass as the Director flew it, MET 800 to 1230, in the
onboard seat with CHARGED pacing, so it needs no COSMOS. Keys are made in memory; the plan and act are
signed with the development test key; the procedure and the pass plan it lists as a reference are made
up for the tests with no fault content, and the docs lookup reads the fixture cache.
"""

import hashlib
import json

from harness.procedures import ProcedureLibrary
from harness.run import Run
from tests.baldur_world import World, changed, dump, example_plan
from tests.repo_checks import REPO_ROOT
from wrapper.huginn import load_scenario

RUN = "dev-s6-0001"
PROCEDURE = (b"PROC-001 Pass procedure (made up for this test, no fault content).\n"
             b"1. Read EPS_LOAD_I and EPS_BATT_SOC.\n"
             b"2. If EPS_LOAD_I is above its yellow limit with PLD_STATE ON, send CMD_PLD_SET_STATE OFF.\n")
PROCEDURE_SHA256 = "sha256:" + hashlib.sha256(PROCEDURE).hexdigest()
PASS_PLAN = b"Pass plan (made up for this test): AOS at MET 800, LOS at MET 1230, no command planned.\n"
PASS_PLAN_SHA256 = "sha256:" + hashlib.sha256(PASS_PLAN).hexdigest()
CHECK_IN = {"text": "ODIN, what just changed on the bus?", "audio_sha256": "sha256:" + "64" * 32,
            "source": "RECORDED", "utc": "2026-10-28T14:10:58.900Z"}
CONFIG = {"seed": 20260731, "model_config": "stand_in", "provider": None, "answer_method": "SCRIPTED",
          "reference_sha256": None}
# A spark run's configuration names the model and its provider; the model ID and reasoning level come from
# spark's frozen block (U56).
SPARK_CONFIG = dict(CONFIG, model_config="spark", provider="Meta Model API, Standard mode",
                    answer_method="STRUCTURED_OUTPUT")
LOCAL = {name: ("127.0.0.1", 0) for name in ("harness", "baldur0", "log")}
DOCS = REPO_ROOT / "tests" / "fixtures" / "cosmos-docs"


class HarnessWorld:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        (tmp_path / "w").mkdir()
        self.world = World(tmp_path / "w")
        (tmp_path / "procedures").mkdir()
        (tmp_path / "procedures" / "PROC-001.txt").write_bytes(PROCEDURE)
        (tmp_path / "procedures" / "pass_plan.md").write_bytes(PASS_PLAN)

    def plan(self, **changes):
        fields = dict(plan_id="TYR0-P3-PASS1-v1", scenario_id="P3", valid_from_met_s=800, valid_until_met_s=1240,
                      contact_window={"aos_met_s": 800, "los_met_s": 1230}, prohibited=[], envelope=[], leases=[],
                      procedures_in_force=[{"id": "PROC-001", "version": "1", "sha256": PROCEDURE_SHA256}],
                      references=[{"name": "Pass plan (made up)", "sha256": PASS_PLAN_SHA256}])
        return changed(example_plan(1), **{**fields, **changes})

    def run(self, *, plans=None, act=None, signer="dev", **options):
        plans = plans if plans is not None else self.world.plans([self.plan()], signer=signer)
        act = act if act is not None else self.world.act(plans, runs=[RUN], signer=signer)
        settings = dict(run_id=RUN, scenario=load_scenario("P3_stuck_load"), scenario_id="P3", phase=2,
                        mode="DEVELOPMENT", plan_paths=plans, act_path=act, root=self.tmp,
                        procedures=ProcedureLibrary(self.tmp / "procedures"), config=CONFIG, seat="ONBOARD",
                        pacing="CHARGED", docs_folder=DOCS, keys_dir=self.world.keys_dir, addresses=LOCAL)
        settings.update(options)
        return Run(**settings)


def records(run, type_=None):
    found = [json.loads(line) for line in (run.folder / "events.jsonl").read_bytes().splitlines()]
    return [r for r in found if type_ is None or r["type"] == type_]


def turns(run, count):
    """Take count turns in-process, as ODIN's GET /turn/next would, each answered with no request."""
    return [json.loads(run.next_turn()) for _ in range(count)]
