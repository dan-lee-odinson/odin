"""Answer checking against contract/schemas (CONTRACT §7.2, §16.5).

The schemas in contract/schemas/ are the single source for every field
list; this module loads them at run time and never re-states them.
A small Draft-7 subset validator resolves the cross-file $refs.
"""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "contract" / "schemas"
REGISTRY_PATH = REPO_ROOT / "config" / "dictionaries.yaml"


class DictionaryError(RuntimeError):
    """The dictionary in force cannot be chosen or trusted (U58)."""


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


def _inline_refs(node, current_file: str, seen: tuple = ()):
    """A copy of `node` with every $ref replaced by its resolved target,
    recursively. Sibling keys beside a $ref are kept, over the target."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if (current_file, ref) in seen:
                raise ValueError(f"circular $ref {ref!r} in {current_file}")
            target, target_file = _resolve_ref(ref, current_file)
            resolved = _inline_refs(target, target_file, seen + ((current_file, ref),))
            siblings = {k: _inline_refs(v, current_file, seen)
                        for k, v in node.items() if k != "$ref"}
            if siblings:
                merged = dict(resolved) if isinstance(resolved, dict) else {}
                merged.update(siblings)
                return merged
            return resolved
        return {k: _inline_refs(v, current_file, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(v, current_file, seen) for v in node]
    return node


def resolved_schema(schema_file: str) -> dict:
    """The named schema with every $ref resolved inline, derived from the
    frozen schema files at call time (M10). The files are never changed."""
    return _inline_refs(_load_schema(schema_file), schema_file)


def load_dictionary_registry(registry_path=None) -> list:
    path = Path(registry_path) if registry_path else REGISTRY_PATH
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(doc.get("dictionaries") or [])


def dictionary_in_force_entry(plan, registry_path=None) -> dict:
    """The registry entry in force (U58): exactly one of the plan's
    references matches an entry; none matching means the HUGINN entry;
    two or more matching is an error."""
    entries = load_dictionary_registry(registry_path)
    referenced = {r.get("sha256") for r in ((plan or {}).get("references") or [])
                  if isinstance(r, dict)}
    matches = [e for e in entries if e.get("reference") in referenced]
    if len(matches) > 1:
        names = ", ".join(sorted(e.get("name", "?") for e in matches))
        raise DictionaryError(f"plan lists two or more registered dictionaries: {names}")
    if matches:
        return matches[0]
    for entry in entries:
        if entry.get("name") == "HUGINN":
            return entry
    raise DictionaryError("registry has no HUGINN entry to fall back to")


def load_dictionary_commands(entry, registry_path=None) -> dict:
    """Read an entry's file, checking its SHA-256 against the entry."""
    path = Path(registry_path) if registry_path else REGISTRY_PATH
    root = path.resolve().parents[1]
    file_path = Path(entry["file"])
    if not file_path.is_absolute():
        file_path = root / file_path
    data = file_path.read_bytes()
    computed = "sha256:" + hashlib.sha256(data).hexdigest()
    if computed != entry.get("sha256"):
        raise DictionaryError(
            f"dictionary {entry.get('name')!r} file {entry.get('file')!r} "
            f"hashes to {computed}, registry records {entry.get('sha256')}")
    doc = yaml.safe_load(data.decode("utf-8"))
    return {cmd["mnemonic"]: cmd for cmd in doc["commands"]}


def dictionary_for_plan(plan, registry_path=None):
    """(entry, commands) in force for a plan, or DictionaryError."""
    entry = dictionary_in_force_entry(plan, registry_path)
    return entry, load_dictionary_commands(entry, registry_path)


def _default_commands() -> dict:
    _entry, commands = dictionary_for_plan({})
    return commands


def dictionary_errors(command: str, parameters, commands=None) -> list:
    """Check a command against the dictionary in force (§7.2, U58).

    Every error names the command or the argument at fault."""
    if commands is None:
        commands = _default_commands()
    if command not in commands:
        return [f"command {command!r} not in dictionary"]
    if not isinstance(parameters, dict):
        return ["parameters must be an object"]
    spec_args = {a["name"]: a for a in commands[command].get("args", [])}
    if set(parameters) != set(spec_args):
        extra = sorted(set(parameters) - set(spec_args))
        missing = sorted(set(spec_args) - set(parameters))
        parts = []
        if extra:
            parts.append(f"argument {extra[0]!r} not in dictionary for command {command!r}")
        if missing:
            parts.append(f"argument {missing[0]!r} missing for command {command!r}")
        return parts
    errors = []
    for name, value in parameters.items():
        spec = spec_args[name]
        kind = spec.get("type")
        if kind == "enum" and value not in spec.get("enum_values", []):
            errors.append(f"argument {name!r}={value!r} not in {spec.get('enum_values')}")
        elif kind == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"argument {name!r} must be a number")
            elif "min" in spec and "max" in spec and not (spec["min"] <= value <= spec["max"]):
                errors.append(f"argument {name!r}={value} outside {spec['min']}..{spec['max']}")
        elif kind == "uint":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"argument {name!r} must be an integer, never a bool")
            elif "min" in spec and "max" in spec and not (spec["min"] <= value <= spec["max"]):
                errors.append(f"argument {name!r}={value} outside {spec['min']}..{spec['max']}")
    return errors


def _dictionary_first_errors(obj, commands) -> list:
    """Dictionary check, run before the generic schema check (U58). Only
    shapes the dictionary can judge are judged here; the rest falls
    through to the schema check."""
    targets = []
    if obj.get("kind") == "command":
        targets.append((obj.get("command"), obj.get("parameters")))
    elif obj.get("kind") == "escalation" and isinstance(obj.get("proposed"), dict):
        proposed = obj["proposed"]
        targets.append((proposed.get("command"), proposed.get("parameters")))
    errors = []
    for command, parameters in targets:
        if not isinstance(command, str):
            continue
        if command not in commands or isinstance(parameters, dict):
            errors += dictionary_errors(command, parameters, commands)
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


def validate_act_text(raw: str, commands=None):
    """Validate the model's ACT-turn text. Returns (ok, obj, reason, detail).

    The dictionary check runs before the generic schema check (U58):
    anything outside the dictionary in force is NOT_IN_DICTIONARY, never
    SCHEMA_VIOLATION. `commands` is that dictionary's commands; when it is
    not given, the registry's default (the HUGINN entry) is used."""
    obj, reason, detail = parse_one_json_object(raw)
    if reason:
        return False, None, reason, detail
    if commands is None:
        commands = _default_commands()
    dict_errors = _dictionary_first_errors(obj, commands)
    if dict_errors:
        return False, None, "NOT_IN_DICTIONARY", "; ".join(dict_errors[:5])
    errors = validate_against_schema("answer.schema.json", obj)
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
