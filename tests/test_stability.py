"""End-to-end regressions using temporary institutions and databases only."""

import copy
import importlib

import pytest
from fastapi.testclient import TestClient


PASSWORD = "Stability-test-2026!"
ADMIN_EMAIL = "admin@stability.example"
CSV = (
    "student_id,attendance_rate,assessment_average,credits_completed_ratio\n"
    "H1,0.10,10,0.10\n"
    "M1,0.65,45,0.45\n"
    "L1,0.95,90,0.95\n"
    "I1,,40,0.40\n"
).encode()


def signup(client, email=ADMIN_EMAIL, name="Stability College"):
    response = client.post("/v1/auth/signup", json={
        "institution_name": name,
        "institution_type": "College",
        "display_name": "Test Administrator",
        "email": email,
        "password": PASSWORD,
        "prediction_horizon": "Week 8 — review the remainder of this semester",
        "term_label": "Semester 1",
        "data_owner": "Academic records team",
        "selected_fields": ["attendance_rate", "assessment_average", "credits_completed_ratio"],
        "responsible_use_confirmed": True,
    })
    assert response.status_code == 200, response.text
    return response


def upload(client, content=CSV, **data):
    return client.post("/v1/data/upload", files={"file": ("students.csv", content, "text/csv")}, data=data)


def login(client, email=ADMIN_EMAIL):
    response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def student_groups(client):
    response = client.get("/v1/dropout-predictions")
    assert response.status_code == 200, response.text
    return {row["student_id"]: row["risk_band"] for row in response.json()["records"]}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "stability.db"))
    monkeypatch.setenv("SESSION_SECRET", "isolated-stability-session-secret-do-not-use-in-production")
    monkeypatch.setenv("STUDENT_SUCCESS_API_KEY", "isolated-stability-api-key")
    import api
    api = importlib.reload(api)
    client = TestClient(api.app, raise_server_exceptions=False)
    signup(client)
    yield api, client
    client.close()


def staff_client(api, administrator, role):
    email = f"{role}@stability.example"
    response = administrator.post("/v1/users", json={
        "display_name": f"Test {role}", "email": email, "password": PASSWORD, "role": role,
    })
    assert response.status_code == 200, response.text
    client = TestClient(api.app, raise_server_exceptions=False)
    login(client, email)
    return client


def test_signup_creates_authenticated_administrator_session(workspace):
    _, client = workspace
    response = client.get("/v1/me")
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"
    assert response.json()["user"]["email"] == ADMIN_EMAIL
    assert client.get("/v1/dashboard").json()["ready"] is False


def test_uploaded_institution_data_survives_logout_and_api_reload(workspace):
    api, client = workspace
    assert upload(client).status_code == 200
    expected = student_groups(client)
    assert client.post("/v1/auth/logout").status_code == 200
    assert client.get("/v1/dashboard").status_code == 401
    login(client)
    assert student_groups(client) == expected
    api = importlib.reload(api)
    with TestClient(api.app, raise_server_exceptions=False) as restarted:
        login(restarted)
        assert student_groups(restarted) == expected
        assert restarted.get("/v1/students/M1").json()["student_id"] == "M1"


def test_staff_share_institution_data_and_viewer_cannot_mutate(workspace):
    api, administrator = workspace
    assert upload(administrator).status_code == 200
    expected = student_groups(administrator)
    checklist = {key: True for key in api.CHECKLIST}
    for role in ("teacher", "viewer"):
        with staff_client(api, administrator, role) as staff:
            assert student_groups(staff) == expected
            assert upload(staff).status_code == 403
            cfg = staff.get("/v1/setup").json()["config"]
            assert staff.put("/v1/setup", json={"config": cfg}).status_code == 403
            assert staff.post("/v1/users", json={
                "display_name": "Forbidden User", "email": "forbidden@example.test",
                "password": PASSWORD, "role": "teacher",
            }).status_code == 403
            expected_status = 200 if role == "teacher" else 403
            assert staff.put("/v1/students/H1/screening", json={"checklist": checklist}).status_code == expected_status
            assert staff.put("/v1/cases/H1", json={"status": "Closed"}).status_code == expected_status


def test_institutions_cannot_access_each_others_uploads_or_cases(workspace):
    api, first = workspace
    assert upload(first).status_code == 200
    assert first.put("/v1/cases/H1", json={"status": "Closed", "follow_up_outcome": "Private note"}).status_code == 200
    first_groups = student_groups(first)
    with TestClient(api.app, raise_server_exceptions=False) as second:
        signup(second, "other@stability.example", "Other College")
        assert second.get("/v1/dashboard").json()["ready"] is False
        assert second.get("/v1/students/H1").status_code == 404
        assert second.get("/v1/cases").json()["items"] == []
        own_csv = b"student_id,attendance_rate,assessment_average,credits_completed_ratio\nB1,0.9,80,0.9\n"
        assert upload(second, own_csv).status_code == 200
        assert set(student_groups(second)) == {"B1"}
        assert second.put("/v1/cases/H1", json={"status": "Closed"}).status_code == 404
    assert student_groups(first) == first_groups


def test_target_changes_recalculate_current_data_and_survive_reupload_and_restart(workspace):
    api, client = workspace
    assert upload(client).status_code == 200
    assert student_groups(client)["M1"] == "Medium"
    cfg = client.get("/v1/setup").json()["config"]
    cfg["review_targets"].update(attendance_rate=.60, assessment_average=40, credits_completed_ratio=.40)
    response = client.put("/v1/setup", json={"config": cfg})
    assert response.status_code == 200, response.text
    assert response.json()["recalculated"] is True
    assert student_groups(client)["M1"] == "Low"
    detail = client.get("/v1/students/M1").json()
    assert not any(check["needs_review"] for check in detail["signal_checks"])
    assert not detail["evidence"], "Explanations must not retain the old targets after recalculation"
    assert upload(client).status_code == 200
    assert student_groups(client)["M1"] == "Low"
    api = importlib.reload(api)
    with TestClient(api.app, raise_server_exceptions=False) as restarted:
        login(restarted)
        assert restarted.get("/v1/setup").json()["config"]["review_targets"]["attendance_rate"] == .60
        assert student_groups(restarted)["M1"] == "Low"


@pytest.mark.parametrize("invalid", ["oops", None, -0.01, 1.01, "NaN", "Infinity"])
def test_invalid_review_targets_are_rejected_without_changing_saved_results(workspace, invalid):
    _, client = workspace
    assert upload(client).status_code == 200
    before_config = client.get("/v1/setup").json()["config"]
    before_groups = student_groups(client)
    bad_config = copy.deepcopy(before_config)
    bad_config["review_targets"]["attendance_rate"] = invalid
    response = client.put("/v1/setup", json={"config": bad_config})
    assert response.status_code == 422, response.text
    assert client.get("/v1/setup").json()["config"] == before_config
    assert student_groups(client) == before_groups


def test_invalid_schema_update_does_not_persist_a_broken_configuration(workspace):
    _, client = workspace
    assert upload(client).status_code == 200
    original = client.get("/v1/setup").json()["config"]
    bad = copy.deepcopy(original)
    bad["model_fields"] = ["unknown_learning_feature"]
    response = client.put("/v1/setup", json={"config": bad})
    assert response.status_code == 422, response.text
    assert client.get("/v1/setup").json()["config"] == original
    assert client.get("/v1/dashboard").status_code == 200


def test_explicit_percentages_and_leading_zero_identifiers_round_trip(workspace):
    api, client = workspace
    content = b"student_id;Attendance %;Average Mark;Credits Completed %\n001;65%;45;45%\n002;95%;90;95%\n"
    response = upload(client, content)
    assert response.status_code == 200, response.text
    assert set(student_groups(client)) == {"001", "002"}
    detail = client.get("/v1/students/001").json()
    checks = {check["field"]: check for check in detail["signal_checks"]}
    assert checks["attendance_rate"]["value"] == pytest.approx(.65)
    assert checks["credits_completed_ratio"]["value"] == pytest.approx(.45)
    api = importlib.reload(api)
    with TestClient(api.app, raise_server_exceptions=False) as restarted:
        login(restarted)
        assert set(student_groups(restarted)) == {"001", "002"}
        assert restarted.get("/v1/students/001").status_code == 200


def test_previous_csv_units_do_not_change_next_csv_results(workspace):
    _, client = workspace
    first = b"student_id,Attendance %,Average Mark,Credits Completed %\nS1,65,45,45\n"
    second = b"student_id,attendance_rate,assessment_average,credits_completed_ratio\nS1,.65,45,.45\n"
    assert upload(client, first).status_code == 200
    initial = client.get("/v1/students/S1").json()
    assert upload(client, second).status_code == 200
    subsequent = client.get("/v1/students/S1").json()
    assert subsequent["risk_band"] == initial["risk_band"]
    assert subsequent["screening_index"] == pytest.approx(initial["screening_index"])
    assert subsequent["risk_probability"] is None
    assert subsequent["signal_checks"] == initial["signal_checks"]


@pytest.mark.parametrize("content", [
    b"student_id,attendance_rate,assessment_average,credits_completed_ratio\n",
    b"",
    b"student_id,attendance_rate,assessment_average,credits_completed_ratio\nS1,.8,70,.7\nS1,.5,40,.4\n",
    b"student_id,attendance_rate,assessment_average,credits_completed_ratio\n\"unclosed,.8,70,.7\n",
    b"student_id,learner_id,attendance_rate,assessment_average,credits_completed_ratio\nS1,S2,.8,70,.7\n",
])
def test_bad_csv_does_not_replace_the_last_valid_dataset(workspace, content):
    _, client = workspace
    assert upload(client).status_code == 200
    before = student_groups(client)
    response = upload(client, content)
    assert response.status_code == 422, response.text
    assert student_groups(client) == before


def test_screening_denominator_and_completion_use_same_eligible_students(workspace):
    api, client = workspace
    assert upload(client).status_code == 200
    all_checked = {key: True for key in api.CHECKLIST}
    assert client.put("/v1/students/H1/screening", json={"checklist": {"invented": True}}).status_code == 422
    partial = {key: False for key in api.CHECKLIST}
    partial[next(iter(partial))] = True
    assert client.put("/v1/students/H1/screening", json={"checklist": partial}).status_code == 200
    # Low-risk follow-up is valid but must not inflate high/medium progress.
    assert client.put("/v1/students/L1/screening", json={"checklist": all_checked}).status_code == 200
    progress = client.get("/v1/dashboard").json()["screening"]
    assert progress["eligible"] == 2
    assert progress["started"] == 1
    assert progress["complete"] == 0
    assert progress["open"] == 1
    assert progress["not_started"] == 1
    assert client.put("/v1/students/H1/screening", json={"checklist": all_checked}).status_code == 200
    progress = client.get("/v1/dashboard").json()["screening"]
    assert progress["complete"] == 1
    assert progress["eligible"] == 2


def test_missing_students_are_not_readable_or_writable(workspace):
    api, client = workspace
    assert upload(client).status_code == 200
    assert client.get("/v1/students/does-not-exist").status_code == 404
    assert client.put("/v1/students/does-not-exist/screening", json={
        "checklist": {key: True for key in api.CHECKLIST},
    }).status_code == 404
    assert client.put("/v1/cases/does-not-exist", json={"status": "Closed"}).status_code == 404


@pytest.mark.parametrize("filename,expected", [
    ("simple_college_demo_60.csv", 60),
    ("uci_697_real_500_natural_upload.csv", 500),
    ("uci_697_real_500_balanced_comparison.csv", 500),
    ("oulad_clean_labeled_300.csv", 300),
])
def test_included_public_and_simulated_csvs(workspace, filename, expected):
    api, client = workspace
    content = (api.ROOT / "DEMO_DATASETS" / filename).read_bytes()
    inspected = client.post("/v1/data/inspect", files={"file": (filename, content, "text/csv")})
    assert inspected.status_code == 200, inspected.text
    response = upload(client, content)
    assert response.status_code == 200, response.text
    assert response.json()["rows"] == expected
    assert response.json()["has_model"] is False
    result = client.get("/v1/dropout-predictions").json()
    assert len(result["records"]) == expected
    assert sum(result["counts"].values()) == expected
    assert all(row["risk_probability"] is None for row in response.json()["predictions"])
    assert client.get("/v1/students/" + result["records"][0]["student_id"]).status_code == 200


def test_five_thousand_students_and_oversize_rejection(workspace):
    _, client = workspace
    header = "student_id,attendance_rate,assessment_average,credits_completed_ratio\n"
    rows = "".join(f"S{i},.8,70,.8\n" for i in range(5000))
    response = upload(client, (header + rows).encode())
    assert response.status_code == 200, response.text
    assert len(student_groups(client)) == 5000
    rejected = upload(client, (header + rows + "S5000,.8,70,.8\n").encode())
    assert rejected.status_code == 422
    assert len(student_groups(client)) == 5000


def test_nonfinite_activity_and_malformed_settings_do_not_crash(workspace):
    _, client = workspace
    assert upload(client).status_code == 200
    content = b"student_id,attendance_rate,assessment_average,days_since_login\nX,.5,40,inf\n"
    assert upload(client, content).status_code == 422
    config = client.get("/v1/setup").json()["config"]
    config["column_map"] = []
    assert client.put("/v1/setup", json={"config": config}).status_code == 422


def test_failed_demo_model_does_not_leave_dashboard_loading_forever(workspace, monkeypatch):
    api, _ = workspace
    def unavailable(benchmark):
        raise RuntimeError("Test model unavailable")
    monkeypatch.setattr(api, "cached_demo_frames", unavailable)
    api.prepare_demo_cache("northstar")
    assert "northstar" in api.app.state.demo_cache_errors
    with TestClient(api.app, raise_server_exceptions=False) as demo:
        assert demo.post("/v1/auth/demo").status_code == 200
        response = demo.get("/v1/dashboard")
        assert response.status_code == 503
        assert "could not be loaded" in response.json()["detail"]
