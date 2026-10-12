"""Session-only casework for public benchmark demonstrations.

This object is held in Streamlit session state and never writes teacher notes to disk.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone


class DemoSupportStore:
    def __init__(self) -> None:
        self.screenings: dict[tuple[str, str], dict] = {}
        self.cases: dict[tuple[str, str], dict] = {}
        self.events: dict[tuple[str, str], list[dict]] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_screening(self, institution_id: str, student_id: str) -> dict:
        return deepcopy(self.screenings.get((institution_id, student_id), {
            "checklist": {}, "notes": "", "updated_at": None, "updated_by": None,
        }))

    def save_screening(self, institution_id: str, student_id: str, checklist: dict,
                       notes: str, updated_by: str) -> None:
        self.screenings[(institution_id, student_id)] = {
            "checklist": deepcopy(checklist), "notes": notes,
            "updated_at": self._now(), "updated_by": updated_by,
        }

    def screening_summary(self, institution_id: str) -> dict:
        rows = [value for (owner, _), value in self.screenings.items() if owner == institution_id]
        complete = sum(bool(row["checklist"]) and all(row["checklist"].values()) for row in rows)
        return {"started": len(rows), "complete": complete, "open": len(rows) - complete}

    def get_case(self, institution_id: str, student_id: str) -> dict:
        return deepcopy(self.cases.get((institution_id, student_id), {
            "owner_email": "", "status": "Needs review", "priority": "Normal", "due_date": "",
            "intervention_type": "", "intervention_accepted": "Not recorded",
            "follow_up_outcome": "", "student_feedback": "", "updated_at": None, "updated_by": None,
        }))

    def save_case(self, institution_id: str, student_id: str, case: dict, updated_by: str) -> None:
        key = (institution_id, student_id)
        now = self._now()
        self.cases[key] = {**deepcopy(case), "updated_at": now, "updated_by": updated_by}
        self.events.setdefault(key, []).insert(0, {
            "action": "Case record saved", "actor_email": updated_by, "created_at": now,
        })

    def case_history(self, institution_id: str, student_id: str) -> list[dict]:
        return deepcopy(self.events.get((institution_id, student_id), [])[:20])

    def list_cases(self, institution_id: str) -> list[dict]:
        visible = [{"student_id": student_id, **row} for (owner, student_id), row in self.cases.items()
                   if owner == institution_id]
        return sorted(visible, key=lambda row: row["updated_at"], reverse=True)[:500]

    def case_summary(self, institution_id: str) -> dict:
        rows = [row for (owner, _), row in self.cases.items() if owner == institution_id]
        return {
            "total": len(rows),
            "unassigned": sum(not row.get("owner_email") for row in rows),
            "open": sum(row.get("status") not in {"Closed", "Resolved"} for row in rows),
            "resolved": sum(row.get("status") in {"Closed", "Resolved"} for row in rows),
        }
