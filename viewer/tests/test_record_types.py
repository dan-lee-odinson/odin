"""Every record type the contract lists is shown, or listed as not shown."""

import json
import re
import unittest

import _support as S
import record_types


def contract_types():
    """The types in CONTRACT.md section 12's 'Record types:' line."""
    lines = [l for l in S.contract_path().read_text(encoding="utf-8").split("\n") if l.startswith("- Record types:")]
    if len(lines) != 1:
        raise AssertionError("expected one 'Record types:' line in the contract, found %d" % len(lines))
    return re.findall(r"`([A-Z_]+)`", lines[0])


def schema_types():
    schema = json.loads((S.schemas_dir() / "log_record.schema.json").read_text(encoding="utf-8"))
    return schema["properties"]["type"]["enum"]


class RecordTypes(unittest.TestCase):
    def test_contract_and_schema_agree(self):
        self.assertEqual(len(contract_types()), 25)
        self.assertEqual(set(contract_types()), set(schema_types()))

    def test_every_contract_type_is_shown_or_listed(self):
        listed = set(record_types.SHOWN) | set(record_types.NOT_SHOWN)
        self.assertFalse(set(record_types.SHOWN) & set(record_types.NOT_SHOWN), "a type is both shown and not shown")
        self.assertEqual(listed, set(schema_types()))
        for name in schema_types():
            with self.subTest(type=name):
                self.assertTrue((record_types.how_shown(name) or "").strip())


if __name__ == "__main__":
    unittest.main()
