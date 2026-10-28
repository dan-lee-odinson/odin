"""The model settings for scored runs, config/models.yaml (CONTRACT.md §11.1, §11.3), as the Director ruled
on 27 October 2026 from M3's measurement table: spark at reasoning high, spark_open at xhigh, an output cap
of 32,000 tokens with reasoning included, and a 120-second timeout per call. Muse Code's loop reads them."""

import datetime

import pytest
import yaml

from tests.repo_checks import REPO_ROOT

MODELS = yaml.safe_load((REPO_ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
PRICES = yaml.safe_load((REPO_ROOT / "config" / "prices.yaml").read_text(encoding="utf-8"))
RULED = {"spark": "high", "spark_open": "xhigh"}
# The levels M3 measured for each model, the table the Director picked from.
MEASURED = {"spark": {"low", "medium", "high"}, "spark_open": {"low", "medium", "high", "xhigh"}}
SOURCE = "the Director's ruling of 27 October 2026, from M3's table"


def test_the_models_are_the_two_the_director_ruled_on():
    assert sorted(MODELS) == ["spark", "spark_open"]


@pytest.mark.parametrize("name", sorted(RULED))
def test_each_model_carries_the_ruled_settings_and_their_source(name):
    assert MODELS[name] == {"model": PRICES[name]["model"], "reasoning_effort": RULED[name],
                            "max_output_tokens": 32000, "timeout_s": 120, "source": SOURCE,
                            "date": datetime.date(2026, 10, 27)}


@pytest.mark.parametrize("name", sorted(RULED))
def test_each_level_is_one_m3_measured_for_that_model(name):
    assert MODELS[name]["reasoning_effort"] in MEASURED[name]


def test_red_spark_at_xhigh_was_never_measured():
    assert "xhigh" not in MEASURED["spark"]
