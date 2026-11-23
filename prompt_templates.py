"""Prompt templates for the three prompt-engineering strategies.

Fairness: all strategies share the SAME task statement, safety rules and output
format (COMMON_RULES / OUTPUT_FORMAT). They differ only in what is added:
  * zero_shot    -> compact schema, no examples
  * few_shot     -> compact schema + worked examples
  * schema_aware -> detailed schema (descriptions, keys, value hints) + ambiguity rules
"""
from __future__ import annotations

from config import FOREIGN_KEYS, SCHEMA
from database import get_schema_description

ZERO_SHOT = "zero_shot"
FEW_SHOT = "few_shot"
SCHEMA_AWARE = "schema_aware"
STRATEGIES = [ZERO_SHOT, FEW_SHOT, SCHEMA_AWARE]
STRATEGY_LABELS = {
    ZERO_SHOT: "Zero-shot prompting",
    FEW_SHOT: "Few-shot prompting",
    SCHEMA_AWARE: "Schema-aware structured prompting",
}

TASK = "You convert English questions about a SQLite database into one SQL query."

COMMON_RULES = """RULES:
1. Generate SQLite-compatible SQL only.
2. Use ONLY the tables and columns listed in the schema. Never invent schema information.
3. Generate exactly ONE read-only SELECT query. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA, ATTACH or any statement that changes data.
4. Do not use SQL comments, WITH/CTEs or UNION.
5. If the question is ambiguous, or cannot be answered from this schema, do not guess: set "status" to "clarification_needed" and put a short question or reason in "message".
6. If the request is unrelated to this database, or asks to modify data, set "status" to "unsupported" and explain briefly in "message".
7. Put only SQL in the "sql" field - no Markdown, no explanation text."""

OUTPUT_FORMAT = """OUTPUT FORMAT: reply with a single JSON object and nothing else:
{"status": "ok" | "clarification_needed" | "unsupported",
 "sql": "<one SELECT query, or empty string when status is not ok>",
 "explanation": "<one or two plain-English sentences describing what the query does>",
 "message": "<empty when status is ok; otherwise the clarification or reason>"}"""

# Few-shot examples are intentionally different from the benchmark questions.
FEW_SHOT_EXAMPLES: list[tuple[str, str, str]] = [
    ("List the names of all ECE students.",
     "SELECT name FROM students WHERE department = 'ECE';",
     "Selects the names of students whose department is ECE."),
    ("Which third-year students have marks below 70?",
     "SELECT name, marks FROM students WHERE year = 3 AND marks < 70;",
     "Filters students by year 3 and marks under 70."),
    ("What is the lowest mark in each department?",
     "SELECT department, MIN(marks) AS lowest_marks FROM students GROUP BY department;",
     "Groups students by department and finds the minimum marks in each group."),
    ("Show the two best IT students.",
     "SELECT name, marks FROM students WHERE department = 'IT' ORDER BY marks DESC LIMIT 2;",
     "Takes IT students, sorts by marks from high to low and keeps two rows."),
    ("List course names with the number of students enrolled in semester 1.",
     "SELECT c.course_name, COUNT(*) AS enrolled FROM enrollments e "
     "JOIN courses c ON c.course_id = e.course_id WHERE e.semester = 1 GROUP BY c.course_name;",
     "Joins enrollments to courses, keeps semester 1 and counts rows per course."),
    ("Show the weather in Chennai.", "",
     "UNSUPPORTED: unrelated to the database."),
]


def schema_brief() -> str:
    return get_schema_description()


def schema_detailed() -> str:
    """Schema with column descriptions, keys and value hints (schema-aware strategy)."""
    parts = []
    for table, cols in SCHEMA.items():
        parts.append(f"Table `{table}`:")
        parts += [f"  - {c} ({t}): {d}" for c, (t, d) in cols.items()]
    parts.append("Relationships (use these for JOINs):")
    parts += [f"  - {a}.{b} references {c}.{d}" for a, b, c, d in FOREIGN_KEYS]
    parts.append("Value hints: department values are exactly 'CSE','ECE','MECH','CIVIL','IT'. "
                 "Course names include 'Python Programming' and 'Database Systems' "
                 "(use LIKE '%Python%' for partial names). year and semester are integers 1-4.")
    return "\n".join(parts)


def _ambiguity_rules() -> str:
    return ("AMBIGUITY RULES:\n"
            "- 'best', 'top' or 'highest' students means highest marks.\n"
            "- If a question needs a column that does not exist (e.g. email, age, fees, grade), use status \"unsupported\".\n"
            "- If the question is too vague to choose a table, column or condition, use status \"clarification_needed\".\n"
            "- When the question says 'show/list students', return the student name and the relevant columns.")


def build_system_prompt(strategy: str) -> str:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy!r}. Choose from {STRATEGIES}.")
    if strategy == SCHEMA_AWARE:
        schema_block = "DATABASE SCHEMA (detailed):\n" + schema_detailed()
    else:
        schema_block = "DATABASE SCHEMA:\n" + schema_brief()
    blocks = [TASK, schema_block, COMMON_RULES]
    if strategy == SCHEMA_AWARE:
        blocks.append(_ambiguity_rules())
    if strategy == FEW_SHOT:
        ex = []
        for q, sql, expl in FEW_SHOT_EXAMPLES:
            if sql:
                ex.append(f'Question: {q}\nAnswer: {{"status": "ok", "sql": "{sql}", "explanation": "{expl}", "message": ""}}')
            else:
                ex.append(f'Question: {q}\nAnswer: {{"status": "unsupported", "sql": "", "explanation": "", "message": "{expl}"}}')
        blocks.append("EXAMPLES:\n" + "\n\n".join(ex))
    blocks.append(OUTPUT_FORMAT)
    return "\n\n".join(blocks)


def build_messages(question: str, strategy: str) -> list[dict[str, str]]:
    """Chat messages for the API: system prompt + the user's question."""
    return [
        {"role": "system", "content": build_system_prompt(strategy)},
        {"role": "user", "content": f"Question: {question.strip()}"},
    ]
