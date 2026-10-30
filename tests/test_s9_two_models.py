"""S9, piece 5, the harness's side of M17 (the Director's ruling of 30 October 2026, "Loop picks model by seat"): a
run names the model that flies the onboard seat beside its own in RUN_START's onboard, each model's settings found
from its frozen block and its adapter; S8 checks each model call against its own model's frozen settings; and a model
whose frozen block names its endpoint calls that one, though its adapter's class carries another's."""

import pytest

import eval.measures as measures_module
from contract.validate import check
from eval.measures import measures
from harness.adapter import adapter_settings
from harness.freeze import frozen_block
from odin.adapters.spark import SparkAdapter
from tests.harness_world import HarnessWorld, records
from tests.s8_world import record
from tests.test_s8_measures import SPARK_CALL, SPARK_START, call

# Glimmer's approved block, as the tests have it until it is in config/models.yaml.
GLIMMER = {"model": "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf", "reasoning_effort": "low", "max_output_tokens": 8192,
           "timeout_s": 60, "endpoint": "https://dan-lee-odinson--odin-glimmer-serve-h100.us-east.modal.run"}
GLIMMER_CALL = dict(SPARK_CALL, config="glimmer_modal", provider="Modal (llama.cpp), proxy auth", model_id=GLIMMER["model"],
                    reasoning_effort="low", max_output_tokens=8192)
ONBOARD = {"model_config": "glimmer_modal", "provider": "Modal (llama.cpp), proxy auth", "model_id": GLIMMER["model"],
           "reasoning_effort": "low", "endpoint": GLIMMER["endpoint"], "answer_method": "STRUCTURED_OUTPUT"}


def test_red_a_scored_run_calls_the_endpoint_its_models_frozen_block_names(monkeypatch):
    # Glimmer's adapter reads its endpoint from its frozen block (M16), and its class inherits spark's.
    import odin.adapters.settings as settings

    class Inherited:
        endpoint = SparkAdapter.endpoint
        provider = ONBOARD["provider"]
        model_id = GLIMMER["model"]

        def __init__(self, base_url=None):
            self.base_url = base_url or GLIMMER["endpoint"]
    monkeypatch.setattr(settings, "build_adapter", lambda config, **given: Inherited(**given))
    assert adapter_settings("glimmer_modal", GLIMMER, mode="SCORED") == {"provider": ONBOARD["provider"],
                                                                          "endpoint": GLIMMER["endpoint"]}
    with pytest.raises(ValueError, match="built-in endpoint"):
        adapter_settings("glimmer_modal", GLIMMER, mode="SCORED", endpoint="https://elsewhere.example")


def test_red_run_start_names_the_onboard_model_beside_the_runs_own(tmp_path):
    for onboard, expected in ((None, None), ("stand_in", {"model_config": "stand_in", "provider": None, "model_id": None,
                                                          "reasoning_effort": None, "endpoint": None,
                                                          "answer_method": "SCRIPTED"})):
        (tmp_path / str(onboard)).mkdir()
        run = HarnessWorld(tmp_path / str(onboard)).run(onboard=onboard)
        try:
            assert run.start()
        finally:
            run.stop()
        [start] = [r["body"] for r in records(run, "RUN_START")]
        assert "onboard" in start and start["onboard"] == expected and check("run_start", start) == []


def test_red_an_onboard_model_that_may_not_fly_the_onboard_seat_is_refused(tmp_path):
    with pytest.raises(ValueError, match="onboard model 'spark'"):
        HarnessWorld(tmp_path).run(onboard="spark")


@pytest.fixture
def glimmer_frozen(monkeypatch):
    monkeypatch.setattr(measures_module, "frozen_block",
                        lambda config: GLIMMER if config == "glimmer_modal" else frozen_block(config))


def two_models():
    return record("RUN_START", 0, **{k: v for k, v in SPARK_START["body"].items() if k != "met_s"}, onboard=ONBOARD)


def test_red_each_call_is_checked_against_its_own_models_frozen_settings(glimmer_frozen):
    found = measures([two_models(), call(), call(turn_id=2, base=GLIMMER_CALL)])
    assert found["model_call_mismatches"] == [] and not found["flagged"]
    found = measures([two_models(), call(), call(turn_id=2, base=GLIMMER_CALL, reasoning_effort="high")])
    assert [(m["turn_id"], m["field"], m["found"], m["expected"]) for m in found["model_call_mismatches"]] == [
        (2, "reasoning_effort", "high", "low")]


def test_red_a_call_from_a_model_the_run_does_not_name_is_a_settings_mismatch(glimmer_frozen):
    found = measures([SPARK_START, call(), call(turn_id=2, base=GLIMMER_CALL)])   # no onboard model named
    assert ("config", "glimmer_modal", "spark") in [(m["field"], m["found"], m["expected"])
                                                    for m in found["model_call_mismatches"]]
    assert found["flagged"]


def test_red_a_phase_3_run_start_without_onboard_fails_its_record():
    # Every run from M17 on writes onboard, null or not; phase 1's and phase 2's were recorded before it.
    from tests.test_s8_set_aside import clean, end, keys

    def phase_3(**onboard):
        return record("RUN_START", 0, run_id="PH3-TEST", model_config="stand_in", provider="none", phase=3,
                      mode="SCORED", **onboard)
    assert keys([phase_3(onboard=None)] + clean()[1:] + [end()]) == []
    assert keys([phase_3()] + clean()[1:] + [end()]) == ["RECORD_FAILS_SCHEMA RUN_START"]
    assert keys(clean() + [end()]) == []   # a phase-2 run, recorded without it
