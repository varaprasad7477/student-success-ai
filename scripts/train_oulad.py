"""Fit on earlier presentations and report untouched 2014J performance."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from student_success.modeling import build_candidates, _best_threshold
from student_success.schema import canonicalize, load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = pd.read_csv(args.data)
    config = load_config(Path(__file__).resolve().parents[1] / "config/institutions/open_university_day28.json")
    frame = canonicalize(raw, config, training=True).frame
    train_mask = raw.code_presentation.ne("2014J")
    # Student IDs can recur in later presentations. Keep the final holdout wholly unseen.
    held_ids = set(raw.loc[~train_mask, "id_student"])
    train_mask &= ~raw.id_student.isin(held_ids)
    X_train, y_train = frame.loc[train_mask, config["model_fields"]], frame.loc[train_mask, "outcome"]
    test_mask = raw.code_presentation.eq("2014J")
    X_test, y_test = frame.loc[test_mask, config["model_fields"]], frame.loc[test_mask, "outcome"]
    # Fixed 2014B validation chooses model and operating threshold; 2014J remains untouched.
    fit_mask = train_mask & raw.code_presentation.ne("2014B")
    valid_mask = train_mask & raw.code_presentation.eq("2014B")
    leaderboard = []
    for name, candidate in build_candidates(config["model_fields"]).items():
        candidate.fit(frame.loc[fit_mask, config["model_fields"]], frame.loc[fit_mask, "outcome"])
        valid_probs = candidate.predict_proba(frame.loc[valid_mask, config["model_fields"]])[:, 1]
        valid_y = frame.loc[valid_mask, "outcome"]
        threshold = _best_threshold(valid_y, valid_probs)
        leaderboard.append({"model": name, "threshold": threshold,
                            "validation_pr_auc": float(average_precision_score(valid_y, valid_probs)),
                            "validation_brier": float(brier_score_loss(valid_y, valid_probs))})
    leaderboard.sort(key=lambda x: (x["validation_pr_auc"], -x["validation_brier"]), reverse=True)
    winner = leaderboard[0]
    model = build_candidates(config["model_fields"])[winner["model"]].fit(X_train, y_train)
    probabilities = model.predict_proba(X_test)[:, 1]
    predicted = probabilities >= winner["threshold"]
    metrics = {"model": winner["model"], "threshold": winner["threshold"],
               "pr_auc": float(average_precision_score(y_test, probabilities)),
               "roc_auc": float(roc_auc_score(y_test, probabilities)),
               "brier": float(brier_score_loss(y_test, probabilities)),
               "recall": float(recall_score(y_test, predicted)),
               "precision": float(precision_score(y_test, predicted, zero_division=0)),
               "rows": int(len(y_test)), "positive_rate": float(y_test.mean())}
    bins = pd.DataFrame({"y": y_test.to_numpy(), "p": probabilities}).assign(
        decile=lambda d: pd.qcut(d.p.rank(method="first"), 10, labels=False))
    calibration = bins.groupby("decile").agg(n=("y", "size"), observed=("y", "mean"), predicted=("p", "mean")).reset_index().to_dict("records")
    subgroup = {}
    for field in config["audit_fields"]:
        audit = raw.loc[test_mask, field].reset_index(drop=True)
        subgroup[field] = [{"group": str(group), "support": int(len(index)),
                            "positive_rate": float(y_test.iloc[index].mean()),
                            "recall": float(recall_score(y_test.iloc[index], predicted[index], zero_division=0))}
                           for group, index in audit.groupby(audit).groups.items() if len(index) >= 100]
    report = {"winner": metrics, "leaderboard": leaderboard, "rows": int(len(X_train)),
              "holdout_presentation": "2014J", "validation_presentation": "2014B",
              "same_student_overlap_removed": True, "calibration_deciles": calibration, "subgroup_audit": subgroup,
              "limitations": "Public Open University benchmark only; not local institution validation or causal explanation."}
    args.output.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "model_name": winner["model"], "threshold": winner["threshold"],
                 "institution_id": config["institution_id"],
                 "feature_names": config["model_fields"], "training_medians": X_train.median().to_dict()},
                args.output / "model_bundle.joblib")
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
