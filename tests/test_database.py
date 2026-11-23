import sqlite3

import pytest

from database import (ENROLLMENTS, execute_validated, get_schema_description, init_database,
                      table_preview)
from sql_validator import ValidationResult, validate_sql


def run(sql, db_path, **kw):
    return execute_validated(validate_sql(sql, kw.get("max_rows", 100)), db_path, **kw)


def test_init_creates_file_and_directory(tmp_path):
    path = init_database(tmp_path / "nested" / "x.db")
    assert path.exists()


def test_init_is_idempotent_no_duplicates(db_path):
    init_database(db_path)
    init_database(db_path)
    assert len(table_preview("students", db_path)) == 16


def test_sample_data_sizes(db_path):
    assert len(table_preview("students", db_path)) >= 15
    assert len(table_preview("courses", db_path)) >= 5
    assert len(table_preview("enrollments", db_path)) == len(ENROLLMENTS)


def test_known_deterministic_results(db_path):
    r = run("SELECT AVG(marks) FROM students WHERE department = 'CSE'", db_path)
    assert r.ok and round(r.data.iloc[0, 0], 2) == 81.2
    r = run("SELECT name FROM students ORDER BY marks DESC LIMIT 1", db_path)
    assert r.data.iloc[0, 0] == "Priya Nair"


def test_foreign_keys_enforced_on_write_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO enrollments (student_id, course_id, semester) VALUES (999, 1, 1)")
    conn.close()


def test_no_orphan_enrollments(db_path):
    r = run("SELECT COUNT(*) FROM enrollments WHERE student_id NOT IN (SELECT student_id FROM students)", db_path)
    assert r.data.iloc[0, 0] == 0


def test_join_query(db_path):
    sql = ("SELECT s.name FROM students s JOIN enrollments e ON s.student_id = e.student_id "
           "JOIN courses c ON c.course_id = e.course_id WHERE c.course_name = 'Database Systems' AND e.semester = 2")
    r = run(sql, db_path)
    assert r.ok and len(r.data) > 0


def test_row_limit_applied(db_path):
    r = run("SELECT * FROM students", db_path, max_rows=5)
    assert r.ok and len(r.data) == 5


def test_refuses_unvalidated_query(db_path):
    bad = ValidationResult(False, "DROP TABLE students")
    r = execute_validated(bad, db_path)
    assert not r.ok
    assert len(table_preview("students", db_path)) == 16


def test_read_only_connection_blocks_writes(db_path):
    # Even a hand-made "valid" result containing a write must fail at database level.
    fake = ValidationResult(True, "x", "DELETE FROM students")
    r = execute_validated(fake, db_path)
    assert not r.ok
    assert len(table_preview("students", db_path)) == 16


def test_execution_failure_is_graceful(db_path):
    fake = ValidationResult(True, "x", "SELECT nope FROM students")
    r = execute_validated(fake, db_path)
    assert not r.ok and str(db_path) not in r.error


def test_missing_database_message(tmp_path):
    r = run("SELECT * FROM students", tmp_path / "missing.db")
    assert not r.ok


def test_timeout_stops_runaway_query(db_path):
    sql = ("SELECT COUNT(*) FROM students a, students b, students c, students d, students e, "
           "students f, students g, students h")
    r = execute_validated(validate_sql(sql), db_path, timeout=0.3)
    assert not r.ok and "too long" in r.error


def test_schema_description_mentions_all_tables():
    d = get_schema_description()
    for word in ("students", "courses", "enrollments", "FOREIGN KEYS"):
        assert word in d
