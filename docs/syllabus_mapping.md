# Syllabus mapping
> **Important:** the assignment did not include the official module titles of 24CS2022. The six rows below use the
> standard topics of a Prompt Engineering course. **Replace the "Module" column with the exact titles from your
> syllabus** before submission; the "Where implemented" column stays valid.

| # | Typical module topic | Where implemented in this project |
|---|---|---|
| 1 | Foundations of LLMs and prompting (tokens, context, temperature, roles) | `sql_generator.py` (system/user roles, temperature, timeout); token estimate in the Prompt comparison tab |
| 2 | Basic prompting techniques (zero-shot, few-shot) | `prompt_templates.py` strategies A and B; `FEW_SHOT_EXAMPLES` |
| 3 | Structured and schema-aware prompting, output formats | Strategy C (`schema_detailed`, ambiguity rules); JSON output contract; `parse_model_response` |
| 4 | Prompt safety, hallucination and reliability | Refusal/clarification statuses; `sql_validator.py`; read-only execution; hallucinated tables/columns rejected |
| 5 | Evaluation and optimisation of prompts | `evaluator.py` metrics, 34-question benchmark, strategy comparison, offline vs live runs |
| 6 | Applications and tool integration (LLM + database/UI, RAG as extension) | `database.py`, `app.py`; RAG discussed as a future extension for large schemas |
