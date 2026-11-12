from __future__ import annotations

from typing import Any


def insight(**overrides: Any) -> dict[str, Any]:
    return {
        "kind": "alert",
        "domain": "money",
        "topic": "money.gasto:restaurantes",
        "title": "Restaurantes, un 60 % por encima de lo tuyo",
        "body": "Llevas 412 € en restaurantes este mes, frente a 258 € de media.",
        "figures": [
            {
                "label": "gasto en restaurantes este mes",
                "value": 412,
                "unit": "€",
                "baseline": 258,
                "baseline_label": "tu media de 12 meses",
            }
        ],
        "affects": "el colchón de 6 meses que te pusiste para diciembre",
        "action": "Dos cenas fuera menos hasta fin de mes: unos 90 € de vuelta al colchón.",
    } | overrides


def proposal(number: int = 1) -> dict[str, Any]:
    return {
        "what": f"Tres cenas en casa de lunes a jueves (propuesta {number})",
        "figure": {
            "label": "cenas fuera esta semana",
            "value": 4,
            "baseline": 2,
            "baseline_label": "tu media de 8 semanas",
        },
        "how": "Shopping: añadir a la lista lo de tres cenas",
    }


def weekly(count: int = 3, **overrides: Any) -> dict[str, Any]:
    return (
        insight(
            kind="weekly",
            domain="cross",
            topic="semana:2026-w42",
            proposals=[proposal(number) for number in range(1, count + 1)],
        )
        | overrides
    )
