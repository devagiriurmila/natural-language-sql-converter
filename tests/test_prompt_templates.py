import pytest

from config import SCHEMA
from prompt_templates import (FEW_SHOT, SCHEMA_AWARE, STRATEGIES, ZERO_SHOT, build_messages,
                              build_system_prompt)


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_has_schema_and_safety_rules(strategy):
    p = build_system_prompt(strategy)
    for table in SCHEMA:
        assert table in p
    for phrase in ("SQLite", "ONE read-only SELECT", "clarification_needed", "unsupported", "JSON"):
        assert phrase in p


def test_zero_shot_has_no_examples():
    assert "EXAMPLES:" not in build_system_prompt(ZERO_SHOT)


def test_few_shot_has_examples():
    p = build_system_prompt(FEW_SHOT)
    assert "EXAMPLES:" in p and p.count("Question:") >= 4


def test_schema_aware_has_descriptions_and_ambiguity_rules():
    p = build_system_prompt(SCHEMA_AWARE)
    assert "references" in p and "AMBIGUITY RULES" in p and "Value hints" in p


def test_no_chain_of_thought_request():
    for s in STRATEGIES:
        assert "step by step" not in build_system_prompt(s).lower()


def test_messages_structure():
    m = build_messages("  Show all students  ", ZERO_SHOT)
    assert [x["role"] for x in m] == ["system", "user"]
    assert m[1]["content"] == "Question: Show all students"


def test_unknown_strategy():
    with pytest.raises(ValueError):
        build_system_prompt("bogus")


def test_few_shot_examples_not_in_benchmark():
    from evaluator import BENCHMARK
    from prompt_templates import FEW_SHOT_EXAMPLES
    bench = {b["question"].lower() for b in BENCHMARK}
    assert not any(q.lower() in bench for q, _, _ in FEW_SHOT_EXAMPLES)
