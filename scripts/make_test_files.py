"""Reproducible public-benchmark upload fixtures; no synthetic labels are invented."""
from pathlib import Path

import pandas as pd


root = Path(__file__).resolve().parents[1]
source = pd.read_csv(root / "data/oulad_day28_prepared.csv")
holdout = source.loc[source.code_presentation.eq("2014J")].sample(n=300, random_state=42)
clean = holdout[["learner_id", "assessments_due_28", "assessments_submitted_28",
                 "assessment_average_28", "days_since_activity_28", "active_day_ratio_28",
                 "withdrawn_after_28"]].sort_values("learner_id")
destination = root / "data/test_uploads"
destination.mkdir(parents=True, exist_ok=True)
clean.to_csv(destination / "oulad_clean_labeled_300.csv", index=False)

# Same learners, with essential columns missing: expected to abstain, not pretend accuracy.
partial = clean.drop(columns=["assessment_average_28", "active_day_ratio_28", "days_since_activity_28",
                              "withdrawn_after_28"]).copy()
partial.to_csv(destination / "oulad_missing_features_300.csv", index=False)

# No learner identifier: expected to fail the schema check with a clear error.
broken = clean.head(20).drop(columns=["learner_id", "withdrawn_after_28"])
broken.to_csv(destination / "oulad_missing_id_20.csv", index=False)
print(f"Created test CSVs in {destination}")
