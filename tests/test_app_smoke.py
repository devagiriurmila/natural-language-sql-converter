"""Headless UI smoke tests using Streamlit's AppTest (no browser, no API)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import sql_generator
from sql_generator import GenerationResult

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def test_app_starts_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    at.text_area[0].set_value("Show all students").run()
    _button(at, "Generate SQL").click().run()
    assert any("OPENAI_API_KEY" in e.value for e in at.error)


@pytest.mark.parametrize("sql,executable", [
    ("SELECT name FROM students WHERE department = 'CSE'", True),
    ("DROP TABLE students", False),
])
def test_generate_validate_execute_flow(monkeypatch, sql, executable):
    monkeypatch.setattr(sql_generator, "generate_sql",
                        lambda q, s, settings=None, client=None: GenerationResult("ok", s, sql, "demo", model="mock"))
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_area[0].set_value("anything").run()
    _button(at, "Generate SQL").click().run()
    assert not at.exception
    run_btn = _button(at, "Execute query")
    assert run_btn.disabled == (not executable)
    if executable:
        run_btn.click().run()
        assert len(at.dataframe) >= 1
