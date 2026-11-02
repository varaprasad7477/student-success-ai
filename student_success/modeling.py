from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .schema import MODEL_FIELDS


def _minimum_data_gate(y: pd.Series) -> None:
    counts = y.value_counts()
    if len(y) < 100 or len(counts) != 2 or counts.min() < 20:
        raise ValueError(
            "Training blocked: provide at least 100 labeled rows and at least 20 examples of each outcome."
        )


def build_candidates(feature_names: list[str] | None = None) -> dict[str, Pipeline]:
    feature_names = feature_names or MODEL_FIELDS
    median = ColumnTransformer([("numeric", SimpleImputer(strategy="median"), feature_names)])
    scaled = ColumnTransformer([
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), feature_names)
    ])
    return {
        "logistic_regression": Pipeline([
            ("preprocess", scaled),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.7)),
        ]),
        "random_forest": Pipeline([
            ("preprocess", median),
            ("model", CalibratedClassifierCV(
                RandomForestClassifier(n_estimators=350, min_samples_leaf=5, class_weight="balanced", random_state=42),
                method="sigmoid", cv=3,
            )),
        ]),
        "hist_gradient_boosting": Pipeline([
            ("preprocess", median),
            ("model", CalibratedClassifierCV(
                HistGradientBoostingClassifier(max_leaf_nodes=15, learning_rate=0.06, l2_regularization=1.0, random_state=42),
                method="sigmoid", cv=3,
            )),
        ]),
    }


def _best_threshold(y: pd.Series, probabilities: np.ndarray) -> float:
    choices = np.linspace(0.20, 0.80, 121)
    scores = [f1_score(y, probabilities >= value) for value in choices]
    return float(choices[int(np.argmax(scores))])


def _chronological_masks(time_values: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.Series]:
    timestamps = pd.to_datetime(time_values.reset_index(drop=True), errors="coerce", utc=True)
    if timestamps.isna().any():
        raise ValueError("Temporal evaluation requires a valid timestamp for every training row.")
    unique_times = timestamps.drop_duplicates().sort_values().reset_index(drop=True)
    if len(unique_times) < 5:
        raise ValueError("Temporal evaluation requires at least five distinct time values.")

    train_end = unique_times.iloc[max(0, int(np.ceil(len(unique_times) * 0.6)) - 1)]
    validation_end = unique_times.iloc[max(1, int(np.ceil(len(unique_times) * 0.8)) - 1)]
    if validation_end <= train_end or validation_end >= unique_times.iloc[-1]:
        raise ValueError("Could not create distinct chronological train, validation, and test periods.")

    train_mask = (timestamps <= train_end).to_numpy()
    validation_mask = ((timestamps > train_end) & (timestamps <= validation_end)).to_numpy()
    test_mask = (timestamps > validation_end).to_numpy()
    return train_mask, validation_mask, test_mask, timestamps


def train_temporal(
    frame: pd.DataFrame,
    time_values: pd.Series,
    output_dir: str | Path,
    audit_fields: list[str] | None = None,
    feature_names: list[str] | None = None,
) -> dict:
    requested = feature_names or MODEL_FIELDS
    unknown = sorted(set(requested) - set(MODEL_FIELDS))
    if unknown:
        raise ValueError(f"Unknown training feature(s): {', '.join(unknown)}")
    if len(frame) != len(time_values):
        raise ValueError("The time column must have one value for every training row.")

    frame = frame.reset_index(drop=True)
    time_values = time_values.reset_index(drop=True)
    active_fields = [field for field in requested if field in frame and frame[field].notna().any()]
    if len(active_fields) < 3:
        raise ValueError("Training blocked: at least three usable canonical predictors are required.")
    X, y = frame[active_fields], frame["outcome"]
    _minimum_data_gate(y)
    train_mask, validation_mask, test_mask, timestamps = _chronological_masks(time_values)
    partitions = {
        "train": y.iloc[np.flatnonzero(train_mask)],
        "validation": y.iloc[np.flatnonzero(validation_mask)],
        "test": y.iloc[np.flatnonzero(test_mask)],
    }
    for name, labels in partitions.items():
        counts = labels.value_counts()
        if len(labels) < 100 or len(counts) != 2 or counts.min() < 20:
            raise ValueError(
                f"Temporal {name} partition needs at least 100 rows and 20 examples of each outcome."
            )

    train_positions = np.flatnonzero(train_mask)
    validation_positions = np.flatnonzero(validation_mask)
    test_positions = np.flatnonzero(test_mask)
    leaderboard = []
    candidates = build_candidates(active_fields)
    for name, estimator in candidates.items():
        estimator.fit(X.iloc[train_positions], y.iloc[train_positions])
        validation_probabilities = estimator.predict_proba(X.iloc[validation_positions])[:, 1]
        validation_y = y.iloc[validation_positions]
        threshold = _best_threshold(validation_y, validation_probabilities)
        validation_predictions = validation_probabilities >= threshold
        leaderboard.append({
            "model": name,
            "threshold": threshold,
            "validation_pr_auc": average_precision_score(validation_y, validation_probabilities),
            "validation_roc_auc": roc_auc_score(validation_y, validation_probabilities),
            "validation_brier": brier_score_loss(validation_y, validation_probabilities),
            "validation_recall": recall_score(validation_y, validation_predictions),
            "validation_precision": precision_score(validation_y, validation_predictions, zero_division=0),
            "validation_f1": f1_score(validation_y, validation_predictions),
        })
    leaderboard.sort(
        key=lambda item: (item["validation_pr_auc"], -item["validation_brier"]), reverse=True
    )
    winner = leaderboard[0]
    fit_positions = np.concatenate([train_positions, validation_positions])
    model = candidates[winner["model"]].fit(X.iloc[fit_positions], y.iloc[fit_positions])
    test_y = y.iloc[test_positions]
    test_probabilities = model.predict_proba(X.iloc[test_positions])[:, 1]
    test_predictions = test_probabilities >= winner["threshold"]
    final_metrics = {
        "model": winner["model"],
        "threshold": winner["threshold"],
        "pr_auc": average_precision_score(test_y, test_probabilities),
        "roc_auc": roc_auc_score(test_y, test_probabilities),
        "brier": brier_score_loss(test_y, test_probabilities),
        "recall": recall_score(test_y, test_predictions),
        "precision": precision_score(test_y, test_predictions, zero_division=0),
        "f1": f1_score(test_y, test_predictions),
        "rows": len(test_positions),
        "positive_rate": float(test_y.mean()),
    }

    fairness = {}
    test_frame = frame.iloc[test_positions]
    for field in audit_fields or []:
        if field not in test_frame:
            continue
        groups = []
        for value, indexes in test_frame.groupby(field, dropna=False).groups.items():
            positions = test_frame.index.get_indexer(indexes)
            if len(positions) < 20:
                continue
            group_y = test_y.iloc[positions]
            group_predictions = test_predictions[positions]
            groups.append({
                "group": str(value),
                "support": len(positions),
                "positive_rate": float(group_y.mean()),
                "recall": recall_score(group_y, group_predictions, zero_division=0),
                "precision": precision_score(group_y, group_predictions, zero_division=0),
            })
        if groups:
            fairness[field] = groups

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    training_frame = X.iloc[fit_positions]
    bundle = {
        "model": model,
        "model_name": winner["model"],
        "threshold": winner["threshold"],
        "feature_names": active_fields,
        "training_medians": training_frame.median(numeric_only=True).to_dict(),
        "evaluation_design": "chronological_train_validation_test",
    }
    joblib.dump(bundle, output / "model_bundle.joblib")
    report = {
        "evaluation_design": "chronological_train_validation_test",
        "status": "held_out_temporal_test",
        "threshold_selection": (
            "F1 maximized on validation data only; choose using local costs and advisor capacity before a pilot."
        ),
        "split_boundaries_utc": {
            "train_end": timestamps[train_mask].max().isoformat(),
            "validation_end": timestamps[validation_mask].max().isoformat(),
            "test_start": timestamps[test_mask].min().isoformat(),
        },
        "split_rows": {name: len(labels) for name, labels in partitions.items()},
        "winner": final_metrics,
        "validation_leaderboard": leaderboard,
        "rows": len(frame),
        "subgroup_audit": fairness,
    }
    (output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def train(frame: pd.DataFrame, output_dir: str | Path, audit_fields: list[str] | None = None,
          feature_names: list[str] | None = None) -> dict:
    requested = feature_names or MODEL_FIELDS
    unknown = sorted(set(requested) - set(MODEL_FIELDS))
    if unknown:
        raise ValueError(f"Unknown training feature(s): {', '.join(unknown)}")
    active_fields = [field for field in requested if field in frame and frame[field].notna().any()]
    if len(active_fields) < 3:
        raise ValueError("Training blocked: at least three usable canonical predictors are required.")
    X, y = frame[active_fields], frame["outcome"]
    _minimum_data_gate(y)
    folds = min(5, int(y.value_counts().min()))
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    leaderboard = []
    candidates = build_candidates(active_fields)
    prediction_cache = {}
    for name, estimator in candidates.items():
        probabilities = cross_val_predict(estimator, X, y, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]
        prediction_cache[name] = probabilities
        threshold = _best_threshold(y, probabilities)
        predicted = probabilities >= threshold
        leaderboard.append({
            "model": name,
            "threshold": threshold,
            "pr_auc": average_precision_score(y, probabilities),
            "roc_auc": roc_auc_score(y, probabilities),
            "brier": brier_score_loss(y, probabilities),
            "recall": recall_score(y, predicted),
            "precision": precision_score(y, predicted, zero_division=0),
            "f1": f1_score(y, predicted),
        })
    leaderboard.sort(key=lambda item: (item["pr_auc"], -item["brier"]), reverse=True)
    winner = leaderboard[0]
    model = candidates[winner["model"]].fit(X, y)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": model,
        "model_name": winner["model"],
        "threshold": winner["threshold"],
        "feature_names": active_fields,
        "training_medians": X.median(numeric_only=True).to_dict(),
        "evaluation_design": "stratified_oof_development_only",
    }
    joblib.dump(bundle, output / "model_bundle.joblib")
    fairness = {}
    winner_probabilities = prediction_cache[winner["model"]]
    winner_predictions = winner_probabilities >= winner["threshold"]
    for field in audit_fields or []:
        if field not in frame:
            continue
        groups = []
        for value, indexes in frame.groupby(field, dropna=False).groups.items():
            positions = frame.index.get_indexer(indexes)
            valid_positions = positions[positions >= 0]
            if len(valid_positions) < 20:
                continue
            group_y = y.iloc[valid_positions]
            group_pred = winner_predictions[valid_positions]
            groups.append({
                "group": str(value), "support": int(len(valid_positions)),
                "positive_rate": float(group_y.mean()),
                "recall": float(recall_score(group_y, group_pred, zero_division=0)),
                "precision": float(precision_score(group_y, group_pred, zero_division=0)),
            })
        if groups:
            fairness[field] = groups
    report = {
        "evaluation_design": "stratified_oof_development_only",
        "status": "development_estimates_not_independent_test",
        "winner": winner,
        "leaderboard": leaderboard,
        "rows": len(frame),
        "positive_rate": float(y.mean()),
        "subgroup_audit": fairness,
    }
    (output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
