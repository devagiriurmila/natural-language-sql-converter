# Project Report – Natural Language-to-SQL Generator Using Prompt Engineering
Subject: 24CS2022 – Prompt Engineering  |  Student: ________  |  Register no.: ________

## 1. Abstract
This project builds a web application that converts English questions into SQLite queries using a large language model and
three prompt strategies (zero-shot, few-shot, schema-aware). Generated SQL is treated as untrusted: it is parsed, checked
against the schema, row-limited and executed on a read-only database only after user confirmation. A 34-question benchmark
and defined metrics compare the strategies. Live results are to be filled in Section 16 after real experiments.

## 2. Introduction
Databases hold most organisational data, but SQL is a barrier for non-programmers. LLMs can bridge this gap, yet they may
hallucinate schema elements or produce unsafe statements. Prompt engineering plus validation makes the approach practical.

## 3. Problem statement
Allow users to query a student database in English, safely and verifiably, and measure how prompt design affects accuracy.

## 4. Objectives
(1) Natural-language-to-SQL generation; (2) three prompt strategies; (3) multi-layer SQL validation; (4) safe execution and
result display; (5) reproducible evaluation; (6) beginner-friendly delivery with tests and documentation.

## 5. Existing system and limitations
Manual SQL writing needs expertise. Generic chatbots give SQL without schema knowledge, without validation, and may
suggest destructive statements; they do not measure accuracy.

## 6. Proposed system
A Streamlit app with modules for prompts, LLM access, validation, database execution and evaluation (Section 9).

## 7. Feasibility study
*Technical:* all components are free, open-source Python libraries; SQLite needs no server. *Economic:* only LLM API usage
costs money; tests and the offline check are free. *Operational:* runs on a laptop in VS Code on Windows.

## 8. Literature review guidance
Do not copy references you have not read. Search and cite (after verifying each one yourself): Google Scholar / ACL Anthology /
arXiv for "text-to-SQL", "large language models text-to-SQL evaluation", "few-shot prompting language models", and benchmark
descriptions such as Spider (Yale) and BIRD. Read the official documentation of SQLite, sqlglot, Streamlit and the OpenAI API.
Write 5–8 verified references in the format your college requires. *No references are listed here on purpose.*

## 9. System architecture
Question → Prompt builder → LLM → Response parser → Validator → (user clicks Execute) → Read-only SQLite executor → Table + explanation.
Evaluator and UI wrap the same modules. See README for the diagram.

## 10. Module descriptions
`config.py` settings and schema; `database.py` creation, seeding, safe execution; `prompt_templates.py` strategies;
`sql_generator.py` API calls and parsing; `sql_validator.py` security checks; `evaluator.py` benchmark and metrics; `app.py` UI.

## 11. Database design
`students(student_id PK, name, department, marks, year)`, `courses(course_id PK, course_name, credits)`,
`enrollments(enrollment_id PK, student_id FK, course_id FK, semester)`. 16 students, 6 courses, 32 enrollments, all fictional
and deterministic (e.g. CSE average marks = 81.2).

## 12. Prompt engineering techniques
Zero-shot (task + schema + rules); few-shot (adds 5 worked examples and one refusal example); schema-aware (adds column
descriptions, relationships, value hints, ambiguity rules). Shared: role/task statement, SQLite-only rule, read-only rule,
clarification/unsupported statuses, JSON output contract, concise explanation instead of hidden reasoning.

## 13. Algorithm and workflow
1. Read question. 2. Build messages for the chosen strategy. 3. Call model (timeout, 1 retry). 4. Strip fences, parse JSON.
5. If status ≠ ok show message. 6. Validate SQL. 7. If valid, enable Execute. 8. On click run on read-only connection with
authorizer, time limit and row limit. 9. Show DataFrame, count and explanation. 10. Log in session history.

## 14. Experimental setup
Fixed database and 34 benchmark questions (30 answerable: filter, aggregate, sort, group, join; 4 that must be refused).
Same model, temperature and prompts-except-strategy for all runs. Record: model name, date, temperature, number of questions.
Offline pipeline check: `python evaluator.py --offline`. Live: `python evaluator.py --live` (saves `data/evaluation_results.csv`).

## 15. Evaluation metrics
Valid SQL rate; Execution accuracy (same column count and rows, numbers rounded to 2 decimals, order compared only when the
question requires it); Exact SQL match (normalised SQL equality, reported separately); Average response time; Error rate
(API/parse/validation/execution failures ÷ all questions); Safe-refusal rate (non-answerable questions answered with no SQL).

## 16. Results (fill in after running live experiments)
Model: ______  Date: ______  Temperature: ______

| Strategy | Valid SQL % | Execution accuracy % | Exact match % | Avg time (s) | Error rate % | Safe-refusal % |
|---|---|---|---|---|---|---|
| Zero-shot | | | | | | |
| Few-shot | | | | | | |
| Schema-aware | | | | | | |

Offline pipeline check (verifies code only, not the LLM): see terminal output of `python evaluator.py --offline`.

## 17. Limitations
Small single-database benchmark; results vary by model and run; valid-but-wrong SQL possible; CTE/UNION unsupported;
simplified column resolution; requires internet and paid API for live generation.

## 18. Security considerations
Defence in depth (README): prompts, parser, statement-type allow-list, schema check, function block-list, comment ban, LIMIT,
read-only connection, SQLite authorizer, timeout, explicit user execution, sanitised errors, `.env` ignored by Git. Residual
risks: parser/SQLite bugs, resource exhaustion within limits, logic errors in generated SQL.

## 19. Future scope
Self-correction loop, RAG for large schemas, multi-database support, role-based access, caching, richer charts.

## 20. Conclusion
The project demonstrates that prompt design shapes SQL generation quality, and that engineering controls (validation,
read-only execution, evaluation) are what make LLM-generated SQL usable. Conclusions about which strategy is best must be
drawn from the live results in Section 16.
