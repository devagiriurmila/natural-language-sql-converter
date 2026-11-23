import pytest

from sql_validator import validate_sql

VALID = [
    "SELECT * FROM students",
    "SELECT name FROM students WHERE marks > 80 ORDER BY marks DESC LIMIT 5",
    "SELECT department, AVG(marks) AS avg_marks FROM students GROUP BY department HAVING AVG(marks) > 75",
    "SELECT department, COUNT(*) FROM students GROUP BY department",
    "SELECT s.name FROM students s JOIN enrollments e ON s.student_id = e.student_id "
    "JOIN courses c ON c.course_id = e.course_id WHERE c.course_name LIKE '%Python%'",
    "SELECT name FROM students WHERE marks > (SELECT AVG(marks) FROM students)",
    "SELECT MIN(marks), MAX(marks) FROM students;",
]


@pytest.mark.parametrize("sql", VALID)
def test_valid_selects(sql):
    r = validate_sql(sql)
    assert r.is_valid, r.errors
    assert "LIMIT" in r.sql.upper()


@pytest.mark.parametrize("sql", [
    "SELEC * FROM students", "SELECT FROM students WHERE", "SELECT * FROM", "SELECT (1 FROM students",
])
def test_invalid_syntax(sql):
    assert not validate_sql(sql).is_valid


@pytest.mark.parametrize("sql", [
    "SELECT * FROM teachers", "SELECT salary FROM students", "SELECT * FROM sqlite_master",
    "SELECT s.salary FROM students s", "SELECT * FROM main.students",
])
def test_unknown_tables_and_columns(sql):
    assert not validate_sql(sql).is_valid


@pytest.mark.parametrize("sql", [
    "INSERT INTO students VALUES (99,'x','CSE',1,1)", "UPDATE students SET marks = 100",
    "DELETE FROM students", "DROP TABLE students", "ALTER TABLE students ADD COLUMN x INT",
    "CREATE TABLE t (a INT)", "PRAGMA table_info(students)", "ATTACH DATABASE 'a.db' AS a",
    "DETACH DATABASE a", "BEGIN", "COMMIT", "VACUUM", "REPLACE INTO students VALUES (1,'a','b',1,1)",
])
def test_write_ddl_and_admin_rejected(sql):
    assert not validate_sql(sql).is_valid


@pytest.mark.parametrize("sql", [
    "SELECT * FROM students; DROP TABLE students", "SELECT 1 FROM students; SELECT 2 FROM students",
])
def test_multiple_statements(sql):
    r = validate_sql(sql)
    assert not r.is_valid and "Multiple" in r.errors[0]


@pytest.mark.parametrize("sql", [
    "SELECT * FROM students -- comment", "SELECT * FROM students /* c */",
    "SELECT * /* x */ FROM students",
])
def test_comments_rejected(sql):
    assert not validate_sql(sql).is_valid


@pytest.mark.parametrize("sql", ["", "   ", None])
def test_empty_rejected(sql):
    assert not validate_sql(sql).is_valid


@pytest.mark.parametrize("sql", [
    "WITH a AS (SELECT * FROM students) SELECT * FROM a",
    "SELECT name FROM students UNION SELECT course_name FROM courses",
    "SELECT load_extension('x') FROM students", "SELECT randomblob(1000000000) FROM students",
])
def test_unsupported_constructs(sql):
    assert not validate_sql(sql).is_valid


def test_row_limit_added_and_reduced():
    assert validate_sql("SELECT * FROM students", 10).sql.endswith("LIMIT 10")
    r = validate_sql("SELECT * FROM students LIMIT 5000", 10)
    assert r.sql.endswith("LIMIT 10") and r.warnings
    assert validate_sql("SELECT * FROM students LIMIT 3", 10).sql.endswith("LIMIT 3")


def test_oversized_sql_rejected():
    assert not validate_sql("SELECT name FROM students WHERE name = '" + "a" * 4000 + "'").is_valid
