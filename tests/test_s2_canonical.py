"""Canonical JSON (CONTRACT.md §4; the Director's ruling on U22, 26 October 2026): log/canonical.py
reproduces every vector in contract/schemas/canonical_vectors.json, the file ODIN's signer is held to
as well. Each red case is a vector file or a writer that differs in one thing, and must be caught."""

import json
import math

import pytest
import yaml

from contract.validate import SCHEMA_DIR
from log.canonical import canonical_json, sha256_tag

VECTORS = SCHEMA_DIR / "canonical_vectors.json"


def check_vectors(path=VECTORS, encode=canonical_json):
    """Every vector the writer encode does not reproduce, and every vector whose own hex and hash disagree."""
    problems = []
    for vector in json.loads(path.read_text(encoding="utf-8"))["vectors"]:
        name = vector["name"]
        try:
            expected = bytes.fromhex(vector["canonical_hex"])
        except ValueError:
            problems.append(f"{name}: canonical_hex is not hex")
            continue
        if sha256_tag(expected) != vector["sha256"]:
            problems.append(f"{name}: the file's hex and its sha256 disagree")
        try:
            actual = encode(vector["value"])
        except ValueError as error:
            problems.append(f"{name}: the writer refused the value ({error})")
            continue
        if actual != expected:
            problems.append(f"{name}: the writer gives {actual!r}, not {expected!r}")
    return problems


def test_canonical_json_reproduces_every_vector():
    assert check_vectors() == []


def test_the_vectors_cover_what_the_ruling_names():
    names = " ".join(v["name"] for v in json.loads(VECTORS.read_text(encoding="utf-8"))["vectors"])
    for subject in ["nesting", "accented", "Basic Multilingual Plane", "quotes", "backslashes", "control",
                    "integers", "floats", "negative zero", "booleans", "null"]:
        assert subject in names, f"no vector for {subject}"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, {"x": [math.nan]}])
def test_nan_and_infinity_are_refused(value):
    with pytest.raises(ValueError):
        canonical_json(value)


def test_the_vector_file_is_ascii():
    VECTORS.read_bytes().decode("ascii")


def test_run_start_hashes_the_canonical_list_of_its_chains_plan_files():
    """RUN_START's plan_chain_sha256 (the Director's ruling on U21), on the two example plans."""
    examples = SCHEMA_DIR / "examples"
    plans = [sha256_tag((examples / "tyr0_plan" / name).read_bytes())
             for name in ("good-plan.yaml", "good-plan-pass2.yaml")]
    run_start = json.loads((examples / "run_start" / "good-spark.json").read_text(encoding="utf-8"))
    assert run_start["plan_chain_sha256"] == sha256_tag(canonical_json(plans))
    assert yaml.safe_load((examples / "arming_act" / "good-arm.yaml").read_text(encoding="utf-8"))[
        "plan_chain_hashes"] == plans


# Red cases: the vector file altered.

def _altered(tmp_path, change):
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    change(data["vectors"])
    copy = tmp_path / "canonical_vectors.json"
    copy.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return copy


def _flip_hex(vector):
    digits = vector["canonical_hex"]
    vector["canonical_hex"] = digits[:-1] + ("0" if digits[-1] != "0" else "1")


def test_red_an_altered_vector_is_caught(tmp_path):
    assert check_vectors(_altered(tmp_path, lambda vectors: _flip_hex(vectors[4]))) != []


def test_red_an_altered_hash_is_caught(tmp_path):
    def change(vectors):
        vectors[0]["sha256"] = sha256_tag(b"")
    assert check_vectors(_altered(tmp_path, change)) != []


def test_red_an_altered_value_is_caught(tmp_path):
    def change(vectors):
        vectors[9]["value"][0] = 2
    assert check_vectors(_altered(tmp_path, change)) != []


# Red cases: writers that differ from the ruling in one thing each. The vectors must tell them apart.

def _utf16_key_order(value):
    if isinstance(value, dict):
        return {k: _utf16_key_order(value[k]) for k in sorted(value, key=lambda k: k.encode("utf-16-be"))}
    if isinstance(value, list):
        return [_utf16_key_order(item) for item in value]
    return value


def _whole_floats_as_integers(value):
    if isinstance(value, dict):
        return {k: _whole_floats_as_integers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_whole_floats_as_integers(item) for item in value]
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return int(value)
    return value


def _dumps(value, **overrides):
    options = dict(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    options.update(overrides)
    return json.dumps(value, **options).encode("utf-8")


OTHER_WRITERS = {
    "characters outside ASCII as \\u escapes": lambda v: _dumps(v, ensure_ascii=True),
    "keys sorted by UTF-16 code unit, as RFC 8785 does": lambda v: _dumps(_utf16_key_order(v), sort_keys=False),
    "2.0 written as 2, as RFC 8785 does": lambda v: _dumps(_whole_floats_as_integers(v)),
    "a space after each separator": lambda v: _dumps(v, separators=(", ", ": ")),
    "a trailing newline": lambda v: _dumps(v) + b"\n",
    "keys left in the order given": lambda v: _dumps(v, sort_keys=False),
    "UTF-16 instead of UTF-8": lambda v: json.dumps(v, sort_keys=True, separators=(",", ":"),
                                                    ensure_ascii=False).encode("utf-16-le"),
}


@pytest.mark.parametrize("writer", OTHER_WRITERS)
def test_red_another_writer_fails_the_vectors(writer):
    assert check_vectors(encode=OTHER_WRITERS[writer]) != []
