"""Layered validation of untrusted, model-generated SQL.

Layers (all must pass):
 1. Reject empty input and SQL comments.
 2. Parse with sqlglot using the SQLite dialect (syntax check).
 3. Require exactly ONE statement.
 4. Require that statement to be a plain SELECT (no INSERT/UPDATE/DELETE/DDL/
    PRAGMA/ATTACH/transactions; no CTEs or UNION - unsupported on purpose).
 5. Check every table and column against the permitted schema.
 6. Reject unknown functions (e.g. load_extension, randomblob).
 7. Force a maximum LIMIT.
database.py adds further layers (read-only connection, authorizer, timeout).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.tokens import Tokenizer

from config import TABLE_COLUMNS

MAX_SQL_LENGTH = 3000
# Functions that are allowed when sqlglot cannot map them to a known aggregate.
ALLOWED_ANONYMOUS_FUNCTIONS = {
    "ROUND", "LENGTH", "ABS", "IFNULL", "COALESCE", "SUBSTR", "UPPER", "LOWER", "TRIM",
}
# Functions that must never appear, whatever sqlglot calls them.
BLOCKED_FUNCTION_NAMES = {"LOAD_EXTENSION", "RANDOMBLOB", "ZEROBLOB", "READFILE", "WRITEFILE"}


@dataclass
class ValidationResult:
    is_valid: bool
    original_sql: str
    sql: str = ""  # normalised SQL (with LIMIT enforced); only trust it if is_valid
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _fail(original: str, *errors: str) -> ValidationResult:
    return ValidationResult(False, original, "", list(errors))


def validate_sql(sql: str | None, max_rows: int = 100,
                 schema: dict[str, set[str]] | None = None) -> ValidationResult:
    """Validate ``sql``; never raises - always returns a ValidationResult."""
    schema = schema or TABLE_COLUMNS
    original = sql if isinstance(sql, str) else ""
    text = original.strip()
    if not text:
        return _fail(original, "The SQL query is empty.")
    if len(text) > MAX_SQL_LENGTH:
        return _fail(original, "The SQL query is too long.")

    # Layer 1: comments can hide payloads, so they are rejected outright.
    try:
        tokens = Tokenizer().tokenize(text)
    except Exception:
        return _fail(original, "The SQL could not be tokenised (invalid syntax).")
    if any(tok.comments for tok in tokens) or "--" in text or "/*" in text:
        return _fail(original, "SQL comments are not allowed.")

    # Layers 2-3: parse in the SQLite dialect and require exactly one statement.
    try:
        statements = [s for s in sqlglot.parse(text, read="sqlite") if s is not None]
    except SqlglotError:
        return _fail(original, "Invalid SQL syntax for SQLite.")
    except Exception:
        return _fail(original, "The SQL could not be parsed.")
    if not statements:
        return _fail(original, "No SQL statement found.")
    if len(statements) > 1:
        return _fail(original, "Multiple SQL statements are not allowed.")
    tree = statements[0]

    # Layer 4: only a plain SELECT is permitted.
    if not isinstance(tree, exp.Select):
        kind = type(tree).__name__.upper()
        return _fail(original, f"Only a single read-only SELECT query is allowed (found {kind}).")
    for banned, label in ((exp.With, "WITH/CTE"), (exp.Union, "UNION/INTERSECT/EXCEPT"),
                          (exp.Into, "SELECT INTO")):
        if tree.find(banned):
            return _fail(original, f"{label} is not supported by this application.")
    forbidden_nodes = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
                       exp.Command, exp.Pragma, exp.Attach, exp.Detach, exp.Transaction,
                       exp.Commit, exp.Rollback)
    if tree.find(*forbidden_nodes):
        return _fail(original, "Data-changing or administrative statements are not allowed.")

    errors: list[str] = []

    # Layer 5a: tables.
    alias_to_table: dict[str, str] = {}
    referenced_tables: set[str] = set()
    for table in tree.find_all(exp.Table):
        name = table.name
        if table.args.get("db") or table.args.get("catalog"):
            errors.append("Schema-qualified table names are not allowed.")
            continue
        if not isinstance(table.this, exp.Identifier) or name.lower() not in schema:
            errors.append(f"Unknown table: '{name}'.")
            continue
        referenced_tables.add(name.lower())
        alias_to_table[(table.alias_or_name or name).lower()] = name.lower()
    if not referenced_tables and not errors:
        errors.append("The query must read from at least one known table.")

    # Layer 5b: columns.
    select_aliases = {a.alias.lower() for a in tree.find_all(exp.Alias) if a.alias}
    derived_aliases = {s.alias.lower() for s in tree.find_all(exp.Subquery) if s.alias}
    visible = set().union(*(schema[t] for t in referenced_tables)) if referenced_tables else set()
    for col in tree.find_all(exp.Column):
        if isinstance(col.this, exp.Star):  # students.*
            continue
        cname, qualifier = col.name.lower(), col.table.lower()
        if qualifier:
            if qualifier in alias_to_table:
                if cname not in schema[alias_to_table[qualifier]]:
                    errors.append(f"Unknown column: '{col.table}.{col.name}'.")
            elif qualifier not in derived_aliases:
                errors.append(f"Unknown table alias: '{col.table}'.")
        elif cname not in visible and cname not in select_aliases:
            errors.append(f"Unknown column: '{col.name}'.")

    # Layer 6: functions.
    for func in tree.find_all(exp.Func):
        if isinstance(func, exp.Anonymous):
            fname = str(func.name).upper()
            if fname in BLOCKED_FUNCTION_NAMES or fname not in ALLOWED_ANONYMOUS_FUNCTIONS:
                errors.append(f"Function not allowed: '{func.name}'.")
    if errors:
        return _fail(original, *dict.fromkeys(errors))  # de-duplicate, keep order

    # Layer 7: enforce a row limit.
    warnings: list[str] = []
    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(max_rows)
        warnings.append(f"No LIMIT found, so LIMIT {max_rows} was added.")
    else:
        value = limit.expression
        if isinstance(value, exp.Literal) and value.is_int:
            if int(value.name) > max_rows:
                tree = tree.limit(max_rows)
                warnings.append(f"LIMIT reduced to the maximum of {max_rows} rows.")
        else:
            return _fail(original, "LIMIT must be a plain integer.")

    return ValidationResult(True, original, tree.sql(dialect="sqlite"), [], warnings)
