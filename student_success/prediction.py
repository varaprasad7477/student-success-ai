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

    @staticmethod
    def _fallback_probability(row: pd.Series) -> float:
        values = {
            "attendance": 1 - row.get("attendance_rate", np.nan),
            "submission": 1 - row.get("submission_rate", np.nan),
            "assessment": 1 - row.get("assessment_average", np.nan) / 100,
            "inactivity": min(row.get("days_since_login", np.nan) / 30, 1),
            "credits": 1 - row.get("credits_completed_ratio", np.nan),
            "engagement": 1 - row.get("engagement_score", np.nan),
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
        if self.bundle:
            feature_names = self.bundle["feature_names"]
            base = pd.DataFrame([{field: row.get(field, np.nan) for field in feature_names}], dtype=float)
            candidates = []
            for field in feature_names:
                actual = row.get(field)
                baseline = medians.get(field)
                if pd.isna(actual) or baseline is None or field not in FRIENDLY:
                    continue
                counterfactual = base.copy()
                counterfactual.loc[0, field] = baseline
                counterfactual_probability = self.bundle["model"].predict_proba(counterfactual)[:, 1][0]
                contribution = probability - counterfactual_probability
                if contribution >= 0.005:
                    candidates.append((contribution, field, actual, baseline))
            candidates.sort(reverse=True)
            return [{
                "feature": field,
                "label": FRIENDLY[field],
                "value": float(actual),
                "baseline": float(baseline),
                "direction": "increases risk",
                "impact": float(contribution),
                "message": f"At the typical training value for {FRIENDLY[field]}, this model's estimated risk would be about {contribution:.1%} lower.",
            } for contribution, field, actual, baseline in candidates[:4]]

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
        defaults = {"attendance_rate": .80, "submission_rate": .80, "assessment_average": 65,
                    "assessment_change": 0, "days_since_login": 7, "support_contacts": 0,
                    "credits_completed_ratio": .75}
        defaults["engagement_score"] = .70
        for field, direction in directions.items():
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
            "direction": "increases risk",
            "message": f"{FRIENDLY[field].capitalize()} is less favorable than the reference level.",
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
            uncertainty = min(.25, .05 + (1.0 - float(row["data_completeness"])) * .35)
            results.append({
                "student_id": row["student_id"],
                "risk_probability": None if not enough else float(probability),
                "review_range_low": None if not enough else float(max(0, probability - uncertainty)),
                "review_range_high": None if not enough else float(min(1, probability + uncertainty)),
                "risk_band": band,
                "data_completeness": float(row["data_completeness"]),
                "missing_fields": list(row["missing_fields"]),
                "critical_data_missing": bool(row["critical_data_missing"]),
                "model_status": "trained model" if self.bundle else ("transparent demo score" if self.allow_demo_score else "no validated model"),
                "prediction_horizon": self.config.get("prediction_horizon", "Not approved"),
                "reason_codes": self._reason_codes(row, probability) if enough and include_explanations else [],
                "policy_flags": evaluate_rules(row.to_dict(), self.config.get("rules", [])),
            })
        return pd.DataFrame(results), validated.warnings

