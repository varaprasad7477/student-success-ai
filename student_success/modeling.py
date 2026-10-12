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
    report = {"winner": winner, "leaderboard": leaderboard, "rows": len(frame), "positive_rate": float(y.mean()), "subgroup_audit": fairness}
    (output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report

