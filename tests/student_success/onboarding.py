"""Institution setup defaults and readiness checks for the local pilot."""

from __future__ import annotations

import re

from .workflow import available_model_fields


ALLOWED_INSTITUTION_TYPES = {"School", "College", "University"}
ALLOWED_FIELDS = {
    "attendance_rate", "assignments_due", "assignments_submitted",
    "assessment_average", "assessment_change", "days_since_login",
    "support_contacts", "credits_completed_ratio", "engagement_score",
}

DEFAULT_FIELDS = {
    "School": ["attendance_rate", "assignments_due", "assignments_submitted", "assessment_average", "days_since_login"],
    "College": ["attendance_rate", "assignments_due", "assignments_submitted", "assessment_average", "engagement_score"],
    "University": ["assignments_due", "assignments_submitted", "assessment_average", "credits_completed_ratio", "engagement_score"],
}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def build_institution_config(
    institution_id: str,
    name: str,
    institution_type: str,
    prediction_horizon: str,
    term_label: str,
    data_owner: str,
    selected_fields: list[str] | None,
) -> dict:
    if institution_type not in ALLOWED_INSTITUTION_TYPES:
        raise ValueError("Choose School, College, or University.")
    fields = [field for field in (selected_fields or DEFAULT_FIELDS[institution_type]) if field in ALLOWED_FIELDS]
    if len(set(fields)) != len(fields):
        raise ValueError("Choose each learning signal only once.")
    if len(fields) < 2:
        raise ValueError("Choose at least two learning signals that are available before the review date.")
    column_map = {"student_id": "student_id", **{field: field for field in fields}}
    model_fields = available_model_fields(column_map, institution_type)
    critical = [field for field in ("attendance_rate", "assignments_due", "assignments_submitted", "assessment_average", "credits_completed_ratio") if field in model_fields]
    rules = []
    if "attendance_rate" in model_fields:
        rules.append({"id": "attendance-review", "field": "attendance_rate", "operator": "lt", "value": .65, "severity": "medium", "message": "Attendance is below the local review point. Verify the record and offer a conversation."})
    if "submission_rate" in model_fields:
        rules.append({"id": "submission-review", "field": "submission_rate", "operator": "lt", "value": .60, "severity": "medium", "message": "Fewer than 60% of expected work is recorded as submitted. Review what is still achievable."})
    if "days_since_login" in model_fields:
        rules.append({"id": "activity-review", "field": "days_since_login", "operator": "gt", "value": 14, "severity": "medium", "message": "There has been no recorded platform activity for more than 14 days. Check access and contact preferences."})
    return {
        "institution_id": institution_id,
        "display_name": name,
        "institution_type": institution_type,
        "prediction_horizon": prediction_horizon.strip(),
        "minimum_data_completeness": .70,
        "column_map": column_map,
        "units": {},
        "model_fields": model_fields,
        "critical_fields": critical,
        "risk_thresholds": {"medium": .35, "high": .65},
        "review_targets": {"attendance_rate": .75, "submission_rate": .60, "assessment_average": 50, "credits_completed_ratio": .50, "engagement_score": .60, "days_since_login": 14},
        "rules": rules,
        "onboarding": {
            "setup_required": True,
            "targets_confirmed": False,
            "term_label": term_label.strip(),
            "data_owner": data_owner.strip(),
            "signals_confirmed": fields,
            "setup_status": "data mapping required",
        },
    }


def readiness_check(config: dict, has_uploaded_data: bool, has_validated_model: bool) -> list[dict]:
    mapping = config.get("column_map", {})
    fields = set(mapping.values())
    return [
        {"name": "Institution and review period recorded", "passed": bool(config.get("display_name")) and bool(config.get("prediction_horizon")), "fallback": "Record the institution name and a prediction horizon before continuing."},
        {"name": "Student identifier mapped", "passed": "student_id" in fields, "fallback": "Map one unique student identifier column in Data setup."},
        {"name": "Learning signals selected", "passed": len(set(config.get("model_fields", [])) & ALLOWED_FIELDS) >= 2, "fallback": "Select at least two meaningful signals available before the review date."},
        {"name": "CSV validated", "passed": has_uploaded_data, "fallback": "Upload a CSV and correct missing, duplicate, or invalid values."},
        {"name": "Institution model validated", "passed": has_validated_model, "fallback": "Use local rules and supportive review only until a locally validated model is approved."},
    ]
