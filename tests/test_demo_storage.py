from student_success.demo_storage import DemoSupportStore


def test_demo_casework_is_session_local_and_separate_by_institution():
    first = DemoSupportStore()
    second = DemoSupportStore()
    first.save_screening("school-a", "S1", {"contacted": True}, "Private demo note", "teacher@demo")
    first.save_case("school-a", "S1", {"status": "Support active", "owner_email": "teacher@demo"}, "teacher@demo")
    assert first.get_screening("school-a", "S1")["notes"] == "Private demo note"
    assert second.get_screening("school-a", "S1")["notes"] == ""
    assert first.case_summary("school-a")["total"] == 1
    assert first.case_summary("school-b")["total"] == 0
    assert first.case_history("school-a", "S1")[0]["actor_email"] == "teacher@demo"

