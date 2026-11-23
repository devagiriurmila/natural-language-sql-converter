"""Benchmark + metrics for comparing the three prompt strategies.

METRIC DEFINITIONS (answerable = questions that have a reference SQL):
 * Valid SQL rate      = answerable questions whose generated SQL passed validate_sql() / answerable.
 * Execution accuracy  = answerable questions whose validated SQL ran AND returned the same result
                         as the reference SQL / answerable. Comparison: same column count, same
                         rows after rounding numbers to 2 decimals; row ORDER is compared only
                         when the benchmark item says order matters (e.g. "top five"). Column
                         alias names are ignored unless strict_columns=True.
 * Exact SQL match     = normalised generated SQL (parsed, re-printed, lower-cased) equals the
                         normalised reference SQL / answerable. Reported separately.
 * Avg response time   = mean seconds the generation call took (all questions).
 * Error rate          = questions with a technical failure (API/parse error, validation failure
                         or execution failure) / all questions.
 * Safe-refusal rate   = non-answerable questions (delete request, unrelated, missing column,
                         vague) where the model returned NO sql / non-answerable questions.
Offline mode ("oracle") feeds the reference SQL back as if it were the model. It tests the
pipeline only and says NOTHING about LLM quality.
"""
from __future__ import annotations

import argparse
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Callable

import pandas as pd
import sqlglot

from config import PROJECT_ROOT, load_settings
from database import QueryResult, execute_validated, init_database
from prompt_templates import STRATEGIES, STRATEGY_LABELS
from sql_generator import GenerationResult, generate_sql
from sql_validator import validate_sql

logger = logging.getLogger(__name__)
RESULTS_CSV = PROJECT_ROOT / "data" / "evaluation_results.csv"

J = "JOIN enrollments e ON s.student_id = e.student_id JOIN courses c ON c.course_id = e.course_id"
# id, category, question, reference SQL (None = must NOT produce SQL), order_matters
_ITEMS: list[tuple[int, str, str, str | None, bool]] = [
    (1, "filter", "Show all details of students in the CSE department.", "SELECT * FROM students WHERE department = 'CSE'", False),
    (2, "filter", "List the names of students who scored above 80 marks.", "SELECT name FROM students WHERE marks > 80", False),
    (3, "filter", "List the names of students in year 2.", "SELECT name FROM students WHERE year = 2", False),
    (4, "filter", "Show the names and marks of MECH students.", "SELECT name, marks FROM students WHERE department = 'MECH'", False),
    (5, "filter", "List the names of CSE students with marks of at least 80.", "SELECT name FROM students WHERE department = 'CSE' AND marks >= 80", False),
    (6, "aggregate", "How many students are there in total?", "SELECT COUNT(*) FROM students", False),
    (7, "filter", "List all course names.", "SELECT course_name FROM courses", False),
    (8, "filter", "Which courses have more than 3 credits? Show the course names.", "SELECT course_name FROM courses WHERE credits > 3", False),
    (9, "sort", "Show the names and marks of the top five students by marks.", "SELECT name, marks FROM students ORDER BY marks DESC LIMIT 5", True),
    (10, "sort", "List the names of all students sorted alphabetically.", "SELECT name FROM students ORDER BY name ASC", True),
    (11, "sort", "Show the names and marks of the three students with the lowest marks.", "SELECT name, marks FROM students ORDER BY marks ASC LIMIT 3", True),
    (12, "sort", "Find the name of the student with the highest marks.", "SELECT name FROM students ORDER BY marks DESC LIMIT 1", False),
    (13, "sort", "Show the names and marks of year 4 students, highest marks first.", "SELECT name, marks FROM students WHERE year = 4 ORDER BY marks DESC", True),
    (14, "aggregate", "What is the average marks of all students?", "SELECT AVG(marks) FROM students", False),
    (15, "aggregate", "What are the minimum and maximum marks among all students?", "SELECT MIN(marks), MAX(marks) FROM students", False),
    (16, "aggregate", "How many students are in the IT department?", "SELECT COUNT(*) FROM students WHERE department = 'IT'", False),
    (17, "aggregate", "What is the total number of credits across all courses?", "SELECT SUM(credits) FROM courses", False),
    (18, "group", "Calculate the average marks of each department.", "SELECT department, AVG(marks) FROM students GROUP BY department", False),
    (19, "group", "Count the students in each department.", "SELECT department, COUNT(*) FROM students GROUP BY department", False),
    (20, "group", "Find the departments whose average marks exceed 75. Show only department names.", "SELECT department FROM students GROUP BY department HAVING AVG(marks) > 75", False),
    (21, "group", "Show the maximum marks in each year.", "SELECT year, MAX(marks) FROM students GROUP BY year", False),
    (22, "group", "Which departments have more than 3 students? Show the department names.", "SELECT department FROM students GROUP BY department HAVING COUNT(*) > 3", False),
    (23, "join", "Show the names of students enrolled in the Python Programming course.", f"SELECT s.name FROM students s {J} WHERE c.course_name = 'Python Programming'", False),
    (24, "join", "Count the enrollments in each course. Show the course name and the count.", "SELECT c.course_name, COUNT(*) FROM enrollments e JOIN courses c ON c.course_id = e.course_id GROUP BY c.course_name", False),
    (25, "join", "Show the names of students enrolled in Database Systems during semester 2.", f"SELECT s.name FROM students s {J} WHERE c.course_name = 'Database Systems' AND e.semester = 2", False),
    (26, "join", "How many students are enrolled in Machine Learning?", f"SELECT COUNT(*) FROM students s {J} WHERE c.course_name = 'Machine Learning'", False),
    (27, "join", "List the course names that the student Aarav Sharma is enrolled in.", f"SELECT c.course_name FROM students s {J} WHERE s.name = 'Aarav Sharma'", False),
    (28, "join", "Find the average marks of students enrolled in Python Programming.", f"SELECT AVG(s.marks) FROM students s {J} WHERE c.course_name = 'Python Programming'", False),
    (29, "join", "Which students are enrolled in more than two courses? Show their names.", f"SELECT s.name FROM students s {J} GROUP BY s.student_id, s.name HAVING COUNT(*) > 2", False),
    (30, "join", "List the distinct names of students enrolled in any course during semester 4.", f"SELECT DISTINCT s.name FROM students s {J} WHERE e.semester = 4", False),
    (31, "refusal", "Delete all students from the CSE department.", None, False),
    (32, "refusal", "What is the weather in Chennai today?", None, False),
    (33, "refusal", "Show the email addresses of all students.", None, False),
    (34, "refusal", "Show me the good ones.", None, False),
]
BENCHMARK: list[dict] = [
    {"id": i, "category": c, "question": q, "reference_sql": r, "order_matters": o,
     "expected_behavior": "answer" if r else "no_sql"}
    for i, c, q, r, o in _ITEMS
]

# ------------------------------------------------------------ comparison ----
def normalize_sql(sql: str | None) -> str:
    text = (sql or "").strip().rstrip(";").strip()
    try:
        return sqlglot.parse_one(text, read="sqlite").sql(dialect="sqlite").lower()
    except Exception:
        return " ".join(text.lower().split())


def _cell(value) -> object:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 2)
    return str(value)


def results_match(predicted: pd.DataFrame, expected: pd.DataFrame, order_matters: bool = False,
                  strict_columns: bool = False) -> bool:
    """Execution-accuracy comparison (see module docstring)."""
    if predicted.shape[1] != expected.shape[1] or predicted.shape[0] != expected.shape[0]:
        return False
    if strict_columns and [c.lower() for c in predicted.columns] != [c.lower() for c in expected.columns]:
        return False
    p = [tuple(_cell(v) for v in row) for row in predicted.itertuples(index=False)]
    e = [tuple(_cell(v) for v in row) for row in expected.itertuples(index=False)]
    return p == e if order_matters else Counter(p) == Counter(e)


def exact_match(generated: str | None, reference: str | None) -> bool:
    return bool(generated) and normalize_sql(generated) == normalize_sql(reference)


# ------------------------------------------------------------ evaluation ----
Generator = Callable[[str, str], GenerationResult]


def _run_sql(sql: str, db_path, max_rows: int) -> tuple[bool, QueryResult | None]:
    validation = validate_sql(sql, max_rows)
    if not validation.is_valid:
        return False, None
    return True, execute_validated(validation, db_path, max_rows)


def evaluate_item(item: dict, strategy: str, generator: Generator, db_path, max_rows: int = 100) -> dict:
    start = time.perf_counter()
    gen = generator(item["question"], strategy)
    seconds = gen.elapsed or (time.perf_counter() - start)
    row = {"id": item["id"], "category": item["category"], "question": item["question"],
           "strategy": strategy, "status": gen.status, "generated_sql": gen.sql,
           "reference_sql": item["reference_sql"] or "", "valid_sql": False, "executed": False,
           "execution_match": False, "exact_match": False, "technical_error": False,
           "behavior_correct": False, "seconds": round(seconds, 3)}
    if item["expected_behavior"] == "no_sql":
        row["behavior_correct"] = gen.status in {"clarification_needed", "unsupported"} and not gen.sql
        row["technical_error"] = gen.status == "error"
        return row
    if gen.status == "error":
        row["technical_error"] = True
        return row
    if not gen.ok:  # model declined to answer an answerable question
        return row
    valid, result = _run_sql(gen.sql, db_path, max_rows)
    row["valid_sql"] = valid
    if not valid or result is None or not result.ok:
        row["technical_error"] = True
        return row
    row["executed"] = True
    ref_ok, ref = _run_sql(item["reference_sql"], db_path, max_rows)
    if ref_ok and ref is not None and ref.ok:
        row["execution_match"] = results_match(result.data, ref.data, item["order_matters"])
    row["exact_match"] = exact_match(gen.sql, item["reference_sql"])
    return row


def summarise(details: pd.DataFrame) -> pd.DataFrame:
    out = []
    for strategy, g in details.groupby("strategy", sort=False):
        ans, ref = g[g["reference_sql"] != ""], g[g["reference_sql"] == ""]
        pct = lambda s, n: round(100 * s / n, 1) if n else None  # noqa: E731
        out.append({
            "Strategy": STRATEGY_LABELS.get(strategy, strategy), "Questions": len(g), "Answerable": len(ans),
            "Valid SQL rate (%)": pct(ans["valid_sql"].sum(), len(ans)),
            "Execution accuracy (%)": pct(ans["execution_match"].sum(), len(ans)),
            "Exact SQL match (%)": pct(ans["exact_match"].sum(), len(ans)),
            "Avg response time (s)": round(g["seconds"].mean(), 3),
            "Error rate (%)": pct(g["technical_error"].sum(), len(g)),
            "Safe-refusal rate (%)": pct(ref["behavior_correct"].sum(), len(ref)),
        })
    return pd.DataFrame(out)


def run_evaluation(generator: Generator, strategies: list[str] | None = None, db_path=None,
                   limit: int | None = None, mode: str = "live",
                   progress: Callable[[int, int], None] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    db_path = init_database(db_path)
    strategies = strategies or STRATEGIES
    items = BENCHMARK[:limit] if limit else BENCHMARK
    rows, total = [], len(items) * len(strategies)
    for s in strategies:
        for item in items:
            rows.append(evaluate_item(item, s, generator, db_path, load_settings().max_rows))
            if progress:
                progress(len(rows), total)
    details = pd.DataFrame(rows)
    details["mode"] = mode
    return summarise(details), details


def oracle_generator(question: str, strategy: str) -> GenerationResult:
    """Pretend model that returns the reference SQL (offline pipeline check)."""
    item = next(i for i in BENCHMARK if i["question"] == question)
    if item["reference_sql"]:
        return GenerationResult("ok", strategy, item["reference_sql"], model="oracle", elapsed=0.0)
    return GenerationResult("unsupported", strategy, message="Not answerable.", model="oracle")


def run_offline_check(db_path=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    return run_evaluation(oracle_generator, [STRATEGIES[0]], db_path, mode="offline_oracle")


def live_generator(question: str, strategy: str) -> GenerationResult:
    return generate_sql(question, strategy)


def save_results(details: pd.DataFrame, path: Path = RESULTS_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    details.to_csv(path, index=False)
    return path


def load_saved_results(path: Path = RESULTS_CSV) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path).fillna("")
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate prompt strategies.")
    ap.add_argument("--offline", action="store_true", help="pipeline check, no API needed")
    ap.add_argument("--live", action="store_true", help="call the LLM API (costs money)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N questions")
    args = ap.parse_args()
    if args.live:
        if not load_settings().api_configured:
            raise SystemExit("OPENAI_API_KEY is missing - see README.")
        summary, details = run_evaluation(live_generator, limit=args.limit, mode="live")
        print("LIVE API RESULTS"); save_results(details)
    else:
        summary, details = run_offline_check()
        print("OFFLINE PIPELINE CHECK (reference SQL as stand-in model; NOT an LLM result)")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
