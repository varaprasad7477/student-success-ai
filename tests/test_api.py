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

