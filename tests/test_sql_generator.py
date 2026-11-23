import json
from types import SimpleNamespace

import openai
import pytest

try:  # the openai SDK ships with whichever HTTP client it needs
    import httpx2 as httpx
except ImportError:  # older SDK versions
    import httpx
from config import Settings
from sql_generator import ResponseParseError, generate_sql, parse_model_response


def settings(key="sk-test"):
    return Settings(key, "test-model", 0.0, 5.0, None, 100, 5.0)  # type: ignore[arg-type]


class FakeClient:
    def __init__(self, content=None, exc=None):
        self.content, self.exc, self.calls = content, exc, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        if self.exc:
            raise self.exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def ok_json(sql="SELECT * FROM students"):
    return json.dumps({"status": "ok", "sql": sql, "explanation": "All students.", "message": ""})


def test_success():
    c = FakeClient(ok_json())
    r = generate_sql("Show all students", "zero_shot", settings(), c)
    assert r.ok and r.sql == "SELECT * FROM students" and c.calls == 1


def test_markdown_fenced_json():
    r = generate_sql("q", "few_shot", settings(), FakeClient("```json\n" + ok_json() + "\n```"))
    assert r.ok


def test_fenced_plain_sql_and_trailing_semicolon():
    p = parse_model_response("```sql\nSELECT * FROM students;\n```")
    assert p["sql"] == "SELECT * FROM students"


def test_json_with_chatter():
    assert parse_model_response("Sure! " + ok_json() + " Hope it helps")["status"] == "ok"


@pytest.mark.parametrize("raw", ["", "   ", None, "I cannot help with that.", "{bad json", '{"status":"weird"}'])
def test_malformed_responses(raw):
    with pytest.raises(ResponseParseError):
        parse_model_response(raw)
    r = generate_sql("q", "zero_shot", settings(), FakeClient(raw))
    assert r.status == "error" and not r.ok


def test_clarification_is_not_ok():
    raw = json.dumps({"status": "clarification_needed", "sql": "", "message": "Which department?"})
    r = generate_sql("q", "schema_aware", settings(), FakeClient(raw))
    assert r.status == "clarification_needed" and not r.ok and "department" in r.message


def test_ok_without_sql_is_error():
    r = generate_sql("q", "zero_shot", settings(), FakeClient(json.dumps({"status": "ok", "sql": ""})))
    assert r.status == "error"


def test_missing_api_key_makes_no_call():
    r = generate_sql("q", "zero_shot", settings(key=None))
    assert r.status == "error" and "OPENAI_API_KEY" in r.message
    assert not settings(key="your-api-key-here").api_configured


def test_empty_and_long_questions_and_bad_strategy():
    assert generate_sql("  ", "zero_shot", settings(), FakeClient(ok_json())).status == "error"
    assert generate_sql("x" * 600, "zero_shot", settings(), FakeClient(ok_json())).status == "error"
    assert generate_sql("q", "nope", settings(), FakeClient(ok_json())).status == "error"


def _req():
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


@pytest.mark.parametrize("exc,word", [
    (openai.AuthenticationError("x", response=httpx.Response(401, request=_req()), body=None), "rejected"),
    (openai.RateLimitError("x", response=httpx.Response(429, request=_req()), body=None), "quota"),
    (openai.NotFoundError("x", response=httpx.Response(404, request=_req()), body=None), "not found"),
    (openai.APIConnectionError(request=_req()), "internet"),
    (openai.APITimeoutError(request=_req()), "timed out"),
])
def test_api_errors_give_friendly_messages(exc, word):
    r = generate_sql("q", "zero_shot", settings(), FakeClient(exc=exc))
    assert r.status == "error" and word in r.message.lower()
    assert "sk-test" not in r.message


def test_unexpected_shape():
    bad = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: SimpleNamespace(choices=[]))))
    assert generate_sql("q", "zero_shot", settings(), bad).status == "error"
