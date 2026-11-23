
"""Local Ollama LLM access. Generated SQL is untrusted and is never executed here."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from config import Settings, load_settings
from prompt_templates import STRATEGIES, build_messages

logger = logging.getLogger(__name__)
MAX_QUESTION_LENGTH = 500

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", "http://localhost:11434"
).rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")


@dataclass
class GenerationResult:
    status: str
    strategy: str
    sql: str = ""
    explanation: str = ""
    message: str = ""
    model: str = ""
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "ok" and bool(self.sql.strip())


class ResponseParseError(ValueError):
    """The model reply could not be parsed."""


_FENCE = re.compile(
    r"```(?:json|sql)?\s*(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def strip_markdown_fences(text: str) -> str:
    match = _FENCE.search(text)
    return match.group(1).strip() if match else text.strip()


def parse_model_response(raw: str | None) -> dict[str, str]:
    if raw is None or not raw.strip():
        raise ResponseParseError("The model returned an empty response.")

    text = strip_markdown_fences(raw)
    data: Any = None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                data = None

    if isinstance(data, dict):
        status = str(
            data.get("status", "ok" if data.get("sql") else "")
        ).strip().lower()

        if status not in {"ok", "clarification_needed", "unsupported"}:
            raise ResponseParseError(
                "The model response had an unknown status."
            )

        return {
            "status": status,
            "sql": str(data.get("sql") or "").strip().rstrip(";").strip(),
            "explanation": str(data.get("explanation") or "").strip(),
            "message": str(data.get("message") or "").strip(),
        }

    # Accept a plain SQL SELECT statement if the model did not return JSON.
    if re.match(r"(?is)^\s*select\b", text):
        return {
            "status": "ok",
            "sql": text.rstrip(";").strip(),
            "explanation": "",
            "message": "",
        }

    raise ResponseParseError(
        "The model response was not valid JSON or SQL."
    )


def _error(
    strategy: str,
    message: str,
    model: str = "",
    elapsed: float = 0.0,
) -> GenerationResult:
    return GenerationResult(
        "error", strategy, message=message,
        model=model, elapsed=elapsed,
    )


def generate_sql(
    question: str,
    strategy: str,
    settings: Settings | None = None,
    client: Any | None = None,
) -> GenerationResult:
    """Generate SQL using a local Ollama model."""
    settings = settings or load_settings()
    model = OLLAMA_MODEL

    if strategy not in STRATEGIES:
        return _error(strategy, f"Unknown prompt strategy '{strategy}'.")

    question = (question or "").strip()

    if not question:
        return _error(strategy, "Please type a question first.")

    if len(question) > MAX_QUESTION_LENGTH:
        return _error(
            strategy,
            f"Question is too long (max {MAX_QUESTION_LENGTH} characters).",
            model,
        )

    # Ollama's /api/chat endpoint accepts messages with role/content fields.
    payload: dict[str, Any] = {
        "model": model,
        "messages": build_messages(question, strategy),
        "stream": False,
        "options": {},
    }

    temperature = getattr(settings, "temperature", None)
    if temperature is not None:
        payload["options"]["temperature"] = temperature

    timeout = getattr(settings, "api_timeout", 120)
    start = time.perf_counter()

    try:
        if client is not None and hasattr(client, "post"):
            response = client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=timeout,
            )
        else:
            response = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=timeout,
            )

        response.raise_for_status()
        result_data = response.json()
        raw = result_data.get("message", {}).get("content", "")

    except requests.exceptions.ConnectionError:
        elapsed = time.perf_counter() - start
        return _error(
            strategy,
            "Cannot connect to Ollama. Make sure Ollama is running "
            "and the model qwen2.5-coder:3b is installed.",
            model,
            elapsed,
        )

    except requests.exceptions.Timeout:
        elapsed = time.perf_counter() - start
        return _error(
            strategy,
            "Ollama took too long to respond. Please try again.",
            model,
            elapsed,
        )

    except requests.exceptions.HTTPError as exc:
        elapsed = time.perf_counter() - start
        logger.warning("Ollama HTTP error: %s", exc)
        return _error(
            strategy,
            "Ollama returned an HTTP error. Check that the model is "
            "installed and Ollama is running.",
            model,
            elapsed,
        )

    except (requests.exceptions.RequestException, ValueError, AttributeError) as exc:
        elapsed = time.perf_counter() - start
        logger.warning("Ollama request failed: %s", type(exc).__name__)
        return _error(
            strategy,
            "Could not read Ollama's response. Check that Ollama is running.",
            model,
            elapsed,
        )

    elapsed = time.perf_counter() - start

    try:
        parsed = parse_model_response(raw)
    except ResponseParseError as exc:
        return _error(strategy, str(exc), model, elapsed)

    if parsed["status"] == "ok" and not parsed["sql"]:
        return _error(
            strategy,
            "The model said 'ok' but returned no SQL.",
            model,
            elapsed,
        )

    return GenerationResult(
        parsed["status"],
        strategy,
        parsed["sql"],
        parsed["explanation"],
        parsed["message"],
        model,
        elapsed,
    )
