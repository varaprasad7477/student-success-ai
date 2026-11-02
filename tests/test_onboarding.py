from student_success.onboarding import build_institution_config, readiness_check


def test_new_institution_config_uses_confirmed_signals_only():
    config = build_institution_config(
        "harbor-001", "Harbor University", "University", "Week 6 — support for the rest of term",
        "Semester 1", "Student records team", ["assignments_due", "assignments_submitted", "assessment_average"],
    )
    assert config["column_map"]["student_id"] == "student_id"
    assert "submission_rate" in config["model_fields"]
    assert config["onboarding"]["data_owner"] == "Student records team"


def test_readiness_keeps_local_model_blocked():
    config = build_institution_config(
        "harbor-001", "Harbor University", "University", "Week 6 — support for the rest of term",
        "Semester 1", "Student records team", ["assignments_due", "assignments_submitted"],
    )
    statuses = readiness_check(config, has_uploaded_data=True, has_validated_model=False)
    model = next(item for item in statuses if item["name"] == "Institution model validated")
    assert not model["passed"]
    assert "local rules" in model["fallback"]
