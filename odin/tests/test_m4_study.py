"""M4: COSMOS docs fetch + study step (AGENTS §4.4). No paid call."""
import json
from pathlib import Path

from odin.study import fetch_docs, study

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tree(tmp_path):
    src = tmp_path / "docs"
    (src / "guide").mkdir(parents=True)
    (src / "index.md").write_text("# COSMOS\nOpen source ground system.\n", encoding="utf-8")
    (src / "guide" / "cmd.md").write_text("Send commands with cmd().\n", encoding="utf-8")
    (src / "guide" / "tlm.md").write_text("Read telemetry with tlm().\n", encoding="utf-8")
    return src


def test_fetch_pinned_to_v721():
    assert fetch_docs.TAG == "v7.2.1"
    args = fetch_docs.clone_command(Path("/tmp/x"))
    assert "v7.2.1" in args and "--depth" in args


def test_every_file_hash_matches_recorded_list(tmp_path):
    src = _tree(tmp_path)
    cache = tmp_path / "cache"
    hash_list = tmp_path / "hashes.json"
    entries = fetch_docs.fetch_tree(src, cache, hash_list)
    assert len(entries) == 3
    assert fetch_docs.verify_hashes(cache, hash_list) == []
    recorded = json.loads(hash_list.read_text(encoding="utf-8"))
    assert [e["path"] for e in recorded] == sorted(e["path"] for e in recorded)


def test_altered_file_fails_hash_check(tmp_path):
    src = _tree(tmp_path)
    cache = tmp_path / "cache"
    hash_list = tmp_path / "hashes.json"
    fetch_docs.fetch_tree(src, cache, hash_list)
    target = cache / "index.md"
    data = bytearray(target.read_bytes())
    data[0] ^= 0x01
    target.write_bytes(bytes(data))
    problems = fetch_docs.verify_hashes(cache, hash_list)
    assert problems and "index.md" in problems[0]


def test_repository_contains_no_docs():
    """Always runs (fresh clone included): no docs inside odin/."""
    recorded_path = REPO_ROOT / "odin" / "study" / "cosmos_docs_hashes.json"
    assert recorded_path.exists(), "recorded hash list must be in the repository"
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    assert recorded, "hash list is empty"
    for entry in recorded:
        assert not (REPO_ROOT / "odin" / entry["path"]).exists()
    assert not (REPO_ROOT / "odin" / "study" / "docs").exists()


def test_cache_matches_recorded_list():
    """Runs only when a cache exists; a fresh clone has none and skips."""
    import pytest

    cache = REPO_ROOT / "cache" / "cosmos-docs-7.2.1"
    if not cache.exists():
        pytest.skip("no docs cache in this checkout (fresh clone); fetch first")
    recorded_path = REPO_ROOT / "odin" / "study" / "cosmos_docs_hashes.json"
    assert fetch_docs.check_tree(cache, recorded_path) == []


def test_cache_check_catches_one_changed_byte(tmp_path):
    """Red case beside the cache check: one altered byte must be caught."""
    src = _tree(tmp_path)
    license_file = _license(tmp_path)
    cache = tmp_path / "cache"
    hash_list = tmp_path / "hashes.json"
    fetch_docs.fetch_tree(src, cache, hash_list, license_file=license_file)
    assert fetch_docs.check_tree(cache, hash_list) == []
    target = cache / "guide" / "cmd.md"
    data = bytearray(target.read_bytes())
    data[0] ^= 0x01
    target.write_bytes(bytes(data))
    assert fetch_docs.check_tree(cache, hash_list)


def test_plain_fetch_run_never_writes_hash_list(tmp_path, monkeypatch):
    clone = tmp_path / "clone"
    (clone / "docs.openc3.com" / "docs").mkdir(parents=True)
    (clone / "docs.openc3.com" / "docs" / "index.md").write_text("# Docs\n", encoding="utf-8")
    (clone / "docs.openc3.com" / "LICENSE.md").write_text("# License\n", encoding="utf-8")
    cache = tmp_path / "cache"
    hash_list = tmp_path / "hashes.json"
    # Recorded list for different content: plain run must check, not rewrite.
    fetch_docs.fetch_tree(clone / "docs.openc3.com" / "docs", tmp_path / "other",
                          hash_list, license_file=clone / "docs.openc3.com" / "LICENSE.md")
    before = hash_list.read_bytes()
    monkeypatch.setattr(fetch_docs, "CACHE_DIR", cache)
    monkeypatch.setattr(fetch_docs, "HASH_LIST", hash_list)
    assert fetch_docs.main(["--source", str(clone)]) == 0
    assert hash_list.read_bytes() == before
    # Changed upstream content: a plain run reports the mismatch (exit 1)
    # and still does not rewrite the recorded list.
    (clone / "docs.openc3.com" / "docs" / "index.md").write_text("# Changed\n", encoding="utf-8")
    assert fetch_docs.main(["--source", str(clone)]) == 1
    assert hash_list.read_bytes() == before
    (clone / "docs.openc3.com" / "docs" / "index.md").write_text("# Docs\n", encoding="utf-8")
    # --write-hashes refuses when a list already exists...
    assert fetch_docs.main(["--source", str(clone), "--write-hashes"]) == 2
    assert hash_list.read_bytes() == before
    # ...and writes only when none exists.
    hash_list.unlink()
    assert fetch_docs.main(["--source", str(clone), "--write-hashes"]) == 0
    assert hash_list.exists()


def _license(tmp_path, text="# OpenC3 Builder's License\nBased on the Elastic License 2.0.\n"):
    path = tmp_path / "LICENSE.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_reference_hash_recorded_and_changes_with_one_byte(tmp_path):
    docs = _tree(tmp_path)
    _license(docs)
    adapter = _FakeStudyAdapter()
    out = tmp_path / "reference.md"
    record = tmp_path / "reference.json"
    result = study.run_study(docs_dir=docs, adapter=adapter, out_path=out,
                             record_path=record)
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["sha256"] == study.hash_reference(out.read_bytes())
    assert result["sha256"] == saved["sha256"]
    altered = bytearray(out.read_bytes())
    altered[0] ^= 0x01
    assert study.hash_reference(bytes(altered)) != saved["sha256"]


class _FakeStudyAdapter:
    name = "spark"

    def complete(self, *, prompt, bundle, **kwargs):
        return {"raw": "# COSMOS operations reference\nDerived from OpenC3 documentation.\n",
                "channel": "CONTENT", "status": "OK", "input_tokens": 10,
                "cached_input_tokens": 0, "output_tokens": 10, "reasoning_tokens": None,
                "latency_s": 0.0, "provider_usage": None, "provider": "fake",
                "model_id": "fake", "reasoning_effort": "high",
                "max_output_tokens": 32000, "cut_off": False}


def test_study_prompt_carries_notice_and_scope(tmp_path):
    docs = study.collect_docs(_tree(tmp_path))
    prompt = study.build_study_prompt(docs)
    assert "OpenC3" in prompt
    assert "Enterprise" in prompt and "absent" in prompt
    assert "Apache" not in prompt
    # Fix 5: only the instructions and the hashed docs; requirements repeated last.
    assert "HUGINN" not in prompt
    assert prompt.startswith(study.STUDY_INSTRUCTIONS)
    assert prompt.endswith(study.STUDY_INSTRUCTIONS)
    assert prompt.count(study.STUDY_INSTRUCTIONS) == 2
    assert "10,000 words" in prompt
    assert "AI operator" in prompt
    assert "limit states and alarms" in prompt
    body = prompt[len(study.STUDY_INSTRUCTIONS):-len(study.STUDY_INSTRUCTIONS)]
    for doc in docs:
        assert doc["text"] in body


# -- Director's license correction (2026-10-27) --------------------------------

def test_fetch_includes_license_md(tmp_path):
    src = _tree(tmp_path)
    site = tmp_path / "site"
    (site / "docs").mkdir(parents=True)
    import shutil as _sh

    _sh.copytree(src, site / "docs", dirs_exist_ok=True)
    (site / "LICENSE.md").write_text("# OpenC3 Builder's License\nTerms.\n", encoding="utf-8")
    cache = tmp_path / "cache"
    hash_list = tmp_path / "hashes.json"
    fetch_docs.fetch_tree(site / "docs", cache, hash_list, license_file=site / "LICENSE.md")
    recorded = json.loads(hash_list.read_text(encoding="utf-8"))
    assert any(e["path"] == "LICENSE.md" for e in recorded)
    assert (cache / "LICENSE.md").exists()


def test_reference_opens_with_fixed_header_and_license_beside(tmp_path):
    docs = _tree(tmp_path)
    _license(docs)
    out = tmp_path / "ref" / "reference.md"
    study.run_study(docs_dir=docs, adapter=_FakeStudyAdapter(), out_path=out,
                    record_path=tmp_path / "ref" / "reference.json")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("Written by Muse Spark from the OpenC3 COSMOS v7.2.1 "
                           "documentation, and modified from it.")
    assert "Copyright © 2026 OpenC3, Inc." in text
    assert "OpenC3 Builder's License" in text  # name read from LICENSE.md's title
    assert "Apache" not in text[:600]
    assert (tmp_path / "ref" / "LICENSE.md").exists()


def test_header_naming_any_other_license_fails():
    import pytest

    with pytest.raises(ValueError):
        study.validate_reference_header(
            "Used under the Apache License 2.0.\nCopyright © 2026 OpenC3, Inc.\n"
            "modified from it\n", "OpenC3 Builder's License")


def test_missing_or_altered_license_fails(tmp_path):
    import pytest

    docs = _tree(tmp_path)
    with pytest.raises((FileNotFoundError, ValueError)):
        study.run_study(docs_dir=docs, adapter=_FakeStudyAdapter(),
                        out_path=tmp_path / "r.md", record_path=tmp_path / "r.json")
    license_file = _license(docs)
    cache = tmp_path / "cache"
    hash_list = tmp_path / "hashes.json"
    fetch_docs.fetch_tree(docs, cache, hash_list, license_file=license_file)
    data = bytearray(license_file.read_bytes())
    data[-2] ^= 0x01
    license_file.write_bytes(bytes(data))
    with pytest.raises(ValueError):
        study.run_study(docs_dir=docs, adapter=_FakeStudyAdapter(),
                        out_path=tmp_path / "r.md", record_path=tmp_path / "r.json",
                        hash_list_path=hash_list)


# -- Director's fixes before the paid study call (2026-10-27) ------------------

def _spark_with_provider(provider):
    from odin.adapters.spark import SparkAdapter

    return SparkAdapter(reasoning_effort="high", max_output_tokens=64000,
                        timeout_s=1800, http_post=provider.post, api_key="test-only")


def test_study_call_is_plain_text_through_real_adapter(tmp_path):
    from odin.devtools.fake_provider import FakeProvider

    docs = _tree(tmp_path)
    _license(docs)
    provider = FakeProvider(answer_text="# Operations reference body\n")
    out = tmp_path / "ref" / "reference.md"
    study.run_study(docs_dir=docs, adapter=_spark_with_provider(provider),
                    out_path=out, record_path=tmp_path / "ref" / "reference.json")
    body = provider.calls[0]["body"]
    assert "response_format" not in body
    assert "tools" not in body
    assert "Operations reference body" in out.read_text(encoding="utf-8")


def test_cut_off_answer_freezes_nothing(tmp_path):
    import pytest
    from odin.devtools.fake_provider import FakeProvider

    docs = _tree(tmp_path)
    _license(docs)
    provider = FakeProvider(cut_off={("spark", "high")})
    out = tmp_path / "ref" / "reference.md"
    with pytest.raises(RuntimeError):
        study.run_study(docs_dir=docs, adapter=_spark_with_provider(provider),
                        out_path=out, record_path=tmp_path / "ref" / "reference.json")
    assert not out.exists()
    assert not (tmp_path / "ref" / "reference.json").exists()
    assert not (tmp_path / "ref" / "LICENSE.md").exists()


def test_empty_answer_freezes_nothing(tmp_path):
    import pytest
    from odin.devtools.fake_provider import FakeProvider

    docs = _tree(tmp_path)
    _license(docs)
    provider = FakeProvider(answer_text="")
    out = tmp_path / "ref" / "reference.md"
    with pytest.raises(RuntimeError):
        study.run_study(docs_dir=docs, adapter=_spark_with_provider(provider),
                        out_path=out, record_path=tmp_path / "ref" / "reference.json")
    assert not out.exists()
    assert not (tmp_path / "ref" / "LICENSE.md").exists()


def test_changed_doc_byte_stops_before_any_call(tmp_path):
    import pytest
    from odin.devtools.fake_provider import FakeProvider

    docs = _tree(tmp_path)
    license_file = _license(docs)
    hash_list = tmp_path / "hashes.json"
    fetch_docs.fetch_tree(docs, tmp_path / "cache", hash_list, license_file=license_file)
    target = docs / "index.md"
    data = bytearray(target.read_bytes())
    data[0] ^= 0x01
    target.write_bytes(bytes(data))
    provider = FakeProvider(answer_text="# body\n")
    with pytest.raises(ValueError):
        study.run_study(docs_dir=docs, adapter=_spark_with_provider(provider),
                        out_path=tmp_path / "r.md", record_path=tmp_path / "r.json",
                        hash_list_path=hash_list)
    assert provider.calls == []


def test_study_record_carries_call_facts(tmp_path):
    import hashlib as _hl

    from odin.devtools.fake_provider import FakeProvider
    from odin.loop.canonical import sha256_tag
    from odin.spend.meter import SpendMeter

    docs = _tree(tmp_path)
    license_file = _license(docs)
    hash_list = tmp_path / "hashes.json"
    fetch_docs.fetch_tree(docs, tmp_path / "cache", hash_list, license_file=license_file)
    provider = FakeProvider(answer_text="# body\n")
    meter = SpendMeter(ledger_path=tmp_path / "spend.jsonl")
    record_path = tmp_path / "ref" / "reference.json"
    record = study.run_study(docs_dir=docs, adapter=_spark_with_provider(provider),
                             out_path=tmp_path / "ref" / "reference.md",
                             record_path=record_path, hash_list_path=hash_list,
                             meter=meter)
    for key in ("model", "provider", "reasoning_effort", "max_output_tokens",
                "timeout_s", "input_tokens", "cached_input_tokens", "output_tokens",
                "reasoning_tokens", "actual_cost_usd", "finish_reason", "latency_s",
                "utc", "instructions_sha256", "docs_hashes_sha256"):
        assert key in record, key
    assert record["reasoning_effort"] == "high"
    assert record["max_output_tokens"] == 64000 and record["timeout_s"] == 1800
    assert record["finish_reason"] == "stop"
    assert record["actual_cost_usd"] > 0
    assert record["instructions_sha256"] == sha256_tag(
        study.STUDY_INSTRUCTIONS.encode("utf-8"))
    assert record["docs_hashes_sha256"] == "sha256:" + _hl.sha256(
        hash_list.read_bytes()).hexdigest()
    assert meter.totals()["META_CREDIT"] == record["actual_cost_usd"]


def test_study_dry_run_reports_size(tmp_path):
    docs = _tree(tmp_path)
    figures = study.study_dry_run(docs, max_output_tokens=32000)
    assert figures["files"] == 3
    assert figures["input_tokens_est"] > 0
    assert figures["worst_case_usd"] > 0
