import pandas as pd
import pytest

from student_success.workflow import (
    automatic_column_mapping,
    available_model_fields,
    student_source_row,
    suggest_column_mappings,
    validate_column_mapping,
)
from student_success.schema import canonicalize


def test_student_lookup_uses_mapped_id_not_first_column():
    source = pd.DataFrame({"attendance": [60, 90], "learner": ["S-1", "S-2"]})
    row = student_source_row(source, {"learner": "student_id", "attendance": "attendance_rate"}, "S-2")
    assert row.iloc[0]["attendance"] == 90


def test_student_lookup_rejects_duplicate_ids():
    source = pd.DataFrame({"learner": ["S-1", "S-1"]})
    with pytest.raises(ValueError, match="exactly one"):
        student_source_row(source, {"learner": "student_id"}, "S-1")


def test_submission_rate_only_when_due_and_submitted_exist():
    assert "submission_rate" in available_model_fields(
        {"due": "assignments_due", "done": "assignments_submitted"}, "School"
    )
    assert "submission_rate" not in available_model_fields(
        {"done": "assignments_submitted"}, "College"
    )


def test_missing_student_id_names_expected_csv_header():
    with pytest.raises(ValueError, match="expects 'learner_id'"):
        canonicalize(pd.DataFrame({"attendance": [0.8]}), {"column_map": {"learner_id": "student_id"}})


def test_column_suggestions_are_conservative_and_include_samples():
    suggestions = suggest_column_mappings(
        ["learner_id", "score", "misc"],
        {"learner_id": ["L-1"], "score": [82], "misc": ["x"]},
    )

    assert suggestions[0]["suggested_field"] == "student_id"
    assert suggestions[0]["confidence"] == "high"
    assert suggestions[0]["sample_values"] == ["L-1"]
    assert suggestions[1]["suggested_field"] == "assessment_average"
    assert suggestions[1]["confidence"] == "review"
    assert suggestions[2]["suggested_field"] == ""


def test_automatic_mapping_recognises_learning_headers_but_never_historical_outcome():
    mapping = automatic_column_mapping([
        "learner_id", "modules_enrolled", "modules_evaluated",
        "first_semester_average", "credits_completed_percent",
        "academic_engagement", "confirmed_dropout", "unrelated_note",
    ])
    assert mapping["learner_id"] == "student_id"
    assert mapping["modules_enrolled"] == "assignments_due"
    assert mapping["first_semester_average"] == "assessment_average"
    assert "confirmed_dropout" not in mapping
    assert "unrelated_note" not in mapping


def test_column_mapping_requires_id_and_unique_fields():
    with pytest.raises(ValueError, match="Student identifier"):
        validate_column_mapping(["learner_id"], {})
    with pytest.raises(ValueError, match="(?i)only one CSV column"):
        validate_column_mapping(
            ["learner", "student"], {"learner": "student_id", "student": "student_id"}
        )
    with pytest.raises(ValueError, match="not present"):
        validate_column_mapping(["learner"], {"missing": "student_id"})
