# Test cases
Run all automated tests: `python -m pytest` (99 tests; offline; temporary databases; API mocked).

## A. Automated test groups
| File | Input | Expected behaviour | Pass criteria |
|---|---|---|---|
| test_database.py | init twice | one set of data, 16 students | counts equal 16 |
| | insert enrollment with unknown student | `IntegrityError` | raised |
| | `DELETE` via executor | refused, data intact | `ok=False`, 16 rows remain |
| | 8-way cross join with 0.3 s limit | stopped | error contains "too long" |
| | `max_rows=5` | 5 rows | len == 5 |
| test_sql_validator.py | valid SELECT / JOIN / subquery | accepted, LIMIT added | `is_valid` |
| | `SELEC * FROM students` | rejected | not valid |
| | unknown table/column, `sqlite_master` | rejected | not valid |
| | INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/PRAGMA/ATTACH/BEGIN | rejected | not valid |
| | `SELECT ...; DROP TABLE ...` | rejected "Multiple" | not valid |
| | SQL with `--` or `/* */` | rejected | not valid |
| | empty / None | rejected | not valid |
| | `LIMIT 5000` with max 10 | reduced to 10 | ends with `LIMIT 10` |
| test_prompt_templates.py | each strategy | contains schema + safety rules | strings present |
| | zero-shot vs few-shot vs schema-aware | no examples / examples / descriptions | markers present |
| test_sql_generator.py (mock API) | fenced JSON, plain SQL, JSON+chatter | parsed | `ok` |
| | empty, malformed, unknown status | error status | `status == "error"` |
| | missing API key | no API call, friendly message | message has `OPENAI_API_KEY` |
| | auth, quota, model-not-found, connection, timeout errors | friendly messages, no secrets | words match |
| test_evaluator.py | result comparison | order/float/alias rules | per test |
| | oracle run | 100 % on all metrics | offline check |
| | weak fake model | low scores; equivalent SQL counts as correct | per test |
| test_app_smoke.py | start without key | no crash; error shown on Generate | no exception |
| | mocked valid / `DROP TABLE` generation | Execute enabled / disabled | button state |

## B. Manual demo cases (needs API key)
| # | Question | Expected | Pass criteria |
|---|---|---|---|
| 1 | Show all students from CSE. | SELECT with `department = 'CSE'`, 5 rows | validation OK, 5 rows |
| 2 | Show the top five students by marks. | ORDER BY marks DESC LIMIT 5 | first row Priya Nair (92) |
| 3 | Find departments whose average marks exceed 75. | GROUP BY + HAVING | CSE, ECE, IT |
| 4 | Show students enrolled in Database Systems during semester 2. | 3-table JOIN | rows returned |
| 5 | Delete all students. | no SQL; "unsupported" message | Execute not offered |
| 6 | Show student email addresses. | no SQL (no such column) | message shown |
| 7 | Show me the good ones. | clarification request | message shown |
| 8 | No API key set | helpful message, app still usable | no crash |
