import importlib
import os

from fastapi.testclient import TestClient


def test_health_and_authorized_prediction(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setenv("STUDENT_SUCCESS_API_KEY", "test-key")
    import api
    importlib.reload(api)
    client = TestClient(api.app)
    assert client.get("/health").status_code == 200
    payload = {"students": [{
        "learner_id": "S1", "modules_enrolled": 6,
        "modules_evaluated": 4, "first_semester_average": 52,
        "semester_score_change": -4, "credits_completed_percent": 50,
        "academic_engagement": .58,
    }]}
    assert client.post("/v1/predict", json=payload).status_code == 401
    response = client.post("/v1/predict", json=payload, headers={"x-api-key": "test-key"})
    assert response.status_code == 200
    assert response.json()["predictions"][0]["student_id"] == "S1"


def test_upload_requires_confirmed_mapping_and_applies_it(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "upload.db"))
    import api
    importlib.reload(api)
    client = TestClient(api.app)
    assert client.post("/v1/auth/demo").status_code == 200

    csv = b"Learner ID,score\nS-1,72\n"
    inspected = client.post(
        "/v1/data/inspect",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert inspected.status_code == 200
    columns = {item["column"]: item for item in inspected.json()["columns"]}
    assert columns["Learner ID"]["suggested_field"] == "student_id"
    assert columns["score"]["confidence"] == "review"

    missing_id_map = client.post(
        "/v1/data/upload",
        files={"file": ("students.csv", csv, "text/csv")},
        data={"column_map": '{"score":"assessment_average"}'},
    )
    assert missing_id_map.status_code == 422
    assert "Student identifier" in missing_id_map.json()["detail"]

    too_little_data = client.post(
        "/v1/data/upload",
        files={"file": ("students.csv", csv, "text/csv")},
        data={"column_map": '{"Learner ID":"student_id","score":"assessment_average"}'},
    )
    assert too_little_data.status_code == 422
    assert "enough recognised learning information" in too_little_data.json()["detail"]

    usable_csv = b"Learner ID,Attendance %,Average Mark,Credits Completed %\nS-1,74,72,65\n"
    uploaded = client.post(
        "/v1/data/upload",
        files={"file": ("students.csv", usable_csv, "text/csv")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["rows"] == 1
    assert uploaded.json()["mapping_saved"] is False


def test_signup_captures_institution_review_context(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "signup.db"))
    import api
    importlib.reload(api)
    client = TestClient(api.app)
    payload = {
        "institution_name": "Harbor College", "institution_type": "College", "display_name": "Admin User",
        "email": "admin@harbor.example", "password": "a-strong-password", "term_label": "Semester 1",
        "data_owner": "Student records", "prediction_horizon": "Week 6 — support for the remainder of the semester",
        "selected_fields": ["attendance_rate", "assignments_due", "assignments_submitted", "assessment_average"],
        "responsible_use_confirmed": True,
    }
    assert client.post("/v1/auth/signup", json=payload).status_code == 200
    assert client.post("/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}).status_code == 200
    workspace = client.get("/v1/setup").json()["config"]
    assert workspace["onboarding"]["term_label"] == "Semester 1"
    assert "submission_rate" in workspace["model_fields"]
