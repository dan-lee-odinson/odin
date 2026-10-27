"""No field in contract/schemas/ is left UNSETTLED (00_HANDOFF.md §4, S1; CONTRACT.md §16)."""

import shutil

from tests.schema_checks import SCHEMA_DIR, check_no_unsettled_markers


def test_no_unsettled_marker_remains():
    assert check_no_unsettled_markers() == []


# Red cases: a scratch folder with one settled schema passes; planting a marker fails it.

def _scratch(tmp_path):
    folder = tmp_path / "schemas"
    (folder / "examples" / "checkin").mkdir(parents=True)
    shutil.copy(SCHEMA_DIR / "checkin.schema.json", folder)
    shutil.copy(SCHEMA_DIR / "examples" / "checkin" / "good-recorded.json", folder / "examples" / "checkin")
    (folder / "README.md").write_text("A description marked UNSETTLED (Un) is open.\n", encoding="utf-8")
    return folder


def test_a_settled_folder_passes(tmp_path):
    assert check_no_unsettled_markers(_scratch(tmp_path)) == []


def test_red_marker_in_a_schema_description_is_caught(tmp_path):
    folder = _scratch(tmp_path)
    schema = folder / "checkin.schema.json"
    text = schema.read_text(encoding="utf-8")
    schema.write_text(text.replace('"The transcript."', '"The transcript. UNSETTLED (U99): its language."'),
                      encoding="utf-8")
    assert check_no_unsettled_markers(folder) != []


def test_red_marker_in_lower_case_is_caught(tmp_path):
    folder = _scratch(tmp_path)
    schema = folder / "checkin.schema.json"
    text = schema.read_text(encoding="utf-8")
    schema.write_text(text.replace('"The transcript."', '"The transcript, format unsettled."'), encoding="utf-8")
    assert check_no_unsettled_markers(folder) != []


def test_red_marker_in_a_yaml_example_comment_is_caught(tmp_path):
    folder = _scratch(tmp_path)
    (folder / "examples" / "checkin" / "good-note.yaml").write_text(
        "# Placeholder: the source is UNSETTLED (U99).\ntext: hello\n", encoding="utf-8")
    assert check_no_unsettled_markers(folder) != []
