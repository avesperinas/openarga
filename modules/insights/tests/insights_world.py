from __future__ import annotations

from typing import Any


def insight(**overrides: Any) -> dict[str, Any]:
    return {
        "kind": "alert",
        "domain": "money",
        "topic": "money.spend:restaurants",
        "title": "Restaurants, 60 % above your usual",
        "body": "You have spent 412 € on restaurants this month, against 258 € on average.",
        "figures": [
            {
                "label": "restaurant spending this month",
                "value": 412,
                "unit": "€",
                "baseline": 258,
                "baseline_label": "your 12-month average",
            }
        ],
        "affects": "the 6-month cushion you set for December",
        "action": "Two fewer dinners out until the end of the month: about 90 € back to savings.",
    } | overrides


def proposal(number: int = 1) -> dict[str, Any]:
    return {
        "what": f"Three dinners at home from Monday to Thursday (proposal {number})",
        "figure": {
            "label": "dinners out this week",
            "value": 4,
            "baseline": 2,
            "baseline_label": "your 8-week average",
        },
        "how": "Shopping: add three dinners to the list",
    }


def weekly(count: int = 3, **overrides: Any) -> dict[str, Any]:
    return (
        insight(
            kind="weekly",
            domain="cross",
            topic="week:2026-w42",
            proposals=[proposal(number) for number in range(1, count + 1)],
        )
        | overrides
    )
