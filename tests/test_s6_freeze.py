"""The freeze record of the six contract schemas ODIN's instructions are rendered from and of the model settings
for scored runs (the Director's ruling on U55, 28 October 2026), so that phases 1, 2 and 3 fly the same settings:
config/frozen.json holds each schema's hash as a whole file and each model's settings as its own entry, the
canonical JSON of its block in config/models.yaml. A model in config/models.yaml without an entry comes to the
Director first; a run whose schemas or model settings differ from the record refuses to start."""

import json
import shutil

import pytest

from harness import freeze
from harness.freeze import SCHEMAS, NotFrozen, check, model_blocks, on_disk, settings_sha256
from log.canonical import canonical_json, sha256_tag
from tests.harness_world import SPARK_CONFIG, HarnessWorld
from tests.repo_checks import REPO_ROOT

RECORD = json.loads((REPO_ROOT / "config" / "frozen.json").read_bytes())
# The six schemas as they stood at fb90847, unchanged since, as the Director checked on 28 October 2026.
SCHEMA_HASHES = {
    "contract/schemas/answer.schema.json": "sha256:d027563de2e6d2dc6c8e5ef260a183050c10324d3f22d070e3b3f4a300ac2e7e",
    "contract/schemas/report_body.schema.json": "sha256:f77c34533d5c5dc4363ce89bf5515930b2503ae78f6007c4834bb84dd811f6c3",
    "contract/schemas/report.schema.json": "sha256:47f5d96a217ea1c710a086aef7a7d015691041151e198ad17685c0600dbde1ec",
    "contract/schemas/turn_bundle.schema.json": "sha256:5fd78e3c8863f185226662d1b39b2da90b1b059d99a9abb28cb7220d2db5cc62",
    "contract/schemas/observation.schema.json": "sha256:6653468213b347f3b1c3f7b760977e439106d52a660af3214404a52e2c7528e0",
    "contract/schemas/common.schema.json": "sha256:3c56f9dc4d08337770838050a0b002b970e6640977cd73ad7566b9701722afce",
}
# Each model's block as the Director ruled it on 27 October 2026 (config/models.yaml at 9aa39d8).
SPARK = (b'{"date":"2026-10-27","max_output_tokens":32000,"model":"muse-spark-1.3","reasoning_effort":"high",'
         b'"source":"the Director\'s ruling of 27 October 2026, from M3\'s table","timeout_s":120}')
MODEL_HASHES = {"spark": "sha256:764c3a01537ba11e8f3fd303c750773498a39e77de9f8552774b15eb491d71a3",
                "spark_open": "sha256:94d25d66a4f9dd48f061d9bb6a41482ccb1b94c061f44799d689a70cbc792d2c"}
MODELS = ("spark", "spark_open")


def test_the_record_holds_the_six_schemas_and_each_ruled_model():
    assert RECORD["schemas"] == SCHEMA_HASHES
    assert RECORD["models"] == MODEL_HASHES


def test_a_models_settings_are_the_canonical_json_of_its_block_with_its_date_as_written():
    assert canonical_json(dict(model_blocks()["spark"], date="2026-10-27")) == SPARK
    assert settings_sha256(model_blocks()["spark"]) == sha256_tag(SPARK) == MODEL_HASHES["spark"]


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda path: path.split("/")[-1].split(".")[0])
def test_each_frozen_schema_is_the_recorded_one(path):
    assert on_disk()["schemas"][path] == RECORD["schemas"][path]


@pytest.mark.parametrize("name", sorted(RECORD["models"]))
def test_each_recorded_models_settings_are_unchanged(name):
    blocks = model_blocks()
    assert name in blocks, f"config/models.yaml no longer holds {name}"
    assert settings_sha256(blocks[name]) == RECORD["models"][name]


def test_models_yaml_holds_no_model_the_record_does_not():
    assert sorted(set(model_blocks()) - set(RECORD["models"])) == []


@pytest.fixture
def copies(tmp_path, monkeypatch):
    """The record, the six schemas and config/models.yaml copied to a scratch folder, which check() then reads."""
    for path in (*SCHEMAS, "config/models.yaml", "config/frozen.json"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / path, tmp_path / path)
    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    monkeypatch.setattr(freeze, "RECORD", tmp_path / "config" / "frozen.json")
    monkeypatch.setattr(freeze, "MODELS", tmp_path / "config" / "models.yaml")
    return tmp_path


def edit(path, old, new):
    data = path.read_bytes()
    assert data.count(old) == 1
    path.write_bytes(data.replace(old, new))


def test_the_frozen_files_pass_for_each_model_and_the_stand_in(copies):
    for model_config in (*MODELS, "stand_in"):
        check(model_config)


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda path: path.split("/")[-1].split(".")[0])
def test_red_one_changed_byte_in_a_schema_refuses_every_run(copies, path):
    data = bytearray((copies / path).read_bytes())
    data[-2] ^= 0x01
    (copies / path).write_bytes(bytes(data))
    for model_config in (*MODELS, "stand_in"):
        with pytest.raises(NotFrozen, match=path.split("/")[-1]):
            check(model_config)


def test_red_a_changed_setting_refuses_that_models_runs_only(copies):
    edit(copies / "config" / "models.yaml", b"  reasoning_effort: high\n", b"  reasoning_effort: medium\n")
    with pytest.raises(NotFrozen, match="spark's settings"):
        check("spark")
    check("spark_open")
    check("stand_in")


def test_red_a_recorded_model_whose_entry_disappears_refuses_its_runs(copies):
    models = copies / "config" / "models.yaml"
    data = models.read_bytes()
    models.write_bytes(data[:data.index(b"spark_open:\n")])
    assert "spark_open" not in model_blocks()
    with pytest.raises(NotFrozen, match="holds no settings for spark_open"):
        check("spark_open")
    check("spark")


def test_red_a_model_with_no_entry_of_its_own_has_no_frozen_settings(copies):
    models = copies / "config" / "models.yaml"
    models.write_bytes(models.read_bytes() + b"\nglimmer_local:\n  model: glimmer-local\n  reasoning_effort: high\n")
    with pytest.raises(NotFrozen, match="glimmer_local has no frozen settings"):
        check("glimmer_local")
    assert "glimmer_local" in on_disk()["models"] and "glimmer_local" not in RECORD["models"]


def test_red_a_setting_written_twice_is_refused(copies):
    edit(copies / "config" / "models.yaml", b"  model: muse-spark-1.3\n",
         b"  model: muse-spark-1.3\n  reasoning_effort: medium\n")
    with pytest.raises(NotFrozen, match="appears twice"):
        check("spark")


def test_red_a_run_whose_schema_changed_refuses_to_start_and_writes_nothing(tmp_path, copies):
    edit(copies / "contract" / "schemas" / "common.schema.json", b'"title": "Shared definitions"',
         b'"title": "Shared definitionS"')
    (tmp_path / "world").mkdir()
    run = HarnessWorld(tmp_path / "world").run()
    with pytest.raises(NotFrozen, match="common.schema.json"):
        run.start()
    assert not run.folder.exists() and not run.final.exists()


def test_red_a_spark_run_whose_settings_changed_refuses_to_start_and_writes_nothing(tmp_path, copies):
    edit(copies / "config" / "models.yaml", b"  reasoning_effort: high\n", b"  reasoning_effort: medium\n")
    (tmp_path / "world").mkdir()
    run = HarnessWorld(tmp_path / "world").run(config=SPARK_CONFIG)
    with pytest.raises(NotFrozen, match="spark's settings"):
        run.start()
    assert not run.folder.exists() and not run.final.exists()
