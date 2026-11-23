"""Database creation, schema description and SAFE query execution (SQLite)."""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from config import FOREIGN_KEYS, SCHEMA, load_settings
from sql_validator import ValidationResult

logger = logging.getLogger(__name__)

STUDENTS = [  # (student_id, name, department, marks, year) - fictional data
    (1, "Aarav Sharma", "CSE", 88, 2), (2, "Priya Nair", "CSE", 92, 3),
    (3, "Rohan Mehta", "CSE", 76, 1), (4, "Ananya Iyer", "CSE", 81, 2),
    (5, "Karthik Raja", "ECE", 67, 3), (6, "Divya Menon", "ECE", 74, 2),
    (7, "Vikram Singh", "ECE", 85, 4), (8, "Sneha Reddy", "MECH", 58, 1),
    (9, "Arjun Patel", "MECH", 72, 3), (10, "Meera Krishnan", "MECH", 79, 2),
    (11, "Rahul Verma", "CIVIL", 63, 4), (12, "Lakshmi Pillai", "CIVIL", 70, 2),
    (13, "Imran Khan", "IT", 90, 3), (14, "Kavya Rao", "IT", 83, 1),
    (15, "Sanjay Kumar", "IT", 77, 4), (16, "Nisha Joshi", "CSE", 69, 4),
]
COURSES = [
    (1, "Python Programming", 4), (2, "Database Systems", 4), (3, "Data Structures", 4),
    (4, "Machine Learning", 3), (5, "Computer Networks", 3), (6, "Digital Electronics", 3),
]
ENROLLMENTS = [  # (student_id, course_id, semester); enrollment_id is auto-numbered 1..N
    (1, 1, 1), (1, 2, 2), (1, 3, 3), (2, 1, 1), (2, 2, 2), (2, 4, 4), (3, 1, 1), (3, 3, 2),
    (4, 2, 2), (4, 5, 3), (5, 5, 3), (5, 6, 3), (6, 6, 2), (6, 1, 2), (7, 6, 4), (7, 5, 4),
    (8, 3, 1), (9, 3, 3), (9, 2, 2), (10, 1, 2), (10, 2, 2), (11, 3, 4), (12, 3, 2),
    (13, 1, 3), (13, 2, 2), (13, 4, 3), (14, 2, 1), (14, 1, 1), (15, 5, 4), (15, 2, 2),
    (16, 1, 4), (16, 4, 4),
]

CREATE_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY, name TEXT NOT NULL, department TEXT NOT NULL,
        marks INTEGER NOT NULL CHECK (marks BETWEEN 0 AND 100),
        year INTEGER NOT NULL CHECK (year BETWEEN 1 AND 4))""",
    """CREATE TABLE IF NOT EXISTS courses (
        course_id INTEGER PRIMARY KEY, course_name TEXT NOT NULL, credits INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS enrollments (
        enrollment_id INTEGER PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(student_id),
        course_id INTEGER NOT NULL REFERENCES courses(course_id),
        semester INTEGER NOT NULL)""",
]


@dataclass
class QueryResult:
    ok: bool
    data: pd.DataFrame
    error: str = ""
    elapsed: float = 0.0
    truncated: bool = False


def _path(db_path: str | Path | None) -> Path:
    return Path(db_path) if db_path else load_settings().db_path


def init_database(db_path: str | Path | None = None) -> Path:
    """Create folder, tables and sample data. Safe to call many times (no duplicates)."""
    path = _path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        for stmt in CREATE_STATEMENTS:
            conn.execute(stmt)
        if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            conn.executemany("INSERT INTO students VALUES (?,?,?,?,?)", STUDENTS)
            conn.executemany("INSERT INTO courses VALUES (?,?,?)", COURSES)
            conn.executemany(
                "INSERT INTO enrollments (student_id, course_id, semester) VALUES (?,?,?)",
                ENROLLMENTS)
        conn.commit()
    finally:
        conn.close()
    return path


def get_schema_description() -> str:
    """Plain-text CREATE-TABLE style description used inside prompts."""
    lines = []
    for table, cols in SCHEMA.items():
        defs = [f"  {c} {t}" for c, (t, _) in cols.items()]
        lines.append(f"TABLE {table} (\n" + ",\n".join(defs) + "\n)")
    lines.append("FOREIGN KEYS:")
    lines += [f"  {a}.{b} -> {c}.{d}" for a, b, c, d in FOREIGN_KEYS]
    return "\n".join(lines)


def _open_readonly(path: Path) -> sqlite3.Connection:
    # as_uri() percent-encodes spaces and handles Windows drive letters (file:///C:/...).
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _authorizer(action: int, arg1, arg2, dbname, source):  # noqa: ANN001
    """SQLite-level allow-list: reads and plain functions only."""
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def execute_validated(validation: ValidationResult, db_path: str | Path | None = None,
                      max_rows: int | None = None, timeout: float | None = None) -> QueryResult:
    """Run SQL that has passed validate_sql(). Refuses anything else."""
    if not isinstance(validation, ValidationResult) or not validation.is_valid:
        return QueryResult(False, pd.DataFrame(), "Refusing to run a query that failed validation.")
    settings = load_settings()
    max_rows = max_rows or settings.max_rows
    timeout = timeout or settings.query_timeout
    path = _path(db_path)
    if not path.exists():
        return QueryResult(False, pd.DataFrame(), "Database not found. Run: python database.py")

    start, conn = time.perf_counter(), None
    try:
        conn = _open_readonly(path)
        conn.set_authorizer(_authorizer)
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 10_000)
        deadline = start + timeout
        # Called every 10,000 VM steps; returning non-zero aborts the query.
        conn.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 10_000)
        cursor = conn.execute(validation.sql)
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)  # +1 lets us detect truncation
        truncated = len(rows) > max_rows
        df = pd.DataFrame(rows[:max_rows], columns=columns)
        return QueryResult(True, df, elapsed=time.perf_counter() - start, truncated=truncated)
    except sqlite3.OperationalError as exc:
        logger.warning("Query failed: %s", exc)
        msg = "The query took too long and was stopped." if "interrupt" in str(exc).lower() \
            else "The database could not run this query."
        return QueryResult(False, pd.DataFrame(), msg)
    except sqlite3.Error as exc:
        logger.warning("Database error: %s", exc)
        return QueryResult(False, pd.DataFrame(), "A database error occurred while running the query.")
    finally:
        if conn is not None:
            conn.close()


def table_preview(table: str, db_path: str | Path | None = None) -> pd.DataFrame:
    """Application-controlled read of a known table (table name is checked, not user input)."""
    if table not in SCHEMA:
        return pd.DataFrame()
    conn = _open_readonly(_path(db_path))
    try:
        return pd.read_sql_query(f"SELECT * FROM {table}", conn)  # noqa: S608 (allow-listed)
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Database ready at: {init_database()}")
