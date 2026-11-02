from __future__ import annotations

import json
import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class AuditStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self):
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS institution_datasets (
                institution_id TEXT PRIMARY KEY, source_json TEXT NOT NULL,
                results_json TEXT NOT NULL, config_json TEXT NOT NULL,
                updated_at TEXT NOT NULL)""")
            db.execute("""
                CREATE TABLE IF NOT EXISTS prediction_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    institution_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    risk_probability REAL,
                    risk_band TEXT NOT NULL,
                    model_status TEXT NOT NULL,
                    data_completeness REAL NOT NULL,
                    reason_codes TEXT NOT NULL,
                    policy_flags TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS institutions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    institution_type TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    institution_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (institution_id) REFERENCES institutions(id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS screening_progress (
                    institution_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    checklist_json TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (institution_id, student_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS support_cases (
                    institution_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    owner_email TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Needs review',
                    priority TEXT NOT NULL DEFAULT 'Normal',
                    due_date TEXT NOT NULL DEFAULT '',
                    intervention_type TEXT NOT NULL DEFAULT '',
                    intervention_accepted TEXT NOT NULL DEFAULT 'Not recorded',
                    follow_up_outcome TEXT NOT NULL DEFAULT '',
                    student_feedback TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (institution_id, student_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS case_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    institution_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_email TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _hash_password(password: str, salt_hex: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 310_000).hex()

    def get_dataset(self, institution_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM institution_datasets WHERE institution_id=?", (institution_id,)).fetchone()
        return dict(row) if row else None

    def save_dataset(self, institution_id: str, source_json: str, results_json: str,
                     config: dict, update_institution: bool = False) -> None:
        with self.connection() as db:
            db.execute("""INSERT INTO institution_datasets VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(institution_id) DO UPDATE SET source_json=excluded.source_json,
                results_json=excluded.results_json, config_json=excluded.config_json, updated_at=excluded.updated_at""",
                (institution_id, source_json, results_json, json.dumps(config), datetime.now(timezone.utc).isoformat()))
            if update_institution:
                db.execute("UPDATE institutions SET config_json=? WHERE id=?", (json.dumps(config), institution_id))

    def create_institution_with_admin(
        self, institution_id: str, name: str, institution_type: str, config: dict,
        display_name: str, email: str, password: str,
    ) -> dict:
        if len(password) < 10:
            raise ValueError("Password must contain at least 10 characters.")
        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as db:
            db.execute(
                "INSERT INTO institutions (id, name, institution_type, config_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (institution_id, name, institution_type, json.dumps(config), now),
            )
            db.execute(
                """INSERT INTO users
                (institution_id, display_name, email, role, password_salt, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (institution_id, display_name, email.strip().lower(), "admin", salt, password_hash, now),
            )
        return {"institution_id": institution_id, "display_name": display_name, "email": email.strip().lower(), "role": "admin"}

    def create_staff_user(self, institution_id: str, display_name: str, email: str, password: str, role: str = "teacher") -> dict:
        if role not in {"teacher", "viewer"}:
            raise ValueError("Only teacher or viewer accounts can be created here.")
        if len(password) < 10:
            raise ValueError("Password must contain at least 10 characters.")
        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)
        try:
            with self.connection() as db:
                db.execute(
                    """INSERT INTO users (institution_id, display_name, email, role, password_salt, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (institution_id, display_name.strip(), email.strip().lower(), role, salt, password_hash, datetime.now(timezone.utc).isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("An account already exists for this email address.") from exc
        return {"display_name": display_name.strip(), "email": email.strip().lower(), "role": role}

    def authenticate(self, email: str, password: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(
                """SELECT users.*, institutions.name AS institution_name,
                institutions.institution_type, institutions.config_json
                FROM users JOIN institutions ON institutions.id = users.institution_id
                WHERE users.email = ?""", (email.strip().lower(),),
            ).fetchone()
        if not row:
            return None
        candidate = self._hash_password(password, row["password_salt"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        return {
            "institution_id": row["institution_id"], "institution_name": row["institution_name"],
            "institution_type": row["institution_type"], "display_name": row["display_name"],
            "email": row["email"], "role": row["role"], "config": json.loads(row["config_json"]),
        }

    def get_user(self, email: str) -> dict | None:
        """Rehydrate a signed-in account from storage; never trust session role data."""
        with self.connection() as db:
            row = db.execute(
                """SELECT users.*, institutions.name AS institution_name, institutions.institution_type,
                institutions.config_json FROM users JOIN institutions ON institutions.id=users.institution_id
                WHERE users.email=?""", (email.strip().lower(),)
            ).fetchone()
        if not row:
            return None
        return {
            "institution_id": row["institution_id"], "institution_name": row["institution_name"],
            "institution_type": row["institution_type"], "display_name": row["display_name"],
            "email": row["email"], "role": row["role"], "config": json.loads(row["config_json"]),
        }

    def get_institution_config(self, institution_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT name, institution_type, config_json FROM institutions WHERE id = ?",
                (institution_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "institution_name": row["name"],
            "institution_type": row["institution_type"],
            "config": json.loads(row["config_json"]),
        }

    def update_institution_config(self, institution_id: str, config: dict, editor_email: str) -> None:
        with self.connection() as db:
            editor = db.execute(
                "SELECT role FROM users WHERE institution_id=? AND email=?",
                (institution_id, editor_email.strip().lower()),
            ).fetchone()
            if not editor or editor["role"] != "admin":
                raise ValueError("Only this institution's administrator can change its rules.")
            db.execute("UPDATE institutions SET config_json=? WHERE id=?", (json.dumps(config), institution_id))

    def get_screening(self, institution_id: str, student_id: str) -> dict:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM screening_progress WHERE institution_id = ? AND student_id = ?",
                (institution_id, student_id),
            ).fetchone()
        if not row:
            return {"checklist": {}, "notes": "", "updated_at": None, "updated_by": None}
        return {
            "checklist": json.loads(row["checklist_json"]), "notes": row["notes"],
            "updated_at": row["updated_at"], "updated_by": row["updated_by"],
        }

    def save_screening(
        self, institution_id: str, student_id: str, checklist: dict,
        notes: str, updated_by: str,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """INSERT INTO screening_progress
                (institution_id, student_id, checklist_json, notes, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(institution_id, student_id) DO UPDATE SET
                checklist_json=excluded.checklist_json, notes=excluded.notes,
                updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                (institution_id, student_id, json.dumps(checklist), notes, updated_by, datetime.now(timezone.utc).isoformat()),
            )

    def screening_summary(self, institution_id: str, student_ids: list[str] | None = None) -> dict:
        if student_ids is not None and not student_ids:
            return {"started": 0, "complete": 0, "open": 0}
        query = "SELECT checklist_json FROM screening_progress WHERE institution_id = ?"
        params: list[str] = [institution_id]
        if student_ids is not None:
            query += " AND student_id IN (" + ", ".join("?" for _ in student_ids) + ")"
            params.extend(student_ids)
        with self.connection() as db:
            rows = db.execute(query, params).fetchall()
        complete = 0
        for row in rows:
            values = list(json.loads(row["checklist_json"]).values())
            if values and all(values):
                complete += 1
        return {"started": len(rows), "complete": complete, "open": len(rows) - complete}

    def get_case(self, institution_id: str, student_id: str) -> dict:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM support_cases WHERE institution_id=? AND student_id=?",
                (institution_id, student_id),
            ).fetchone()
        return dict(row) if row else {
            "owner_email": "", "status": "Needs review", "priority": "Normal", "due_date": "",
            "intervention_type": "", "intervention_accepted": "Not recorded",
            "follow_up_outcome": "", "student_feedback": "", "updated_at": None, "updated_by": None,
        }

    def save_case(self, institution_id: str, student_id: str, case: dict, updated_by: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        fields = ("owner_email", "status", "priority", "due_date", "intervention_type",
                  "intervention_accepted", "follow_up_outcome", "student_feedback")
        values = [str(case.get(field, "")) for field in fields]
        with self.connection() as db:
            db.execute(
                """INSERT INTO support_cases
                (institution_id, student_id, owner_email, status, priority, due_date,
                 intervention_type, intervention_accepted, follow_up_outcome, student_feedback,
                 updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(institution_id, student_id) DO UPDATE SET
                owner_email=excluded.owner_email, status=excluded.status, priority=excluded.priority,
                due_date=excluded.due_date, intervention_type=excluded.intervention_type,
                intervention_accepted=excluded.intervention_accepted,
                follow_up_outcome=excluded.follow_up_outcome, student_feedback=excluded.student_feedback,
                updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                (institution_id, student_id, *values, updated_by, now),
            )
            db.execute(
                "INSERT INTO case_events (institution_id, student_id, action, actor_email, created_at) VALUES (?, ?, ?, ?, ?)",
                (institution_id, student_id, "Case record saved", updated_by, now),
            )

    def case_history(self, institution_id: str, student_id: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT action, actor_email, created_at FROM case_events WHERE institution_id=? AND student_id=? ORDER BY id DESC LIMIT 20",
                (institution_id, student_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_cases(self, institution_id: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT student_id, owner_email, status, priority, due_date, updated_by, updated_at FROM support_cases WHERE institution_id=? ORDER BY updated_at DESC",
                (institution_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def case_summary(self, institution_id: str) -> dict:
        with self.connection() as db:
            rows = db.execute("SELECT status, owner_email FROM support_cases WHERE institution_id=?", (institution_id,)).fetchall()
        return {
            "total": len(rows),
            "unassigned": sum(not row["owner_email"] for row in rows),
            "open": sum(row["status"] not in {"Closed", "Resolved"} for row in rows),
            "resolved": sum(row["status"] in {"Closed", "Resolved"} for row in rows),
        }

    def monitoring_summary(self, institution_id: str) -> dict:
        with self.connection() as db:
            row = db.execute(
                """SELECT COUNT(*) total,
                SUM(CASE WHEN risk_band='Insufficient data' THEN 1 ELSE 0 END) insufficient,
                AVG(data_completeness) mean_completeness,
                SUM(CASE WHEN risk_band='High' THEN 1 ELSE 0 END) high_count
                FROM prediction_audit WHERE institution_id=?""", (institution_id,)
            ).fetchone()
        return {key: (row[key] or 0) for key in row.keys()}

    def record(self, institution_id: str, result: dict) -> int:
        with self.connection() as db:
            cursor = db.execute(
                """INSERT INTO prediction_audit
                (created_at, institution_id, student_id, risk_probability, risk_band,
                 model_status, data_completeness, reason_codes, policy_flags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(), institution_id,
                    result["student_id"], result["risk_probability"], result["risk_band"],
                    result["model_status"], result["data_completeness"],
                    json.dumps(result["reason_codes"]), json.dumps(result["policy_flags"]),
                ),
            )
            return int(cursor.lastrowid)

    def recent(self, limit: int = 100) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM prediction_audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

