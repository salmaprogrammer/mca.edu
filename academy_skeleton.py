from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import sqlite3
from typing import Dict, List, Optional


class Role(str, Enum):
    ADMIN = "admin"
    ASSISTANT = "assistant"
    TEACHER = "teacher"
    STUDENT = "student"
    PARENT = "parent"


ROLE_PERMISSIONS: Dict[Role, set[str]] = {
    Role.ADMIN: {
        "manage_users",
        "manage_students",
        "assign_teacher",
        "track_attendance",
        "track_exams",
        "manage_payments",
        "view_financial_reports",
    },
    Role.ASSISTANT: {
        "track_attendance",
        "track_exams",
        "view_students",
    },
    Role.TEACHER: {
        "view_assigned_students",
        "view_calendar",
        "track_attendance",
        "track_homework",
        "track_exams",
    },
    Role.STUDENT: {
        "view_own_dashboard",
    },
    Role.PARENT: {
        "view_child_dashboard",
        "view_invoice",
    },
}


def can(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def calculate_remaining_sessions(total_sessions: int, consumed_sessions: int) -> int:
    """Core tracking equation: total - consumed = remaining."""
    return max(0, int(total_sessions) - int(consumed_sessions))


@dataclass
class SessionCounter:
    total_sessions: int
    consumed_sessions: int

    @property
    def remaining_sessions(self) -> int:
        return calculate_remaining_sessions(self.total_sessions, self.consumed_sessions)


class AcademyDB:
    """Low-level DB bootstrap + basic queries for linking teacher-student + tracking."""

    def __init__(self, db_path: str = "academy.db") -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def create_user(self, full_name: str, role: Role, phone: Optional[str] = None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (full_name, role, phone, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (full_name.strip(), role.value, (phone or "").strip(), datetime.utcnow().isoformat()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def create_student_profile(
        self,
        student_user_id: int,
        teacher_user_id: int,
        round_name: str,
        total_sessions: int,
        payment_status: str = "pending",
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO student_profiles (
                    student_user_id,
                    teacher_user_id,
                    round_name,
                    total_sessions,
                    consumed_sessions,
                    payment_status,
                    created_at
                )
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    student_user_id,
                    teacher_user_id,
                    round_name.strip(),
                    int(total_sessions),
                    payment_status,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def assign_teacher(self, student_user_id: int, teacher_user_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE student_profiles
                SET teacher_user_id = ?, updated_at = ?
                WHERE student_user_id = ?
                """,
                (teacher_user_id, datetime.utcnow().isoformat(), student_user_id),
            )
            conn.commit()

    def teacher_students(self, teacher_user_id: int) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    u.id AS student_id,
                    u.full_name AS student_name,
                    sp.round_name,
                    sp.total_sessions,
                    sp.consumed_sessions,
                    (sp.total_sessions - sp.consumed_sessions) AS remaining_sessions,
                    sp.payment_status
                FROM student_profiles sp
                JOIN users u ON u.id = sp.student_user_id
                WHERE sp.teacher_user_id = ?
                ORDER BY u.full_name
                """,
                (teacher_user_id,),
            )
            return list(cur.fetchall())

    def add_attendance(
        self,
        student_user_id: int,
        teacher_user_id: int,
        status: str,
        homework_text: str = "",
        exam_grade: Optional[int] = None,
        note: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO attendance_records (
                    student_user_id,
                    teacher_user_id,
                    session_date,
                    status,
                    homework_text,
                    exam_grade,
                    note,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    student_user_id,
                    teacher_user_id,
                    date.today().isoformat(),
                    status,
                    homework_text.strip(),
                    exam_grade,
                    note.strip(),
                    datetime.utcnow().isoformat(),
                ),
            )

            if status.lower() == "present":
                conn.execute(
                    """
                    UPDATE student_profiles
                    SET consumed_sessions = consumed_sessions + 1,
                        updated_at = ?
                    WHERE student_user_id = ?
                    """,
                    (datetime.utcnow().isoformat(), student_user_id),
                )

            conn.commit()

    def set_payment_confirmed(self, student_user_id: int, charged_sessions: int) -> int:
        """Marks round as paid and creates parent-facing invoice without amount."""
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE student_profiles
                SET payment_status = 'paid',
                    updated_at = ?
                WHERE student_user_id = ?
                """,
                (datetime.utcnow().isoformat(), student_user_id),
            )

            cur = conn.execute(
                """
                INSERT INTO invoices (
                    student_user_id,
                    invoice_date,
                    charged_sessions,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    student_user_id,
                    date.today().isoformat(),
                    int(charged_sessions),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def create_calendar_event(
        self,
        teacher_user_id: int,
        student_user_id: int,
        title: str,
        start_at_iso: str,
        end_at_iso: str,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO calendar_events (
                    teacher_user_id,
                    student_user_id,
                    title,
                    start_at,
                    end_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    teacher_user_id,
                    student_user_id,
                    title.strip(),
                    start_at_iso,
                    end_at_iso,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_student_dashboard(self, student_user_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    s.id AS student_id,
                    s.full_name AS student_name,
                    t.full_name AS teacher_name,
                    sp.round_name,
                    sp.total_sessions,
                    sp.consumed_sessions,
                    (sp.total_sessions - sp.consumed_sessions) AS remaining_sessions,
                    sp.payment_status
                FROM student_profiles sp
                JOIN users s ON s.id = sp.student_user_id
                JOIN users t ON t.id = sp.teacher_user_id
                WHERE sp.student_user_id = ?
                LIMIT 1
                """,
                (student_user_id,),
            )
            return cur.fetchone()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'assistant', 'teacher', 'student', 'parent')),
    phone TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parent_student_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_user_id INTEGER NOT NULL,
    student_user_id INTEGER NOT NULL,
    relationship TEXT DEFAULT 'parent',
    created_at TEXT NOT NULL,
    UNIQUE(parent_user_id, student_user_id),
    FOREIGN KEY(parent_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(student_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS student_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_user_id INTEGER NOT NULL UNIQUE,
    teacher_user_id INTEGER NOT NULL,
    round_name TEXT NOT NULL,
    total_sessions INTEGER NOT NULL,
    consumed_sessions INTEGER NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'pending' CHECK (payment_status IN ('pending', 'paid')),
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY(student_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(teacher_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_user_id INTEGER NOT NULL,
    teacher_user_id INTEGER NOT NULL,
    session_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('present', 'absent')),
    homework_text TEXT DEFAULT '',
    exam_grade INTEGER,
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(student_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(teacher_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_user_id INTEGER NOT NULL,
    student_user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(teacher_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(student_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_user_id INTEGER NOT NULL,
    invoice_date TEXT NOT NULL,
    charged_sessions INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(student_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_student_profiles_teacher ON student_profiles(teacher_user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_student_date ON attendance_records(student_user_id, session_date);
CREATE INDEX IF NOT EXISTS idx_calendar_teacher_start ON calendar_events(teacher_user_id, start_at);
"""


if __name__ == "__main__":
    db = AcademyDB("academy.db")
    db.init_schema()
    print("Database schema initialized: academy.db")