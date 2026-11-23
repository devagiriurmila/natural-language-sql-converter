# Natural Language-to-SQL Generator Using Prompt Engineering
Course project for **24CS2022 – Prompt Engineering**.

Ask questions about a student database in plain English. An LLM (OpenAI API) writes the SQL using one of three
prompt strategies; the app **validates** it, lets you **execute** it safely on SQLite, shows the results, and
explains the query.

## Problem statement
Writing SQL needs technical knowledge. LLMs can translate English to SQL, but their output is untrusted: it can be wrong,
invented, or dangerous. This project shows how prompt engineering improves generation **and** why validation is still essential.

## Objectives
1. Convert English questions to SQLite queries with an LLM.
2. Implement and compare zero-shot, few-shot and schema-aware prompting.
3. Treat model output as untrusted (multi-layer validation, read-only execution).
4. Measure results with a fixed 34-question benchmark and precise metrics.

## Architecture
```
Question -> prompt_templates.py -> sql_generator.py (OpenAI) -> JSON parse
         -> sql_validator.py (sqlglot, schema check, LIMIT) -> [user clicks Execute]
         -> database.py (read-only SQLite + authorizer + timeout) -> table + explanation
evaluator.py runs the benchmark through the same pipeline.   app.py = Streamlit UI.
```
| File | Role |
|---|---|
| `config.py` | settings from `.env`; the single source of truth for the schema |
| `database.py` | create/seed DB, schema text, **safe** execution |
| `prompt_templates.py` | the 3 prompt strategies |
| `sql_generator.py` | OpenAI calls, response parsing, friendly errors |
| `sql_validator.py` | security validation of generated SQL |
| `evaluator.py` | benchmark, metrics, offline check, live evaluation |
| `app.py` | Streamlit interface |
| `tests/` | 99 offline pytest tests (no internet, no API key) |

## Technology stack
Python 3.10+, Streamlit, SQLite (`sqlite3`), OpenAI Python SDK, python-dotenv, pandas, sqlglot, matplotlib (listed; charts use Streamlit's built-in chart), pytest.

## Folder structure
```
natural-language-sql/
  app.py  config.py  database.py  evaluator.py  prompt_templates.py  sql_generator.py  sql_validator.py
  requirements.txt  .env.example  .gitignore  pytest.ini  README.md
  data/.gitkeep           (students.db is created here automatically)
  tests/   conftest.py test_database.py test_sql_validator.py test_prompt_templates.py
           test_sql_generator.py test_evaluator.py test_app_smoke.py
  docs/    project_report.md syllabus_mapping.md viva_questions.md test_cases.md
```

## Setup on Windows (PowerShell) – follow in order
**Prerequisite:** Python 3.10 or newer from python.org (tick **"Add python.exe to PATH"** during install). Check: `python --version`.

```powershell
# 1. Open PowerShell (Start menu -> "PowerShell"), or in VS Code: Terminal > New Terminal
# 2. Go to the project folder (change the path to where you unzipped it)
cd C:\Users\YourName\Documents\natural-language-sql

# 3. Create the virtual environment
python -m venv .venv

# 4. Activate it (you should see (.venv) at the start of the prompt)
.\.venv\Scripts\Activate.ps1
#    If you get "running scripts is disabled": run this once, then activate again
#    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 5. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 6. Create your .env from the template
Copy-Item .env.example .env

# 7. Add your API key: open .env in VS Code (code .env) and replace your-api-key-here.
#    Never share or commit .env (it is in .gitignore). Create keys at platform.openai.com.

# 8. Initialise the database (also happens automatically when the app starts)
python database.py

# 9. Launch the app (opens http://localhost:8501)
streamlit run app.py

# 10. Run the automated tests (no API key or internet needed)
python -m pytest

# 11. Run the offline evaluator (pipeline check, no API)
python evaluator.py --offline
#     Optional LIVE evaluation (needs key; costs credits; 3 strategies x N questions)
python evaluator.py --live --limit 10

# 12. Git (first time only)
git init
git add .
git commit -m "Natural Language-to-SQL project"
#    Check that .env is NOT listed:  git status
```
The app starts without an API key: you can browse the schema, read the prompts and run the offline check.

## Troubleshooting (Windows)
| Problem | Fix |
|---|---|
| `python` is not recognized | Reinstall Python with "Add to PATH", or try `py -m venv .venv` and `py --version`. Restart PowerShell. |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, then activate again. Or use `cmd` and `.venv\Scripts\activate.bat`. |
| `ModuleNotFoundError` | The venv is not active or packages are missing: activate, then `pip install -r requirements.txt`. |
| "OPENAI_API_KEY is missing" | `.env` must be in the project root (next to `app.py`), contain a real key, and the app must be restarted. |
| "Model ... was not found" | Set `OPENAI_MODEL` in `.env` to a model your account can use. |
| API error about `temperature` | Some models reject it: set `OPENAI_TEMPERATURE=` (blank) in `.env`. |
| Quota / rate-limit message | Add billing credit or wait; check usage in the OpenAI dashboard. |
| "Database not found" / path errors | Run `python database.py` from the project folder; keep `DATABASE_PATH=data/students.db`. |
| "Validation failed" | Working as designed: the generated SQL used an unknown column/table, a write, a comment, etc. Rephrase or switch strategy. |
| `streamlit` not recognized | Activate the venv, or run `python -m streamlit run app.py`. |
| Port busy | `streamlit run app.py --server.port 8502`. |

## Security measures (defence in depth)
1. Prompts forbid writes (not trusted as the boundary).
2. `sqlglot` parses SQL in SQLite dialect; syntax errors are rejected.
3. Exactly one statement; it must be a plain `SELECT` (INSERT/UPDATE/DELETE/DDL/PRAGMA/ATTACH/transactions/CTE/UNION rejected).
4. Every table and column must exist in the schema; unknown functions (e.g. `load_extension`) are rejected; comments rejected.
5. `LIMIT` is forced to `MAX_RESULT_ROWS`.
6. Execution uses a **read-only** SQLite connection (`mode=ro`), a SQLite **authorizer** (allows only SELECT/READ/FUNCTION),
   a time limit (progress handler) and SQLite length limits. `database.execute_validated` refuses anything not marked valid.
7. Users must click **Execute**; generation never runs SQL. Error messages shown to the user hide paths and internals.

## Known limitations
* Validation is strong but not a formal proof of safety. Semantically *wrong* but valid SQL still runs (that is what accuracy metrics measure).
* Column checks are simplified (e.g. a column valid in another table of the same query may pass in an ambiguous join).
* No `WITH`/`UNION`; a few legitimate questions are therefore refused.
* Only one small fictional database; results do not generalise to large real schemas.
* Live results depend on the model, its version and API availability; `openai`/`sqlglot` APIs may change in future versions.
* Tests were run in a Linux sandbox; the Windows commands above were written but **not executed on Windows**.

## Future enhancements
Self-correction loop (feed validation errors back to the model), RAG over schema documentation for large databases, chain-of-thought-free
self-consistency voting, multi-database support, chart generation, user authentication, caching of repeated questions.
