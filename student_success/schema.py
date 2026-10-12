from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


NUMERIC_FIELDS = [
    "attendance_rate",
    "assignments_due",
    "assignments_submitted",
    "assessment_average",
    "assessment_change",
    "days_since_login",
    "support_contacts",
    "credits_completed_ratio",
    "engagement_score",
]
MODEL_FIELDS = NUMERIC_FIELDS + ["submission_rate"]
RANGES = {
    "attendance_rate": (0, 1),
    "assignments_due": (0, None),
    "assignments_submitted": (0, None),
    "assessment_average": (0, 100),
    "assessment_change": (-100, 100),
    "days_since_login": (0, None),
    "support_contacts": (0, None),
    "credits_completed_ratio": (0, 1),
    "engagement_score": (0, 1),
}


@dataclass(frozen=True)
class ValidationResult:
    frame: pd.DataFrame
    warnings: list[str]
    dataset_issues: list[dict]


def load_config(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonicalize(source: pd.DataFrame, config: dict, training: bool = False) -> ValidationResult:
    column_map = config.get("column_map", {})
    frame = source.rename(columns=column_map).copy()
    if frame.columns.duplicated().any():
        duplicates = sorted(set(frame.columns[frame.columns.duplicated()].tolist()))
        raise ValueError(f"Multiple CSV columns map to the same field: {', '.join(duplicates)}")
    required = {"student_id"} | ({"outcome"} if training else set())
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required mapped fields: {', '.join(missing)}")

    warnings: list[str] = []
    dataset_issues: list[dict] = []
    units = config.get("units", {})
    relevant_fields = set(config.get("model_fields", MODEL_FIELDS)) | set(config.get("critical_fields", []))
    relevant_fields.update(rule.get("field") for rule in config.get("rules", []))
    for field in NUMERIC_FIELDS:
        if field not in frame:
            frame[field] = np.nan
            if field in relevant_fields:
                warnings.append(f"{field} is unavailable; records that need it may not be scored.")
                dataset_issues.append({"field": field, "issue": "column unavailable", "affected_rows": len(frame)})
        original = frame[field]
        frame[field] = pd.to_numeric(original, errors="coerce")
        malformed = original.notna() & original.astype(str).str.strip().ne("") & frame[field].isna()
        if malformed.any() and field in relevant_fields:
            count = int(malformed.sum())
            warnings.append(f"{field} has {count} non-numeric value(s); those rows need source correction.")
            dataset_issues.append({"field": field, "issue": "non-numeric value", "affected_rows": count})
        if units.get(field) == "percent":
            frame[field] = frame[field] / 100.0
        low, high = RANGES[field]
        invalid = frame[field].notna() & (frame[field] < low)
        if high is not None:
            invalid |= frame[field].notna() & (frame[field] > high)
        if invalid.any():
            raise ValueError(f"{field} contains {int(invalid.sum())} out-of-range value(s).")

    due = frame["assignments_due"]
    submitted = frame["assignments_submitted"]
    impossible = due.notna() & submitted.notna() & (submitted > due)
    if impossible.any():
        raise ValueError("assignments_submitted cannot exceed assignments_due.")
    frame["submission_rate"] = np.where(due > 0, submitted / due, np.nan)
    blank_id = frame["student_id"].isna() | frame["student_id"].astype(str).str.strip().eq("")
    if blank_id.any():
        raise ValueError(f"student_id is blank on {int(blank_id.sum())} row(s).")
    frame["student_id"] = frame["student_id"].astype(str).str.strip()
    if training:
        frame["outcome"] = pd.to_numeric(frame["outcome"], errors="raise").astype(int)
        if not set(frame["outcome"].unique()).issubset({0, 1}):
            raise ValueError("outcome must contain only 0 and 1.")
    completeness_fields = config.get("model_fields", MODEL_FIELDS)
    invalid_fields = sorted(set(completeness_fields) - set(MODEL_FIELDS))
    if invalid_fields:
        raise ValueError(f"Unknown model_fields in configuration: {', '.join(invalid_fields)}")
    missing_share = frame[completeness_fields].isna().mean(axis=1)
    frame["data_completeness"] = 1.0 - missing_share
    frame["missing_fields"] = frame[completeness_fields].apply(
        lambda row: [field for field in completeness_fields if pd.isna(row[field])], axis=1
    )
    critical_fields = [field for field in config.get("critical_fields", []) if field in completeness_fields]
    frame["critical_data_missing"] = frame[critical_fields].isna().any(axis=1) if critical_fields else False
    for field in completeness_fields:
        count = int(frame[field].isna().sum())
        if count:
            dataset_issues.append({"field": field, "issue": "missing values", "affected_rows": count})
    if frame["student_id"].duplicated().any():
        count = int(frame["student_id"].duplicated(keep=False).sum())
        raise ValueError(f"student_id contains {count} duplicate row(s); one current record per student is required.")
    return ValidationResult(frame=frame, warnings=warnings, dataset_issues=dataset_issues)

