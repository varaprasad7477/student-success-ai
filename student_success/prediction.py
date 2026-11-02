from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .rules import evaluate_rules
from .schema import MODEL_FIELDS, canonicalize


FRIENDLY = {
    "attendance_rate": "attendance rate",
    "submission_rate": "assignment submission rate",
    "assessment_average": "assessment average",
    "assessment_change": "recent assessment change",
    "days_since_login": "days since last login",
    "support_contacts": "support contact count",
    "credits_completed_ratio": "credit completion",
    "engagement_score": "learning engagement",
    "assignments_due": "assignments due",
    "assignments_submitted": "assignments submitted",
}

SUPPORTIVE_LANGUAGE = {
    "attendance_rate": ("Attendance has been lower than usual in the available record.", "Check whether timetable, transport, health, or access issues are affecting attendance."),
    "submission_rate": ("Fewer expected pieces of work have been submitted than is typical here.", "Review which tasks are still achievable and ask what is getting in the way."),
    "assessment_average": ("Recorded assessment results have been lower than is typical here.", "Review recent work with the student and offer academic support."),
    "credits_completed_ratio": ("The student has completed a smaller share of enrolled credits than is typical here.", "Check academic progress and agree a realistic recovery plan."),
    "engagement_score": ("Recorded learning activity has been lower than is typical here.", "Check platform access and invite the student to discuss their experience."),
    "days_since_login": ("There has been a longer gap in recorded platform activity than is typical here.", "Check whether the student can access the platform and whether another contact method is needed."),
    "assessment_change": ("Recent assessment results have declined compared with earlier work.", "Review the timeline with the student before deciding what support is useful."),
}

# These are transparent review points for the student-facing evidence panel.
# They are not hidden model thresholds and can later be moved into each
# institution's policy configuration.
REVIEW_TARGETS = {
    "attendance_rate": (0.75, "Attendance", "minimum 75% attendance", "below"),
    "submission_rate": (0.60, "Work submitted", "at least 60% of expected work", "below"),
    "assessment_average": (50.0, "Assessment result", "at least 50% assessment result", "below"),
    "credits_completed_ratio": (0.50, "Credit progress", "at least 50% credits completed", "below"),
    "engagement_score": (0.60, "Learning engagement", "at least 60% recorded engagement", "below"),
    "days_since_login": (14.0, "Platform activity", "no more than 14 days since activity", "above"),
}


def student_signal_checks(row: pd.Series, fields: list[str] | None = None, review_targets: dict | None = None) -> list[dict]:
    """Return human-readable value-versus-review-target evidence."""
    allowed = set(fields or REVIEW_TARGETS)
    configured = review_targets or {}
    checks = []
    for field, (default_target, label, target_text, direction) in REVIEW_TARGETS.items():
        if field not in allowed:
            continue
        target = float(configured.get(field, default_target))
        if field == "attendance_rate": target_text = f"minimum {target:.0%} attendance"
        elif field == "submission_rate": target_text = f"at least {target:.0%} of expected work"
        elif field == "assessment_average": target_text = f"at least {target:.0f}% assessment result"
        elif field == "credits_completed_ratio": target_text = f"at least {target:.0%} credits completed"
        elif field == "engagement_score": target_text = f"at least {target:.0%} recorded engagement"
        elif field == "days_since_login": target_text = f"no more than {target:.0f} days since activity"
        value = row.get(field, np.nan)
        if pd.isna(value):
            continue
        value = float(value)
        needs_review = value > target if direction == "above" else value < target
        checks.append({
            "field": field,
            "label": label,
            "value": value,
            "target": target,
            "target_text": target_text,
            "direction": direction,
            "needs_review": needs_review,
        })
    return checks


def plain_language_evidence(reasons: list[dict]) -> list[dict]:
    """Describe observable signals, never infer a student's ability or personal cause."""
    items = []
    for reason in reasons:
        field = reason.get("feature")
        if field not in SUPPORTIVE_LANGUAGE:
            continue
        value, baseline = reason.get("value"), reason.get("baseline")
        if value is None or baseline is None:
            continue
        concerning = value > baseline if field == "days_since_login" else value < baseline
        if not concerning:
            continue
        observation, next_step = SUPPORTIVE_LANGUAGE[field]
        if reason.get("basis") == "institution target":
            if field == "days_since_login":
                observation = f"No recorded platform activity for {value:g} days; your institution's limit is {baseline:g} days."
            else:
                multiplier = 1 if field == "assessment_average" else 100
                observation = f"{FRIENDLY[field].capitalize()} is {value * multiplier:.1f}%; your institution's minimum is {baseline * multiplier:.1f}%."
        items.append({"field": field, "observation": observation, "next_step": next_step})
    return items


class PredictionService:
    def __init__(self, config: dict, model_path: str | Path | None = None, allow_demo_score: bool = True):
        self.config = config
        self.allow_demo_score = allow_demo_score
        self.bundle = None
        if model_path and Path(model_path).exists():
            import joblib

            self.bundle = joblib.load(model_path)
            bound_to = self.bundle.get("institution_id")
            if bound_to and bound_to != config.get("institution_id"):
                raise ValueError("Model institution does not match the active data schema.")

    def _fallback_probability(self, row: pd.Series) -> float:
        """Transparent institution-target-based risk screen for new workspaces."""
        targets = {field: spec[0] for field, spec in REVIEW_TARGETS.items()}
        targets.update(self.config.get("review_targets", {}))
        attendance_target = float(targets["attendance_rate"])
        submission_target = float(targets["submission_rate"])
        assessment_target = float(targets["assessment_average"])
        activity_target = float(targets["days_since_login"])
        credits_target = float(targets["credits_completed_ratio"])
        engagement_target = float(targets["engagement_score"])

        def shortfall(value: float, target: float) -> float:
            # Several small misses across different learning signals should
            # become visible as a medium-support priority, not disappear.
            return min(1.0, 3.2 * max(0.0, (target - value) / max(target, 0.01)))

        values = {
            "attendance": shortfall(row.get("attendance_rate", np.nan), attendance_target) if pd.notna(row.get("attendance_rate", np.nan)) else np.nan,
            "submission": shortfall(row.get("submission_rate", np.nan), submission_target) if pd.notna(row.get("submission_rate", np.nan)) else np.nan,
            "assessment": shortfall(row.get("assessment_average", np.nan), assessment_target) if pd.notna(row.get("assessment_average", np.nan)) else np.nan,
            "inactivity": min(1.0, 3.2 * max(0.0, (row.get("days_since_login", np.nan) - activity_target) / max(activity_target, 1))) if pd.notna(row.get("days_since_login", np.nan)) else np.nan,
            "credits": shortfall(row.get("credits_completed_ratio", np.nan), credits_target) if pd.notna(row.get("credits_completed_ratio", np.nan)) else np.nan,
            "engagement": shortfall(row.get("engagement_score", np.nan), engagement_target) if pd.notna(row.get("engagement_score", np.nan)) else np.nan,
        }
        available = {key: value for key, value in values.items() if pd.notna(value)}
        if len(available) < 3:
            return float("nan")
        weights = {"attendance": .25, "submission": .20, "assessment": .20, "inactivity": .10, "credits": .10, "engagement": .15}
        denominator = sum(weights[key] for key in available)
        return float(sum(available[key] * weights[key] for key in available) / denominator)

    def _probability(self, frame: pd.DataFrame) -> np.ndarray:
        if self.bundle:
            return self.bundle["model"].predict_proba(frame[self.bundle["feature_names"]])[:, 1]
        if not self.allow_demo_score:
            return np.full(len(frame), np.nan)
        return np.array([self._fallback_probability(row) for _, row in frame.iterrows()])

    def _reason_codes(self, row: pd.Series, probability: float) -> list[dict]:
        medians = (self.bundle or {}).get("training_medians", {})
        candidates = []
        directions = {
            "attendance_rate": -1, "submission_rate": -1, "assessment_average": -1,
            "assessment_change": -1, "days_since_login": 1, "support_contacts": 1,
            "credits_completed_ratio": -1,
            "engagement_score": -1,
        }
        scales = {"attendance_rate": .20, "submission_rate": .25, "assessment_average": 20,
                  "assessment_change": 15, "days_since_login": 14, "support_contacts": 3,
                  "credits_completed_ratio": .20}
        scales["engagement_score"] = .20
        review_targets = {field: spec[0] for field, spec in REVIEW_TARGETS.items()}
        review_targets.update(self.config.get("review_targets", {}))
        defaults = {"attendance_rate": review_targets["attendance_rate"], "submission_rate": review_targets["submission_rate"],
                    "assessment_average": review_targets["assessment_average"], "assessment_change": 0,
                    "days_since_login": review_targets["days_since_login"], "support_contacts": 0,
                    "credits_completed_ratio": review_targets["credits_completed_ratio"]}
        defaults["engagement_score"] = review_targets["engagement_score"]
        for field, direction in directions.items():
            if self.bundle and field not in self.bundle["feature_names"]:
                continue
            if not self.bundle and field not in review_targets:
                continue
            actual = row.get(field)
            if pd.isna(actual):
                continue
            baseline = medians.get(field, defaults[field])
            risk_strength = direction * (actual - baseline) / scales[field]
            if risk_strength > 0:
                candidates.append((risk_strength, field, actual, baseline))
        candidates.sort(reverse=True)
        return [{
            "feature": field,
            "label": FRIENDLY[field],
            "value": float(actual),
            "baseline": float(baseline),
            "basis": "training comparison" if self.bundle else "institution target",
            "direction": "increases risk",
            "message": f"{FRIENDLY[field].capitalize()} is less favorable than the typical reference level.",
        } for _, field, actual, baseline in candidates[:4]]

    def predict(self, source: pd.DataFrame, include_explanations: bool = True) -> tuple[pd.DataFrame, list[str]]:
        validated = canonicalize(source, self.config, training=False)
        frame = validated.frame
        self.last_dataset_issues = validated.dataset_issues
        probabilities = self._probability(frame)
        medium = self.config.get("risk_thresholds", {}).get("medium", .35)
        high = self.config.get("risk_thresholds", {}).get("high", .65)
        results = []
        for position, (_, row) in enumerate(frame.iterrows()):
            probability = probabilities[position]
            minimum = float(self.config.get("minimum_data_completeness", .70))
            enough = row["data_completeness"] >= minimum and not bool(row["critical_data_missing"]) and pd.notna(probability)
            if not self.bundle and not self.allow_demo_score:
                band = "Not scored"
            elif not enough:
                band = "Insufficient data"
            elif probability >= high:
                band = "High"
            elif probability >= medium:
                band = "Medium"
            else:
                band = "Low"
            results.append({
                "student_id": row["student_id"],
                "risk_probability": float(probability) if enough and self.bundle else None,
                "screening_index": float(probability) if enough and not self.bundle else None,
                "review_range_low": None,
                "review_range_high": None,
                "risk_band": band,
                "data_completeness": float(row["data_completeness"]),
                "missing_fields": list(row["missing_fields"]),
                "critical_data_missing": bool(row["critical_data_missing"]),
                "model_status": "trained model" if self.bundle else ("transparent dropout-risk screen" if self.allow_demo_score else "no validated model"),
                "prediction_horizon": self.config.get("prediction_horizon", "Not approved"),
                "reason_codes": self._reason_codes(row, probability) if enough and include_explanations else [],
                "policy_flags": evaluate_rules(row.to_dict(), self.config.get("rules", [])),
            })
        return pd.DataFrame(results), validated.warnings

