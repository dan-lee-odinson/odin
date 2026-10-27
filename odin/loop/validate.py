"""Answer checking against contract/schemas (CONTRACT §7.2, §16.5).

The schemas in contract/schemas/ are the single source for every field
list; this module loads them at run time and never re-states them.
A small Draft-7 subset validator resolves the cross-file $refs.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "contract" / "schemas"
DICT_PATH = REPO_ROOT / "deps" / "huginn" / "defs" / "tlm_cmd.yaml"


@lru_cache(maxsize=None)
def _load_schema(filename: str) -> dict:
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


def _resolve_ref(ref: str, current_file: str):
    if ref.startswith("#/"):
        doc, frag = _load_schema(current_file), ref[2:]
    else:
        file_part, _, frag = ref.partition("#/")
        doc = _load_schema(file_part)
        current_file = file_part
        if not frag:
            return doc, current_file
    node = doc
    for part in frag.split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node, current_file


def _type_ok(instance, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "null":
        return instance is None
    return True


def validate_instance(instance, schema, current_file: str, path: str = "$") -> list:
    """Return a list of error strings; empty means valid."""
    errors = []
    if not isinstance(schema, dict):
        return errors
    if "$ref" in schema:
        target, target_file = _resolve_ref(schema["$ref"], current_file)
        return validate_instance(instance, target, target_file, path)
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum")
    expected_type = schema.get("type")
    if expected_type is not None:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_type_ok(instance, t) for t in types):
            errors.append(f"{path}: expected type {expected_type}")
            return errors
    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: pattern mismatch")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above maximum")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: not above exclusiveMinimum")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required {key!r}")
        props = schema.get("properties", {})
        for key, subschema in props.items():
            if key in instance:
                errors += validate_instance(instance[key], subschema, current_file, f"{path}.{key}")
        additional = schema.get("additionalProperties", True)
        if additional is False:
            for key in instance:
                if key not in props:
                    errors.append(f"{path}: additional property {key!r}")
        elif isinstance(additional, dict):
            for key in instance:
                if key not in props:
                    errors += validate_instance(instance[key], additional, current_file, f"{path}.{key}")
        if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
            errors.append(f"{path}: too many properties")
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            errors.append(f"{path}: too few properties")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems")
        if schema.get("uniqueItems") and len({json.dumps(i, sort_keys=True) for i in instance}) != len(instance):
            errors.append(f"{path}: items not unique")
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(instance):
                errors += validate_instance(item, items, current_file, f"{path}[{i}]")
        elif isinstance(items, list):
            for i, subschema in enumerate(items):
                if i < len(instance):
                    errors += validate_instance(instance[i], subschema, current_file, f"{path}[{i}]")
            additional_items = schema.get("additionalItems")
            if isinstance(additional_items, dict):
                for i in range(len(items), len(instance)):
                    errors += validate_instance(instance[i], additional_items, current_file, f"{path}[{i}]")
            elif additional_items is False and len(instance) > len(items):
                errors.append(f"{path}: too many items")
    for subschema in schema.get("allOf", []):
        errors += validate_instance(instance, subschema, current_file, path)
    if "anyOf" in schema:
        if all(validate_instance(instance, s, current_file, path) for s in schema["anyOf"]):
            errors.append(f"{path}: matches no anyOf branch")
    if "oneOf" in schema:
        matches = sum(1 for s in schema["oneOf"] if not validate_instance(instance, s, current_file, path))
        if matches != 1:
            errors.append(f"{path}: matches {matches} oneOf branches, expected 1")
    if "not" in schema and not validate_instance(instance, schema["not"], current_file, path):
        errors.append(f"{path}: matches forbidden schema")
    if "if" in schema:
        if not validate_instance(instance, schema["if"], current_file, path):
            if "then" in schema:
                errors += validate_instance(instance, schema["then"], current_file, path)
        elif "else" in schema:
            errors += validate_instance(instance, schema["else"], current_file, path)
    return errors


def validate_against_schema(schema_file: str, instance) -> list:
    return validate_instance(instance, _load_schema(schema_file), schema_file)


@lru_cache(maxsize=1)
def _dictionary_commands() -> dict:
    doc = yaml.safe_load(DICT_PATH.read_text(encoding="utf-8"))
    return {cmd["mnemonic"]: cmd for cmd in doc["commands"]}


def dictionary_errors(command: str, parameters) -> list:
    """Check a command against deps/huginn/defs/tlm_cmd.yaml (§7.2)."""
    commands = _dictionary_commands()
    if command not in commands:
        return [f"command {command!r} not in dictionary"]
    if not isinstance(parameters, dict):
        return ["parameters must be an object"]
    spec_args = {a["name"]: a for a in commands[command].get("args", [])}
    errors = []
    if set(parameters) != set(spec_args):
        errors.append(f"arguments {sorted(parameters)} != dictionary {sorted(spec_args)}")
        return errors
    for name, value in parameters.items():
        spec = spec_args[name]
        if spec["type"] == "enum" and value not in spec["enum_values"]:
            errors.append(f"{name}={value!r} not in {spec['enum_values']}")
        if spec["type"] == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{name} must be a number")
            elif not (spec["min"] <= value <= spec["max"]):
                errors.append(f"{name}={value} outside {spec['min']}..{spec['max']}")
    return errors


def parse_one_json_object(raw: str):
    """(obj, reason, detail): exactly one JSON object and nothing else."""
    if not isinstance(raw, str) or not raw.strip():
        return None, "NOT_ONE_JSON_OBJECT", "empty or non-text answer"
    try:
        obj = json.loads(raw)
    except Exception as exc:
        return None, "NOT_ONE_JSON_OBJECT", f"not exactly one JSON value: {exc}"
    if not isinstance(obj, dict):
        return None, "NOT_ONE_JSON_OBJECT", "answer is not a JSON object"
    return obj, None, ""


def validate_act_text(raw: str):
    """Validate the model's ACT-turn text. Returns (ok, obj, reason, detail)."""
    obj, reason, detail = parse_one_json_object(raw)
    if reason:
        return False, None, reason, detail
    errors = validate_against_schema("answer.schema.json", obj)
    if obj.get("kind") == "command":
        errors += dictionary_errors(obj.get("command"), obj.get("parameters"))
    if obj.get("kind") == "escalation" and isinstance(obj.get("proposed"), dict):
        proposed = obj["proposed"]
        errors += dictionary_errors(proposed.get("command"), proposed.get("parameters"))
    if errors:
        return False, None, "SCHEMA_VIOLATION", "; ".join(errors[:5])
    return True, obj, None, ""


def validate_report_text(raw: str, report_kind: str):
    """Validate the model's REPORT-turn text (report body, §16.3 U12)."""
    obj, reason, detail = parse_one_json_object(raw)
    if reason:
        return False, None, reason, detail
    if "kind" in obj:
        return False, None, "WRONG_FORM_FOR_TURN", "ACT answer form on a REPORT turn"
    errors = validate_against_schema("report_body.schema.json", obj)
    if report_kind == "CHECK_IN" and "answer" not in obj:
        errors.append("CHECK_IN report requires answer")
    if report_kind != "CHECK_IN" and "answer" in obj:
        errors.append("answer allowed only on CHECK_IN reports")
    if errors:
        return False, None, "SCHEMA_VIOLATION", "; ".join(errors[:5])
    return True, obj, None, ""
