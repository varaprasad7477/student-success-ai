from pathlib import Path

import joblib
import pandas as pd
import pytest

from student_success.prediction import PredictionService
from student_success.schema import canonicalize, load_config


ROOT = Path(__file__).resolve().parents[1]


def test_oulad_source_has_day28_contract():
    config = load_config(ROOT / "config/institutions/open_university_day28.json")
    source = pd.read_csv(ROOT / "data/oulad_day28_prepared.csv")
    assert len(source) == 27422
    assert source.learner_id.is_unique
    assert (source.assessments_submitted_28 <= source.assessments_due_28).all()
    assert source.active_day_ratio_28.between(0, 1).all()
    assert source.days_since_activity_28.between(0, 29).all()
    validated = canonicalize(source.head(100), config, training=True)
    assert validated.frame.outcome.isin([0, 1]).all()


def test_model_cannot_cross_institution_boundary(tmp_path):
    config = load_config(ROOT / "config/institutions/open_university_day28.json")
    path = tmp_path / "model.joblib"
    joblib.dump({"institution_id": "other-institution"}, path)
    with pytest.raises(ValueError, match="institution does not match"):
        PredictionService(config, path)
