"""Where a run's model settings come from (the Director's ruling on U56, 28 October 2026): whoever starts a run
names only the model, and RUN_START's model ID and reasoning level come from that model's frozen block in
config/models.yaml, the block its loop reads. A run configuration carrying its own is refused, so there is no
second copy. The stand-in stays null. The provider has no single source in the build, so the configuration
still names it."""

import pytest

from harness.run import FROM_BLOCK
from log.canonical import canonical_json, sha256_tag
from tests.harness_world import CONFIG, SPARK_CONFIG, HarnessWorld, records


def started(tmp_path, config):
    run = HarnessWorld(tmp_path).run(config=config)
    assert run.start()
    [start] = records(run, "RUN_START")
    run.stop()
    return start["body"]


def test_a_spark_run_takes_its_model_id_and_reasoning_level_from_the_frozen_block(tmp_path):
    body = started(tmp_path, SPARK_CONFIG)
    derived = {"model_id": "muse-spark-1.3", "reasoning_effort": "high"}
    assert {name: body[name] for name in ("model_config", "provider", *derived)} == {
        "model_config": "spark", "provider": "Meta Model API, Standard mode", **derived}
    assert body["config_sha256"] == sha256_tag(canonical_json({**SPARK_CONFIG, **derived}))


def test_the_stand_in_stays_null_for_all_three(tmp_path):
    body = started(tmp_path, CONFIG)
    assert (body["provider"], body["model_id"], body["reasoning_effort"]) == (None, None, None)


@pytest.mark.parametrize("name", sorted(FROM_BLOCK))
@pytest.mark.parametrize("config", [SPARK_CONFIG, CONFIG], ids=["spark", "stand_in"])
def test_red_a_configuration_carrying_its_own_setting_is_refused(tmp_path, config, name):
    # Refused even when the copy agrees with the frozen block: there is no second copy.
    copy = {"model_id": "muse-spark-1.3", "reasoning_effort": "high"}[name] if config is SPARK_CONFIG else None
    run = HarnessWorld(tmp_path).run(config=dict(config, **{name: copy}))
    with pytest.raises(ValueError, match=f"carries its own {name}"):
        run.start()
    assert not run.folder.exists() and not run.final.exists()
