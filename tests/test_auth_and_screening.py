from student_success.storage import AuditStore


def test_account_authentication_and_screening_persistence(tmp_path):
    store = AuditStore(tmp_path / "app.db")
    config = {"institution_id": "north-college", "column_map": {}, "rules": []}
    store.create_institution_with_admin(
        "north-college", "North College", "College", config,
        "A Teacher", "teacher@example.edu", "secure-pass-123",
    )
    assert store.authenticate("teacher@example.edu", "wrong-password") is None
    user = store.authenticate("Teacher@Example.edu", "secure-pass-123")
    assert user["institution_id"] == "north-college"
    assert user["role"] == "admin"

    checklist = {"student_contacted": True, "follow_up_scheduled": False}
    store.save_screening("north-college", "S-1", checklist, "Follow up Friday", user["email"])
    saved = store.get_screening("north-college", "S-1")
    assert saved["checklist"] == checklist
    assert saved["notes"] == "Follow up Friday"
    assert store.screening_summary("north-college") == {"started": 1, "complete": 0, "open": 1}

    case = {
        "owner_email": "teacher@example.edu", "status": "Support active", "priority": "Elevated",
        "due_date": "2026-10-10", "intervention_type": "Tutoring", "intervention_accepted": "Accepted",
        "follow_up_outcome": "Meeting booked", "student_feedback": "Requested mathematics support",
    }
    store.save_case("north-college", "S-1", case, user["email"])
    saved_case = store.get_case("north-college", "S-1")
    assert saved_case["owner_email"] == "teacher@example.edu"
    assert saved_case["intervention_accepted"] == "Accepted"
    assert store.case_summary("north-college") == {"total": 1, "unassigned": 0, "open": 1, "resolved": 0}
    assert store.case_history("north-college", "S-1")[0]["actor_email"] == "teacher@example.edu"
    assert store.list_cases("north-college")[0]["student_id"] == "S-1"
    revised = {**config, "rules": [{"id": "new-rule"}]}
    store.update_institution_config("north-college", revised, user["email"])
    assert store.authenticate("teacher@example.edu", "secure-pass-123")["config"]["rules"][0]["id"] == "new-rule"

