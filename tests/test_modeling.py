from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from student_success import modeling


def test_chronological_masks_keep_timestamps_in_order():
    values = pd.Series(pd.date_range("2020-01-01", periods=10).tolist() * 2)
    train, validation, test, timestamps = modeling._chronological_masks(values)

    assert timestamps[train].max() < timestamps[validation].min()
    assert timestamps[validation].max() < timestamps[test].min()
    assert np.all(train.astype(int) + validation.astype(int) + test.astype(int) == 1)


def test_chronological_training_reports_untouched_test(tmp_path, monkeypatch):
    rows_per_period = 60
    outcomes = np.tile([0, 1], rows_per_period // 2)
    frame = pd.DataFrame({
        "assignments_due": np.full(rows_per_period * 10, 10.0),
        "assignments_submitted": np.tile(np.where(outcomes == 1, 4.0, 9.0), 10),
        "assessment_average": np.tile(np.where(outcomes == 1, 40.0, 80.0), 10),
        "outcome": np.tile(outcomes, 10),
    })
    time_values = pd.Series(
        np.repeat(pd.date_range("2020-01-01", periods=10, freq="MS"), rows_per_period)
    )
    candidate = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", LogisticRegression()),
    ])
    monkeypatch.setattr(modeling, "build_candidates", lambda _: {"logistic_regression": candidate})

    report = modeling.train_temporal(
        frame,
        time_values,
        tmp_path,
        feature_names=["assignments_due", "assignments_submitted", "assessment_average"],
    )

    assert report["evaluation_design"] == "chronological_train_validation_test"
    assert report["status"] == "held_out_temporal_test"
    assert report["split_rows"] == {"train": 360, "validation": 120, "test": 120}
    assert report["winner"]["rows"] == report["split_rows"]["test"]
    assert report["validation_leaderboard"][0]["model"] == "logistic_regression"
    assert (Path(tmp_path) / "model_bundle.joblib").exists()
    assert (Path(tmp_path) / "metrics.json").exists()


def test_chronological_masks_reject_missing_or_sparse_timestamps():
    with pytest.raises(ValueError, match="valid timestamp"):
        modeling._chronological_masks(pd.Series(["2020-01-01", None, "2020-02-01"]))
    with pytest.raises(ValueError, match="five distinct"):
        modeling._chronological_masks(pd.Series(pd.date_range("2020-01-01", periods=4)))
