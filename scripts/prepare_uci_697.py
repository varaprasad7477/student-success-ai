"""Prepare UCI dataset 697 for the Student Success AI canonical schema.

Source: https://archive.ics.uci.edu/dataset/697/predict%2Bstudents%2Bdropout%2Band%2Bacademic%2Bsuccess
License: Creative Commons Attribution 4.0 International
Citation: Realinho, V., Vieira Martins, M., Machado, J., & Baptista, L. (2021).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return np.where(denominator > 0, numerator / denominator, np.nan)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = pd.read_csv(args.input)
    # "Enrolled" is not a confirmed success/non-dropout outcome. Excluding it avoids
    # teaching a binary classifier that every currently enrolled student is safe.
    frame = source[source["Target"].isin(["Dropout", "Graduate"])].copy().reset_index(drop=True)
    enrolled_1 = frame["Curricular units 1st sem (enrolled)"]
    evaluated_1 = frame["Curricular units 1st sem (evaluations)"]
    approved_1 = frame["Curricular units 1st sem (approved)"]
    approval_rate = pd.Series(safe_ratio(approved_1, enrolled_1), index=frame.index).clip(0, 1)
    evaluation_rate = pd.Series(safe_ratio(evaluated_1, enrolled_1), index=frame.index).clip(0, 1)

    prepared = pd.DataFrame({
        "learner_id": [f"NMU-{number:05d}" for number in range(1, len(frame) + 1)],
        "modules_enrolled": enrolled_1,
        # Evaluation attempts may exceed enrolled modules because of repeated attempts.
        # The canonical submitted-count field represents modules with participation,
        # so cap attempts at the number of enrolled modules.
        "modules_evaluated": np.minimum(evaluated_1, enrolled_1),
        "first_semester_average": (frame["Curricular units 1st sem (grade)"] * 5).clip(0, 100),
        "semester_score_change": ((frame["Curricular units 2nd sem (grade)"] - frame["Curricular units 1st sem (grade)"]) * 5).clip(-100, 100),
        "credits_completed_percent": approval_rate * 100,
        "academic_engagement": pd.concat([approval_rate, evaluation_rate], axis=1).mean(axis=1),
        "gender_audit": frame["Gender"].map({0: "Female", 1: "Male"}).fillna("Unknown"),
        "age_band_audit": pd.cut(frame["Age at enrollment"], bins=[0, 20, 24, 29, 100], labels=["20 or younger", "21-24", "25-29", "30+"]).astype(str),
        "confirmed_dropout": (frame["Target"] == "Dropout").astype(int),
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(args.output, index=False)
    print({
        "source_rows": len(source), "prepared_rows": len(prepared),
        "excluded_enrolled_rows": int((source["Target"] == "Enrolled").sum()),
        "dropout_rate": float(prepared["confirmed_dropout"].mean()),
        "output": str(args.output),
    })


if __name__ == "__main__":
    main()

