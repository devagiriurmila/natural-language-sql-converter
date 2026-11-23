
"""Central configuration and the single source of truth for the database schema."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Local Ollama configuration
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", "http://localhost:11434"
).rstrip("/")
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL", "qwen2.5-coder:3b"
).strip() or "qwen2.5-coder:3b"

# Database schema
SCHEMA: dict[str, dict[str, tuple[str, str]]] = {
    "students": {
        "student_id": ("INTEGER", "Unique student ID (primary key)"),
        "name": ("TEXT", "Full name of the student"),
        "department": ("TEXT", "Department code: CSE, ECE, MECH, CIVIL or IT"),
        "marks": ("INTEGER", "Overall marks out of 100"),
        "year": ("INTEGER", "Year of study, 1 to 4"),
    },
    "courses": {
        "course_id": ("INTEGER", "Unique course ID (primary key)"),
        "course_name": ("TEXT", "Course title, e.g. 'Python Programming', 'Database Systems'"),
        "credits": ("INTEGER", "Credit value of the course"),
    },
    "enrollments": {
        "enrollment_id": ("INTEGER", "Unique enrollment ID (primary key)"),
        "student_id": ("INTEGER", "Foreign key -> students.student_id"),
        "course_id": ("INTEGER", "Foreign key -> courses.course_id"),
        "semester": ("INTEGER", "Semester number (1 to 4) of the enrollment"),
    },
}

FOREIGN_KEYS: list[tuple[str, str, str, str]] = [
    ("enrollments", "student_id", "students", "student_id"),
    ("enrollments", "course_id", "courses", "course_id"),
]

TABLE_COLUMNS: dict[str, set[str]] = {
    table: set(columns) for table, columns in SCHEMA.items()
}


def _float_or_none(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Retained for compatibility with the existing project.
    api_key: str | None
    model: str
    temperature: float | None
    api_timeout: float
    db_path: Path
    max_rows: int
    query_timeout: float

    @property
    def api_configured(self) -> bool:
        # Ollama is local, so no API token is required.
        return True


def load_settings() -> Settings:
    """Read configuration from environment variables each time."""
    db_raw = os.getenv("DATABASE_PATH", "data/students.db")
    db_path = Path(db_raw)

    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    return Settings(
        api_key=None,
        model=OLLAMA_MODEL,
        temperature=_float_or_none(os.getenv("OLLAMA_TEMPERATURE", "0")),
        api_timeout=float(_int(os.getenv("OLLAMA_TIMEOUT_SECONDS"), 120)),
        db_path=db_path,
        max_rows=_int(os.getenv("MAX_RESULT_ROWS"), 100),
        query_timeout=float(_int(os.getenv("QUERY_TIMEOUT_SECONDS"), 5)),
    )
