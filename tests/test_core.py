import json
from pathlib import Path

import pandas as pd
import pytest

from student_success.prediction import PredictionService, plain_language_evidence
from student_success.rules import evaluate_rules
from student_success.schema import canonicalize


CONFIG = json.loads((Path(__file__).parents[1] / "config/institutions/example.json").read_text())


def row(student="S1", attendance=50):
    return pd.DataFrame([{
        "Student ID": student, "Attendance %": attendance, "Assignments Due": 10,
        "Assignments Submitted": 5, "Average Mark": 55, "Score Change": -5,
        "Days Since Login": 18, "Support Contacts": 2, "Credits Completed %": 60,
    }])


def test_prediction_is_independent_of_other_rows():
    service = PredictionService(CONFIG)
    alone, _ = service.predict(row())
    together, _ = service.predict(pd.concat([row(), row("S2", 95)], ignore_index=True))
    assert alone.iloc[0].risk_probability == pytest.approx(together.iloc[0].risk_probability)


def test_percent_units_are_converted_and_validated():
    result = canonicalize(row(attendance=75), CONFIG)
    assert result.frame.iloc[0].attendance_rate == pytest.approx(.75)
    with pytest.raises(ValueError):
        canonicalize(row(attendance=175), CONFIG)


def test_rules_are_separate_and_traceable():
    flags = evaluate_rules({"attendance_rate": .5}, CONFIG["rules"])
    assert flags[0]["id"] == "attendance-critical"
    assert flags[0]["actual"] == .5


def test_duplicate_students_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        canonicalize(pd.concat([row(), row()], ignore_index=True), CONFIG)


def test_blank_and_malformed_ids_are_rejected():
    with pytest.raises(ValueError, match="student_id is blank"):
        canonicalize(row(student="  "), CONFIG)
    with pytest.raises(ValueError, match="duplicate"):
        canonicalize(pd.concat([row(" S1 "), row("S1")], ignore_index=True), CONFIG)


def test_non_numeric_input_is_reported_as_data_issue():
    source = row()
    source.loc[0, "Average Mark"] = "not recorded"
    result = canonicalize(source, CONFIG)
    assert any(issue["issue"] == "non-numeric value" and issue["field"] == "assessment_average"
               for issue in result.dataset_issues)


def test_missing_fields_are_disclosed_and_can_block_scoring():
    config = {**CONFIG, "critical_fields": ["attendance_rate"], "minimum_data_completeness": .5}
    source = row().drop(columns=["Attendance %"])
    result = canonicalize(source, config)
    assert "attendance_rate" in result.frame.iloc[0].missing_fields
    assert bool(result.frame.iloc[0].critical_data_missing)
    prediction, _ = PredictionService(config).predict(source)
    assert prediction.iloc[0].risk_band == "Insufficient data"
    assert pd.isna(prediction.iloc[0].risk_probability)


def test_plain_language_evidence_does_not_claim_a_cause():
    reasons = [{"feature": "assessment_average", "value": 42.0, "baseline": 65.0},
               {"feature": "assignments_due", "value": 12.0, "baseline": 8.0}]
    items = plain_language_evidence(reasons)
    assert len(items) == 1
    assert "Recorded assessment results" in items[0]["observation"]
    assert "incapable" not in str(items).lower()


def test_unvalidated_institution_is_not_given_a_probability():
    result, _ = PredictionService(CONFIG, allow_demo_score=False).predict(row())
    assert result.iloc[0].risk_band == "Not scored"
    assert pd.isna(result.iloc[0].risk_probability)


def test_prediction_contains_horizon_and_review_range():
    config = {**CONFIG, "prediction_horizon": "Week 8", "minimum_data_completeness": .5}
    prediction, _ = PredictionService(config).predict(row())
    item = prediction.iloc[0]
    assert item.prediction_horizon == "Week 8"
    assert 0 <= item.review_range_low <= item.risk_probability <= item.review_range_high <= 1

