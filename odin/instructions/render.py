"""Render ODIN's instructions from contract/schemas (M7, AGENTS §5).

The answer forms, escalation kinds and urgencies, report fields and bundle
fields are rendered from the schemas at build time — never typed a second
time. The frozen instructions (odin/instructions/system_prompt.md) are
this rendered text, hashed in odin/instructions/system_prompt.sha256.json.
If a schema changes, the rendered text changes.
"""
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "contract" / "schemas"
TEMPLATE = Path(__file__).resolve().parent / "template.md"


def _load(name, schema_dir):
    return json.loads((Path(schema_dir) / name).read_text(encoding="utf-8"))


def _resolve(doc, ref):
    node = doc
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _describe(doc, name, definition) -> str:
    required = set(definition.get("required", []))
    parts = []
    for field, spec in definition.get("properties", {}).items():
        if "$ref" in spec:
            spec = _resolve(doc, spec["$ref"])
        note = "required" if field in required else "optional"
        if "enum" in spec:
            note += ", one of " + "/".join(str(v) for v in spec["enum"])
        elif "const" in spec:
            note += f", always {spec['const']!r}"
        parts.append(f"{field} ({note})")
    return f"- kind {name!r}: " + "; ".join(parts) + "."


def render_instructions(schema_dir=None) -> str:
    schema_dir = Path(schema_dir or SCHEMA_DIR)
    answer = _load("answer.schema.json", schema_dir)
    defs = answer["definitions"]
    forms = "\n".join(
        _describe(answer, kind, defs[kind])
        for kind in ("command", "escalation", "none"))
    esc_spec = defs["escalation"]["properties"]["escalation_kind"]
    urg_spec = defs["escalation"]["properties"]["urgency"]
    esc = _resolve(answer, esc_spec["$ref"]) if "$ref" in esc_spec else esc_spec
    urg = _resolve(answer, urg_spec["$ref"]) if "$ref" in urg_spec else urg_spec
    report_body = _load("report_body.schema.json", schema_dir)
    report = _load("report.schema.json", schema_dir)
    body_required = set(report_body.get("required", []))
    body_fields = "; ".join(
        f"{f} ({'required' if f in body_required else 'optional'})"
        for f in report_body.get("properties", {}))
    kinds = "/".join(report["properties"]["report_kind"]["enum"])
    loop_filled = ", ".join(
        f for f in report["required"] if f not in report_body.get("properties", {}))
    report_text = (
        f"Report kinds: {kinds}. You write: {body_fields}. "
        f"`answer` is required on a CHECK_IN report and forbidden on the "
        f"others. The loop fills: {loop_filled}.")
    bundle = _load("turn_bundle.schema.json", schema_dir)
    bundle_fields = ", ".join(f"`{f}`" for f in bundle.get("properties", {}))
    observation = _load("observation.schema.json", schema_dir)
    observation_fields = ", ".join(f"`{f}`" for f in observation.get("properties", {}))
    ground_link = observation.get("definitions", {}).get("ground_link", {})
    ground_states = "/".join(
        ground_link.get("properties", {}).get("state", {}).get("enum", []))
    common = _load("common.schema.json", schema_dir)
    rungs = "/".join(common["definitions"]["rung"]["enum"])
    classes = "/".join(common["definitions"]["class"]["enum"])
    classes_text = (
        f"{classes} (in rising order of consequence: C1 routine, "
        "C2 reconfigure, C3 protective, C4 leased).")
    text = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (
        ("{{ANSWER_FORMS}}", forms),
        ("{{ESCALATION_KINDS}}", ", ".join(esc["enum"])),
        ("{{URGENCIES}}", ", ".join(urg["enum"])),
        ("{{REPORT_FORMS}}", report_text),
        ("{{BUNDLE_FIELDS}}", bundle_fields),
        ("{{OBSERVATION_FIELDS}}", observation_fields),
        ("{{GROUND_LINK_STATES}}", ground_states),
        ("{{RUNGS}}", rungs),
        ("{{CLASSES}}", classes_text),
    ):
        assert token in text, token
        text = text.replace(token, value)
    return text


def hash_instructions(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def freeze(out_md=None, out_record=None) -> dict:
    text = render_instructions()
    out_md = Path(out_md or Path(__file__).parent / "system_prompt.md")
    out_record = Path(out_record or Path(__file__).parent / "system_prompt.sha256.json")
    # Write bytes with line feeds only, on every machine: the frozen hash
    # is the hash of the file's exact bytes.
    out_md.write_bytes(text.encode("utf-8"))
    record = {"file": out_md.name, "sha256": hash_instructions(text)}
    out_record.write_bytes((json.dumps(record, indent=2) + "\n").encode("utf-8"))
    return record


def main() -> int:
    record = freeze()
    print(f"rendered {record['file']} sha256={record['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
