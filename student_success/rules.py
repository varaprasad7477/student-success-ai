from __future__ import annotations

import math


OPERATORS = {
    "lt": lambda actual, expected: actual < expected,
    "lte": lambda actual, expected: actual <= expected,
    "gt": lambda actual, expected: actual > expected,
    "gte": lambda actual, expected: actual >= expected,
    "eq": lambda actual, expected: actual == expected,
}


def evaluate_rules(row: dict, rules: list[dict]) -> list[dict]:
    triggered = []
    for rule in rules:
        field = rule.get("field")
        actual = row.get(field)
        if actual is None or (isinstance(actual, float) and math.isnan(actual)):
            continue
        operator = rule.get("operator")
        if operator not in OPERATORS:
            raise ValueError(f"Unsupported rule operator: {operator}")
        if OPERATORS[operator](actual, rule.get("value")):
            triggered.append({
                "id": rule.get("id", "unnamed-rule"),
                "severity": rule.get("severity", "medium"),
                "message": rule.get("message", f"{field} triggered a policy rule."),
                "field": field,
                "actual": actual,
                "threshold": rule.get("value"),
            })
    return triggered

