"""Where a run's model settings come from (the Director's rulings on U56 and U57, 28 October 2026): whoever
starts a run names only the model. RUN_START's model ID and reasoning level come from that model's frozen block
in config/models.yaml, the block its loop reads, and its provider and endpoint from the model's adapter, whose
code makes the call. A run configuration carrying any of the four is refused, so there is no second copy. The
adapter's model ID must be its frozen block's model, and a SCORED run calls only the adapter's built-in
endpoint. The stand-in stays null."""

import pytest

from harness.adapter import adapter_settings
from harness.freeze import frozen_block
from harness.instructions import NotFrozen
from harness.run import DERIVED
from log.canonical import canonical_json, sha256_tag
from odin.adapters.spark import SparkAdapter
from tests.harness_world import CONFIG, SPARK_CONFIG, HarnessWorld, records

SPARK = {"model_id": "muse-spark-1.3", "reasoning_effort": "high", "provider": "Meta Model API, Standard mode",
         "endpoint": "https://api.meta.ai/v1"}
SPARK_OPEN = {"model_id": "meta-models/muse-spark-open-1026", "reasoning_effort": "xhigh",
              "provider": "Baseten Model API", "endpoint": "https://inference.baseten.co/v1"}
SPARK_OPEN_CONFIG = dict(CONFIG, model_config="spark_open", answer_method="ANSWER_TOOLS")
DEVELOPMENT_ENDPOINT = "http://127.0.0.1:8999/v1"
# Listed here, not read from harness/run.py, so a setting dropped there still has its red case.
SETTINGS = ("model_id", "reasoning_effort", "provider", "endpoint")


def started(tmp_path, config, **options):
    run = HarnessWorld(tmp_path).run(config=config, **options)
    assert run.start()
    [start] = records(run, "RUN_START")
    run.stop()
    return start["body"]


@pytest.mark.parametrize("config, expected", [(SPARK_CONFIG, SPARK), (SPARK_OPEN_CONFIG, SPARK_OPEN)],
                         ids=["spark", "spark_open"])
def test_a_run_takes_its_settings_from_the_frozen_block_and_the_adapter(tmp_path, config, expected):
    body = started(tmp_path, config)
    assert {name: body[name] for name in expected} == expected
    assert body["config_sha256"] == sha256_tag(canonical_json({**config, **expected}))


def test_the_stand_in_stays_null_for_all_four(tmp_path):
    body = started(tmp_path, CONFIG)
    assert [body[name] for name in SETTINGS] == [None] * 4


def test_the_run_derives_exactly_the_four_settings():
    assert sorted(DERIVED) == sorted(SETTINGS)


def test_a_development_run_records_the_endpoint_it_gives_the_adapter(tmp_path):
    assert started(tmp_path, SPARK_CONFIG, endpoint=DEVELOPMENT_ENDPOINT + "/")["endpoint"] == DEVELOPMENT_ENDPOINT


def test_a_scored_run_may_name_the_built_in_endpoint():
    block = frozen_block("spark")
    for endpoint in (None, SPARK["endpoint"], SPARK["endpoint"] + "/"):
        assert adapter_settings("spark", block, mode="SCORED", endpoint=endpoint) == {
            "provider": SPARK["provider"], "endpoint": SPARK["endpoint"]}


@pytest.mark.parametrize("name", SETTINGS)
@pytest.mark.parametrize("config", [SPARK_CONFIG, CONFIG], ids=["spark", "stand_in"])
def test_red_a_configuration_carrying_its_own_setting_is_refused(tmp_path, config, name):
    # Refused even when the copy agrees with the block or the adapter: there is no second copy.
    run = HarnessWorld(tmp_path).run(config=dict(config, **{name: SPARK[name] if config is SPARK_CONFIG else None}))
    with pytest.raises(ValueError, match=f"carries its own {name}"):
        run.start()
    assert not run.folder.exists() and not run.final.exists()


def test_red_a_scored_run_with_an_overridden_endpoint_is_refused(tmp_path):
    run = HarnessWorld(tmp_path).run(config=SPARK_CONFIG, mode="SCORED", endpoint=DEVELOPMENT_ENDPOINT)
    with pytest.raises(ValueError, match="a SCORED run calls only spark's built-in endpoint"):
        run.start()
    assert not run.folder.exists() and not run.final.exists()


def test_red_an_adapter_calling_another_model_id_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(SparkAdapter, "model_id", "muse-spark-1.2")
    run = HarnessWorld(tmp_path).run(config=SPARK_CONFIG)
    with pytest.raises(NotFrozen, match="spark's adapter calls muse-spark-1.2, not its frozen block's muse-spark-1.3"):
        run.start()
    assert not run.folder.exists() and not run.final.exists()


def test_red_the_stand_in_given_an_endpoint_is_refused(tmp_path):
    run = HarnessWorld(tmp_path).run(config=CONFIG, endpoint=DEVELOPMENT_ENDPOINT)
    with pytest.raises(ValueError, match="the stand-in calls no endpoint"):
        run.start()
    assert not run.folder.exists() and not run.final.exists()
