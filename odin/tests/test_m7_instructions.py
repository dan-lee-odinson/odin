"""M7: ODIN's instructions rendered from contract/schemas (§5)."""
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from odin.instructions.render import hash_instructions, render_instructions
from odin.loop.prompt import build_prompt
from conftest import make_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "contract" / "schemas"


def test_rendered_forms_match_schemas():
    text = render_instructions()
    answer = json.loads((SCHEMAS / "answer.schema.json").read_text(encoding="utf-8"))
    for kind in ("OFF_COURSE", "MALFUNCTION", "DECISION_NEEDED", "LEASE_NEEDED",
                 "AUTHORITY_NEEDED", "CONFLICT", "ROUTINE", "URGENT"):
        assert kind in text
    # The kinds/urgencies lines themselves are rendered from the schemas.
    assert ("Escalation kinds (use exactly one): OFF_COURSE, MALFUNCTION, "
            "DECISION_NEEDED, LEASE_NEEDED, AUTHORITY_NEEDED, CONFLICT") in text
    assert "Urgencies (use exactly one): ROUTINE, URGENT" in text
    for field in ("escalation_kind", "refs", "proposed", "urgency", "rationale",
                  "command", "parameters", "kind"):
        assert field in text
    body = json.loads((SCHEMAS / "report_body.schema.json").read_text(encoding="utf-8"))
    for field in body["required"]:
        assert field in text
    for kind in ("PASS_START", "CHECK_IN", "HAND_BACK"):
        assert kind in text


def test_schema_change_changes_rendered_text(tmp_path):
    """A field added to a schema changes the rendered instructions."""
    copied = tmp_path / "schemas"
    shutil.copytree(SCHEMAS, copied)
    before = render_instructions()
    path = copied / "answer.schema.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    none_def = data["definitions"]["none"]
    none_def["properties"]["brand_new_field"] = {"type": "string"}
    none_def["required"] = ["kind", "brand_new_field"]
    path.write_text(json.dumps(data), encoding="utf-8")
    after = render_instructions(schema_dir=copied)
    assert "brand_new_field" in after
    assert after != before


def test_no_spacecraft_names_in_instructions():
    text = render_instructions()
    doc = yaml.safe_load(
        (REPO_ROOT / "deps" / "huginn" / "defs" / "tlm_cmd.yaml").read_text(encoding="utf-8"))
    names = [c["mnemonic"] for c in doc["commands"]]
    for group in doc["telemetry_groups"]:
        names += [p["mnemonic"] for p in group["points"]]
    for name in names:
        assert name not in text, name
    assert not re.search(r"PROC-\d+", text)


def test_frozen_hash_recorded_and_changes_with_one_byte():
    text = render_instructions()
    recorded = json.loads(
        (REPO_ROOT / "odin" / "instructions" / "system_prompt.sha256.json")
        .read_text(encoding="utf-8"))
    assert recorded["sha256"] == hash_instructions(text)
    frozen = (REPO_ROOT / "odin" / "instructions" / "system_prompt.md").read_text(
        encoding="utf-8")
    assert frozen == text
    altered = bytearray(text.encode("utf-8"))
    altered[10] ^= 0x01
    assert hash_instructions(bytes(altered).decode("utf-8")) != recorded["sha256"]


def test_frozen_file_bytes_hash_to_the_record():
    """The recorded hash is the hash of the file's exact bytes (LF only)."""
    import hashlib as _hl

    data = (REPO_ROOT / "odin" / "instructions" / "system_prompt.md").read_bytes()
    recorded = json.loads(
        (REPO_ROOT / "odin" / "instructions" / "system_prompt.sha256.json")
        .read_text(encoding="utf-8"))
    assert b"\r" not in data
    assert "sha256:" + _hl.sha256(data).hexdigest() == recorded["sha256"]


def test_carriage_returns_change_the_hash(tmp_path):
    """Red case: the same text written with CRLF hashes differently."""
    import hashlib as _hl

    data = (REPO_ROOT / "odin" / "instructions" / "system_prompt.md").read_bytes()
    crlf = tmp_path / "system_prompt.md"
    crlf.write_bytes(data.replace(b"\n", b"\r\n"))
    recorded = json.loads(
        (REPO_ROOT / "odin" / "instructions" / "system_prompt.sha256.json")
        .read_text(encoding="utf-8"))
    assert "sha256:" + _hl.sha256(crlf.read_bytes()).hexdigest() != recorded["sha256"]


def test_frozen_instructions_never_change():
    """Freeze guard (§10.4): any change to the frozen instructions, the
    template, or the prompt builder fails; rendering must reproduce the
    frozen bytes exactly."""
    import hashlib as _hl

    base = REPO_ROOT / "odin" / "instructions"
    record = json.loads((base / "system_prompt.sha256.json").read_text(encoding="utf-8"))
    assert record["frozen"] is True
    for key, path in (("sha256", base / "system_prompt.md"),
                      ("template_sha256", base / "template.md"),
                      ("prompt_template_sha256", REPO_ROOT / "odin" / "loop" / "prompt.py")):
        digest = "sha256:" + _hl.sha256(path.read_bytes()).hexdigest()
        assert digest == record[key], f"{path.name} changed since the freeze"
    frozen_text = (base / "system_prompt.md").read_text(encoding="utf-8")
    assert render_instructions() == frozen_text


def test_build_prompt_puts_instructions_first():
    bundle = make_bundle(1, turn_kind="ACT")
    prompt = build_prompt(bundle, render_instructions()).decode("utf-8")
    assert prompt.startswith("=== INSTRUCTIONS ===\n" + render_instructions()[:80])


def test_instructions_cover_rulings():
    text = render_instructions()
    for phrase in ("AI_AUTONOMOUS", "HUMAN_ONLY", "NO_FRESH_TELEMETRY",
                   "WRONG_RUN", "PLAN_MISMATCH", "HAND_BACK", "gateway_feedback",
                   "uses_left", "60 s", "protective"):
        assert phrase in text, phrase


def test_director_review_points():
    text = " ".join(render_instructions().split())  # ignore prose line wraps
    # 1. Only this build's two rungs, rendered from the schema enum.
    common = json.loads((SCHEMAS / "common.schema.json").read_text(encoding="utf-8"))
    assert common["definitions"]["rung"]["enum"] == ["HUMAN_ONLY", "AI_AUTONOMOUS"]
    assert "Rungs in this build: HUMAN_ONLY/AI_AUTONOMOUS" in text
    assert "AI_PROPOSE" not in text and "SAFE_HOLD" not in text
    # 2. Protective commands: open at AI_AUTONOMOUS, refused at HUMAN_ONLY.
    assert "whatever the plan says" in text
    assert "At HUMAN_ONLY they are refused like everything else" in text
    assert "always open" not in text
    # 3. No advice of our own.
    assert "prefer to wait" not in text
    # 4. VOIDED recheck; REFUSE names the first failed check.
    assert "rechecks every allowed command just before dispatch" in text
    assert "names the first check that failed" in text
    # 5. History: one row per frame; bundle history 300 s; no downsampling.
    assert "one row per received frame" in text
    assert "last 300 s" in text
    assert "50 buckets" not in text and "downsample" not in text
    # 6. The Director's words, no astronaut.
    assert "the Director's words" in text and "astronaut" not in text
    # 7. A plan has objectives and a contact window, not a schedule.
    assert "objectives and a contact window" in text
    assert "schedule" not in text
    # 8. contact_state, seat, queued escalations; observation fields rendered.
    assert "queued" in text and "acquisition of signal" in text
    assert "GROUND works COSMOS" in text and "ONBOARD reads" in text
    obs = json.loads((SCHEMAS / "observation.schema.json").read_text(encoding="utf-8"))
    for field in obs["properties"]:
        assert f"`{field}`" in text
    # The ground-interface field, rendered from the refreshed schema.
    assert "`ground_link`" in text
    for state in obs["definitions"]["ground_link"]["properties"]["state"]["enum"]:
        assert state in text
    assert "`received_count`" in text
    # 9. Proposed is a command with parameters, or null.
    assert "`proposed` is a command with its parameters" in text
    assert "or null when you propose none" in text
