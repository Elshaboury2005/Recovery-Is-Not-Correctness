"""Strict lexical allow-list for pipeline filter expressions."""

from __future__ import annotations

import re

_TOKEN = re.compile(
    r"\s*(?:(?P<string>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")|"
    r"(?P<number>\d+(?:\.\d+)?)|(?P<operator>==|!=|>=|<=|>|<|=)|"
    r"(?P<paren>[()])|(?P<identifier>[A-Za-z_][A-Za-z0-9_]*))"
)
_KEYWORDS = {"and", "or", "not", "in", "is", "null", "true", "false"}


def validate_filter_condition(condition: str) -> None:
    """Accept only identifiers, comparisons, boolean operators and literals."""
    if not isinstance(condition, str) or not condition.strip():
        raise ValueError("Filter condition must be a non-empty expression.")
    condition = condition.strip()
    position = 0
    has_comparison = False
    while position < len(condition):
        match = _TOKEN.match(condition, position)
        if match is None:
            if "__" in condition[position:]:
                raise ValueError("Filter condition contains disallowed dunder names (__).")
            raise ValueError(
                "Filter condition contains an unsupported token; calls and attribute access are not allowed."
            )
        position = match.end()
        identifier = match.group("identifier")
        if identifier and identifier.startswith("__"):
            raise ValueError("Filter condition cannot reference dunder names.")
        has_comparison |= match.group("operator") is not None or (identifier or '').lower() in {"is", "in"}
    if not has_comparison:
        raise ValueError("Filter condition must contain a comparison.")


def pandas_filter_condition(condition: str) -> str:
    """Translate only lexed SQL equality/boolean tokens; never edit literals."""
    validate_filter_condition(condition)
    parts=[]
    for match in _TOKEN.finditer(condition.strip()):
        token=match.group(0).strip()
        if match.group('operator') == '=': token='=='
        if (match.group('identifier') or '').lower() in {'and','or','not'}: token=token.lower()
        parts.append(token)
    return ' '.join(parts)
