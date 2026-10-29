"""M3: adapters carry no built-in settings; every call takes config."""
import pytest

from odin.adapters.glimmer_local import GlimmerLocalAdapter
from odin.adapters.spark import SparkAdapter
from odin.adapters.spark_open import SparkOpenAdapter
from odin.devtools.fake_provider import FakeProvider

FULL = {"reasoning_effort": "low", "max_output_tokens": 32000, "timeout_s": 600}


def test_adapter_given_no_reasoning_raises():
    with pytest.raises((ValueError, TypeError)):
        SparkAdapter()
    with pytest.raises((ValueError, TypeError)):
        SparkOpenAdapter()
    with pytest.raises((ValueError, TypeError)):
        GlimmerLocalAdapter()


def test_adapter_given_partial_settings_raises():
    with pytest.raises((ValueError, TypeError)):
        SparkAdapter(reasoning_effort="low")
    with pytest.raises((ValueError, TypeError)):
        SparkOpenAdapter(reasoning_effort="low", max_output_tokens=32000)
    # Explicitly unset (None from an empty configuration) must also raise.
    with pytest.raises(ValueError):
        SparkAdapter(reasoning_effort=None, max_output_tokens=32000, timeout_s=600)
    with pytest.raises(ValueError):
        SparkOpenAdapter(reasoning_effort="low", max_output_tokens=None, timeout_s=600)


def test_spark_call_uses_configured_cap_timeout_level():
    provider = FakeProvider(answer_text='{"kind":"none"}')
    adapter = SparkAdapter(**FULL, http_post=provider.post, api_key="test-only")
    result = adapter.complete(prompt=b"prompt", bundle={"turn_kind": "ACT", "report_kind": None})
    assert result["raw"] == '{"kind":"none"}'
    call = provider.calls[0]
    assert call["body"]["max_tokens"] == 32000
    assert call["body"]["reasoning_effort"] == "low"
    assert call["timeout"] == 600


def test_spark_open_call_uses_configured_cap_timeout_level():
    provider = FakeProvider()
    adapter = SparkOpenAdapter(**{**FULL, "reasoning_effort": "xhigh"},
                               http_post=provider.post, api_key="test-only")
    result = adapter.complete(prompt=b"prompt", bundle={"turn_kind": "ACT", "report_kind": None})
    assert result["channel"] == "MESSAGE"
    call = provider.calls[0]
    assert call["body"]["max_tokens"] == 32000
    assert call["body"]["reasoning_effort"] == "xhigh"
    assert call["timeout"] == 600
