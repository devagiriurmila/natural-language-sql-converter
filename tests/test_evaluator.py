import pandas as pd

from evaluator import (BENCHMARK, exact_match, normalize_sql, results_match, run_evaluation,
                       run_offline_check)
from sql_generator import GenerationResult
from sql_validator import validate_sql


def df(rows, cols=("a", "b")):
    return pd.DataFrame(rows, columns=list(cols))


def test_benchmark_size_and_ids():
    assert len(BENCHMARK) >= 30
    assert len({b["id"] for b in BENCHMARK}) == len(BENCHMARK)
    assert any(b["expected_behavior"] == "no_sql" for b in BENCHMARK)


def test_all_reference_queries_are_valid():
    for b in BENCHMARK:
        if b["reference_sql"]:
            assert validate_sql(b["reference_sql"]).is_valid, b["id"]


def test_results_match_ignores_row_order_unless_required():
    a, b = df([(1, "x"), (2, "y")]), df([(2, "y"), (1, "x")])
    assert results_match(a, b)
    assert not results_match(a, b, order_matters=True)


def test_results_match_float_rounding_and_alias_names():
    assert results_match(df([(81.2,)], ["avg_marks"]), df([(81.2000001,)], ["AVG(marks)"]))
    assert not results_match(df([(81.2,)], ["x"]), df([(81.2,)], ["y"]), strict_columns=True)


def test_results_match_detects_differences():
    assert not results_match(df([(1, "x")]), df([(1, "z")]))
    assert not results_match(df([(1, "x")]), df([(1, "x"), (2, "y")]))
    assert not results_match(df([(1,)], ["a"]), df([(1, "x")]))
    assert not results_match(df([(1, "x"), (1, "x")]), df([(1, "x"), (2, "y")]))


def test_exact_match_normalisation():
    assert exact_match("select  name FROM students;", "SELECT name FROM students")
    assert not exact_match("SELECT name FROM students", "SELECT * FROM students")
    assert not exact_match("", "SELECT 1")
    assert normalize_sql("not sql at all") == "not sql at all"


def test_offline_check_is_perfect(db_path):
    summary, details = run_offline_check(db_path)
    row = summary.iloc[0]
    assert row["Valid SQL rate (%)"] == 100 and row["Execution accuracy (%)"] == 100
    assert row["Safe-refusal rate (%)"] == 100 and row["Error rate (%)"] == 0
    assert (details["mode"] == "offline_oracle").all()


def test_bad_model_scores_low_and_different_sql_can_still_be_correct(db_path):
    def gen(question, strategy):
        item = next(b for b in BENCHMARK if b["question"] == question)
        if item["id"] == 6:  # equivalent but textually different SQL
            return GenerationResult("ok", strategy, "SELECT COUNT(student_id) AS n FROM students")
        if item["id"] == 1:
            return GenerationResult("ok", strategy, "DROP TABLE students")
        if item["expected_behavior"] == "no_sql":
            return GenerationResult("ok", strategy, "SELECT * FROM students")  # should have refused
        return GenerationResult("error", strategy, message="boom")

    summary, details = run_evaluation(gen, ["zero_shot"], db_path)
    d = details.set_index("id")
    assert d.loc[6, "execution_match"] and not d.loc[6, "exact_match"]
    assert not d.loc[1, "valid_sql"] and d.loc[1, "technical_error"]
    assert not d.loc[31, "behavior_correct"]
    assert summary.iloc[0]["Execution accuracy (%)"] < 10


def test_evaluation_never_modifies_database(db_path):
    run_offline_check(db_path)
    from database import table_preview
    assert len(table_preview("students", db_path)) == 16
