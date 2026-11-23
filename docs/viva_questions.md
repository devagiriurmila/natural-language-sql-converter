# Viva questions and answers

**Python / tools**
1. **Why a virtual environment?** It keeps this project's packages separate from other projects so versions do not clash.
2. **What does `python-dotenv` do?** It loads settings such as `OPENAI_API_KEY` from a `.env` file into environment variables so secrets are not hard-coded.
3. **Why Streamlit?** It builds a web UI in pure Python; each user action re-runs the script and `st.session_state` keeps values between runs.
4. **What is Pandas used for here?** Query results are returned as DataFrames, which Streamlit displays as tables and the evaluator compares.
5. **Why pytest and mocks?** Tests must be repeatable, free and offline. A mock (fake client) replaces the real API so no key is needed.

**SQL / SQLite**
6. **What is SQLite?** A serverless database stored in one file, accessed with Python's built-in `sqlite3`.
7. **What is a foreign key?** A column referencing another table's primary key, e.g. `enrollments.student_id -> students.student_id`; with `PRAGMA foreign_keys=ON` SQLite rejects orphan rows.
8. **WHERE vs HAVING?** WHERE filters rows before grouping; HAVING filters groups after aggregation (e.g. `HAVING AVG(marks) > 75`).
9. **Why do we need a JOIN for "students enrolled in Python"?** The student name is in `students`, the course name in `courses`; `enrollments` links them.
10. **Why is a parameterised query used for app-controlled values?** It stops values from being interpreted as SQL. Model-generated SQL cannot be parameterised, so it is validated instead.

**LLMs and prompting**
11. **What is an LLM?** A neural network trained on large text data to predict the next token; it can follow instructions written as prompts.
12. **What is a token?** A piece of text (word or part of a word) the model reads/writes; cost and context limits are counted in tokens.
13. **What does temperature do?** It controls randomness; 0 gives the most repeatable output, which suits SQL generation.
14. **What is prompt engineering?** Designing instructions, context, examples and output formats so a model gives reliable results.
15. **Zero-shot prompting?** The task and schema are given with no examples.
16. **Few-shot prompting?** Several example question-to-SQL pairs are included so the model copies the pattern and format.
17. **Schema-aware structured prompting?** The prompt includes detailed tables, column descriptions, relationships, value hints and ambiguity rules.
18. **Why are the three strategies compared fairly?** They share the same task, rules and output format; only the extra guidance differs, and few-shot examples are not in the benchmark.
19. **What is a hallucination in this project?** The model invents a table, column or fact, e.g. `students.email`. The validator rejects it.
20. **Why ask for JSON output?** A fixed structure (`status`, `sql`, `explanation`, `message`) is easy to parse and lets the model say "clarification needed" instead of guessing.
21. **Why not ask for chain-of-thought?** We only need a short explanation; hidden reasoning is unnecessary and may be inconsistent.

**Safety / validation**
22. **Why not trust the prompt rules?** Models can ignore instructions or be manipulated, so code must enforce safety.
23. **What layers protect the database?** Parsing, single SELECT only, schema check, function/comment rejection, forced LIMIT, read-only connection, SQLite authorizer, time limit, user-click execution.
24. **What is SQL injection and how is it related?** Untrusted text altering a query's meaning. Here the "untrusted text" is model output; we validate and run it read-only.
25. **Why add LIMIT?** To bound memory and display size.

**Evaluation / extensions**
26. **Execution accuracy vs exact match?** Execution accuracy compares results; exact match compares SQL text. Different SQL can give the same correct result, so exact match is reported separately.
27. **What is "valid SQL rate"?** Share of answerable questions whose SQL passes validation.
28. **Why an offline "oracle" run?** It feeds the reference SQL through the pipeline to verify the code; it says nothing about LLM quality.
29. **Why must results not be invented?** Only measured live runs are valid evidence; the report keeps placeholders until they exist.
30. **What is RAG and how could it extend this project?** Retrieval-Augmented Generation fetches relevant documents at query time. For a database with hundreds of tables, retrieve only the relevant table descriptions and put them in the prompt.
31. **Limitations of this system?** Small database, valid-but-wrong SQL possible, no CTE/UNION, depends on model and API, validation not a formal proof.
