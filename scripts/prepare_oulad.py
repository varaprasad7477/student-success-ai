"""Build a leakage-controlled day-28 OULAD benchmark from the official UCI ZIP."""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd


KEY = ["code_module", "code_presentation", "id_student"]
CUTOFF = 28


def prepare(archive: Path) -> tuple[pd.DataFrame, dict]:
    with ZipFile(archive) as z:
        info = pd.read_csv(z.open("studentInfo.csv"))
        registrations = pd.read_csv(z.open("studentRegistration.csv"))
        assessments = pd.read_csv(z.open("assessments.csv"))
        submissions = pd.read_csv(z.open("studentAssessment.csv"))

        registrations["date_registration"] = pd.to_numeric(registrations.date_registration, errors="coerce")
        registrations["date_unregistration"] = pd.to_numeric(registrations.date_unregistration, errors="coerce")
        base = info.merge(registrations, on=KEY, how="inner", validate="one_to_one")
        before = len(base)
        # A day-28 prediction is meaningful only for students already registered and still enrolled.
        base = base.loc[base.date_registration.le(CUTOFF) &
                        (base.date_unregistration.isna() | base.date_unregistration.gt(CUTOFF))].copy()
        # Missing withdrawal timing cannot establish that a withdrawn learner was at risk on day 28.
        base = base.loc[base.final_result.ne("Withdrawn") | base.date_unregistration.gt(CUTOFF)].copy()
        base["withdrawn_after_28"] = base.final_result.eq("Withdrawn").astype(int)

        assessments["date"] = pd.to_numeric(assessments.date, errors="coerce")
        due = assessments.loc[assessments.date.between(0, CUTOFF, inclusive="both"),
                              ["code_module", "code_presentation", "id_assessment"]].copy()
        due_counts = due.groupby(KEY[:2]).size().rename("assessments_due_28").reset_index()
        base = base.merge(due_counts, on=KEY[:2], how="left")
        base["assessments_due_28"] = base.assessments_due_28.fillna(0).astype(int)

        submissions["date_submitted"] = pd.to_numeric(submissions.date_submitted, errors="coerce")
        submissions["score"] = pd.to_numeric(submissions.score, errors="coerce")
        valid = submissions.loc[submissions.date_submitted.le(CUTOFF) & submissions.is_banked.eq(0)]
        valid = valid.merge(due, on="id_assessment", how="inner", validate="many_to_one")
        valid = valid.sort_values("date_submitted").drop_duplicates(KEY + ["id_assessment"])
        submitted = valid.groupby(KEY).agg(assessments_submitted_28=("id_assessment", "nunique"),
                                             assessment_average_28=("score", "mean")).reset_index()
        base = base.merge(submitted, on=KEY, how="left")
        base["assessments_submitted_28"] = base.assessments_submitted_28.fillna(0).astype(int)

        activity_parts = []
        with z.open("studentVle.csv") as stream:
            for chunk in pd.read_csv(stream, chunksize=1_000_000):
                active = chunk.loc[chunk.date.between(0, CUTOFF, inclusive="both") & chunk.sum_click.gt(0), KEY + ["date"]]
                activity_parts.append(active.drop_duplicates())
        activity = pd.concat(activity_parts, ignore_index=True).drop_duplicates()
        observed = activity.groupby(KEY).agg(active_days_28=("date", "nunique"),
                                              last_activity_28=("date", "max")).reset_index()
        base = base.merge(observed, on=KEY, how="left")
        base["active_day_ratio_28"] = base.active_days_28.fillna(0) / (CUTOFF + 1)
        base["days_since_activity_28"] = CUTOFF - base.last_activity_28.fillna(-1)
        base["learner_id"] = ("OU-" + base.code_module + "-" + base.code_presentation + "-" +
                              base.id_student.astype(str))
        base = base.rename(columns={"gender": "gender_audit", "age_band": "age_band_audit"})
        columns = ["learner_id", "code_module", "code_presentation", "id_student", "gender_audit",
                   "age_band_audit", "assessments_due_28", "assessments_submitted_28",
                   "assessment_average_28", "days_since_activity_28", "active_day_ratio_28",
                   "withdrawn_after_28"]
        result = base[columns].sort_values("learner_id").reset_index(drop=True)
        assert result.learner_id.is_unique
        assert (result.assessments_submitted_28 <= result.assessments_due_28).all()
        audit = {"original_student_presentation_rows": before, "eligible_day28_rows": len(result),
                 "excluded_before_or_at_day28": before - len(result),
                 "withdrawal_rate_after_day28": float(result.withdrawn_after_28.mean()),
                 "presentation_counts": result.code_presentation.value_counts().sort_index().to_dict(),
                 "cutoff_day": CUTOFF}
        return result, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data, audit = prepare(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.output, index=False)
    print(audit)


if __name__ == "__main__":
    main()
