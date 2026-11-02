"""Small, testable helpers for the teacher workflow."""

from __future__ import annotations

import re

import pandas as pd

from .schema import NUMERIC_FIELDS


FIELD_LABELS = {
    "student_id": "Student identifier",
    "attendance_rate": "Attendance rate",
    "assignments_due": "Assignments due",
    "assignments_submitted": "Assignments submitted / evaluated",
    "assessment_average": "Assessment average",
    "assessment_change": "Assessment change",
    "days_since_login": "Days since last login",
    "support_contacts": "Support contacts",
    "credits_completed_ratio": "Credits completed ratio",
    "engagement_score": "Engagement score",
    "outcome": "Historical outcome (training only)",
}

_FIELD_ALIASES = {
    "student_id": {"studentid", "learnerid", "idstudent", "studentnumber", "learnernumber"},
    "attendance_rate": {"attendance", "attendancerate", "attendancepercent", "attendancepercentage"},
    "assignments_due": {"assignmentsdue", "assessmentdue", "assessmentsdue", "moduleseenrolled", "modulesenrolled", "assessments_due_28"},
    "assignments_submitted": {
        "assignmentssubmitted", "assessmentssubmitted", "assignmentsevaluated", "modulesevaluated",
        "assessments_submitted_28",
    },
    "assessment_average": {
        "assessmentaverage", "averageassessment", "averagemark", "gradeaverage", "firstsemesteraverage", "assessment_average_28",
    },
    "assessment_change": {"assessmentchange", "scorechange", "gradechange"},
    "days_since_login": {"dayssincelogin", "dayssinceactivity", "dayssince lastlogin", "days_since_activity_28"},
    "support_contacts": {"supportcontacts", "numberofsupportcontacts"},
    "credits_completed_ratio": {"creditscompletedratio", "creditscompletedpercent", "creditscompleted", "creditcompletionrate"},
    "engagement_score": {
        "engagementscore", "academicengagement", "active dayratio", "active_day_ratio_28",
    },
    "outcome": {
        "historicaloutcome", "dropoutrisk", "withdrawnafter28", "confirmeddropout", "withdrawn_after_28",
    },
}
_REVIEW_ONLY_ALIASES = {
    "student_id": {"student", "learner"},
    "attendance_rate": {"attendance", "attended", "attendancepercent", "attendancepercentage"},
    "assessment_average": {"grade", "score", "mark", "result"},
    "credits_completed_ratio": {"creditscompleted", "creditscompletedpercent", "creditcompletion"},
    "outcome": {"outcome", "status", "target", "label"},
}
_MAPPABLE_FIELDS = ["student_id", *NUMERIC_FIELDS, "outcome"]


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def suggest_column_mappings(
    columns: list[str], sample_values: dict[str, list], configured_map: dict[str, str] | None = None,
) -> list[dict]:
    """Suggest conservative mappings; ambiguous names are surfaced for human review."""
    configured_map = configured_map or {}
    exact_aliases = {
        _normalized_header(alias): field
        for field, aliases in _FIELD_ALIASES.items()
        for alias in aliases | {field}
    }
    review_aliases = {
        _normalized_header(alias): field
        for field, aliases in _REVIEW_ONLY_ALIASES.items()
        for alias in aliases
    }
    suggestions = []
    for column in columns:
        configured = configured_map.get(column)
        normalized = _normalized_header(column)
        if configured in FIELD_LABELS:
            field, confidence, reason = configured, "high", "Matches this workspace's saved mapping."
        elif normalized in exact_aliases:
            field, confidence, reason = exact_aliases[normalized], "high", "Exact known header synonym."
        elif normalized in review_aliases:
            field, confidence, reason = review_aliases[normalized], "review", "Ambiguous header; confirm its meaning."
        else:
            field, confidence, reason = "", "none", "No safe suggestion; choose only if you know the field meaning."
        if field == "outcome":
            field, confidence, reason = "", "none", "Historical outcomes are excluded from live prediction."
        suggestions.append({
            "column": column,
            "suggested_field": field,
            "confidence": confidence,
            "reason": reason,
            "sample_values": [None if pd.isna(value) else str(value)[:80] for value in sample_values.get(column, [])],
        })
    return suggestions


def automatic_column_mapping(columns: list[str], configured_map: dict[str, str] | None = None) -> dict[str, str]:
    """Return only unambiguous header matches.

    This deliberately does not guess from vague headers such as ``score`` or
    ``status``.  A CSV is either recognisable enough to screen safely, or the
    user receives one short, actionable message rather than a large mapping
    form.
    """
    configured_map = configured_map or {}
    exact_aliases = {
        _normalized_header(alias): field
        for field, aliases in _FIELD_ALIASES.items()
        for alias in aliases | {field}
    }
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for column in columns:
        field = configured_map.get(column) or exact_aliases.get(_normalized_header(column))
        # Historical labels are useful for later evaluation, never as an input
        # to a live dropout-risk screen.
        if field == "outcome":
            continue
        if field in used:
            raise ValueError(f"Multiple CSV columns identify {FIELD_LABELS[field]}. Keep one unambiguous column for that meaning.")
        if field in FIELD_LABELS and field not in used:
            mapping[column] = field
            used.add(field)
    return mapping


def validate_column_mapping(columns: list[str], column_map: dict) -> dict[str, str]:
    if not isinstance(column_map, dict) or not column_map:
        raise ValueError("Confirm at least the Student identifier mapping before upload.")
    normalized_map: dict[str, str] = {}
    for source, target in column_map.items():
        if not isinstance(source, str) or source not in columns:
            raise ValueError(f"Mapped CSV column {source!r} is not present in the uploaded file.")
        if not isinstance(target, str) or target not in FIELD_LABELS:
            raise ValueError(f"Unsupported mapped field {target!r}.")
        if target == "outcome":
            raise ValueError("Historical outcomes cannot be mapped as live prediction inputs.")
        if target in normalized_map.values():
            raise ValueError(f"Only one CSV column can be mapped to {FIELD_LABELS[target]}.")
        normalized_map[source] = target
    if "student_id" not in normalized_map.values():
        raise ValueError("Map one CSV column to Student identifier before uploading.")
    return normalized_map


def student_source_row(source: pd.DataFrame, column_map: dict[str, str], student_id: str) -> pd.DataFrame:
    """Find a student using the configured ID column, regardless of CSV column order."""
    id_columns = [name for name, meaning in column_map.items() if meaning == "student_id"]
    if len(id_columns) != 1 or id_columns[0] not in source:
        raise ValueError("The mapped student ID column is missing from this CSV.")
    matches = source.loc[source[id_columns[0]].astype(str).str.strip().eq(str(student_id).strip())]
    if len(matches) != 1:
        raise ValueError("The selected student does not have exactly one matching source record.")
    return matches


def available_model_fields(column_map: dict[str, str], institution_type: str) -> list[str]:
    available = set(column_map.values()) & {
        "attendance_rate", "assignments_due", "assignments_submitted",
        "assessment_average", "assessment_change", "days_since_login",
        "support_contacts", "credits_completed_ratio", "engagement_score",
    }
    if {"assignments_due", "assignments_submitted"} <= available:
        available.add("submission_rate")
    if institution_type == "University":
        available.discard("assessment_change")
    return sorted(available)
