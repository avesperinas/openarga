from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from arga_widgets import panel
from money import analysis, kpis

HUES = [1, 2, 7, 6, 4, 3, 5, 8]
GROUP_HUES = {
    "Efectivo": 2,
    "Fondos": 1,
    "Bolsa": 6,
    "Pensión": 5,
    "Cripto": 3,
    "Vivienda": 4,
    "Fianzas": 8,
}


def num(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def eur(value: float, sign: bool = False) -> str:
    whole = round(value)
    text = f"{abs(whole):,}".replace(",", ".") + " €"
    if whole < 0:
        return f"−{text}"
    return f"+{text}" if sign and whole > 0 else text


def percent(value: float, sign: bool = False) -> str:
    whole = round(value * 100)
    text = f"{abs(whole)} %"
    if whole < 0:
        return f"−{text}"
    return f"+{text}" if sign and whole > 0 else text


def months_text(value: float) -> str:
    rounded = round(value, 1)
    shown = f"{rounded:.1f}".replace(".", ",").replace(",0", "")
    return f"{shown} {'mes' if rounded == 1 else 'meses'}"


def labelling(waiting: int) -> str:
    return f"{waiting} {'movimiento' if waiting == 1 else 'movimientos'} por etiquetar"


def build(
    lo: Any, today: date, owed: Decimal, other: str, open_years: list[int], waiting: int
) -> dict:
    found = {k.key: k for k in kpis.compute(lo, today)}
    networth = found.get("networth")
    expense = found.get("expense")
    emergency = found.get("emergency")
    liquid = found.get("liquid")
    cash = found.get("cash")

    worth = analysis.worth(
        lo, analysis.shift_months(today.replace(day=1), -11), today, False, False, today
    )
    points = [{"label": p["label"], "value": num(p["total"])} for p in worth.get("points", [])]

    month_start = today.replace(day=1)
    flow = analysis.flow(lo, month_start, today, False, False, today, compare=False)
    totals = {
        key: num(value) for key, value in (flow.get("totals") or {}).items() if value is not None
    }
    entered = totals.get("income", 0.0) + totals.get("member", 0.0)
    spent = totals.get("spent", 0.0) + totals.get("common", 0.0)
    invested = totals.get("invested", 0.0)
    left = totals.get("left", 0.0)
    rate = flow.get("totals", {}).get("rate")

    spending = analysis.spending(lo, month_start, today, "all", False, "all", today)
    month_spent = num(spending.get("total"))
    rows = [row for row in spending.get("rows", []) if num(row.get("total")) > 0]
    rows.sort(key=lambda row: num(row["total"]), reverse=True)

    days = calendar.monthrange(today.year, today.month)[1]
    average = num(expense.value) if expense and expense.value is not None else None
    projected = month_spent / today.day * days if today.day else month_spent

    headlines: list[dict] = []
    if average and month_spent:
        margin = average - projected
        if margin >= 0:
            headlines.append(
                {
                    "text": f"Llegas a fin de mes con unos {eur(margin)} de margen",
                    "emphasis": f"unos {eur(margin)}",
                    "tone": "positive",
                    "status": "Vas bien",
                    "priority": 55,
                }
            )
        else:
            headlines.append(
                {
                    "text": f"Al ritmo de este mes te pasas unos {eur(-margin)} de tu media",
                    "emphasis": f"unos {eur(-margin)}",
                    "tone": "warning",
                    "status": "Ojo al gasto",
                    "priority": 70,
                }
            )
    elif networth and networth.value is not None:
        headlines.append(
            {
                "text": f"Tienes {eur(num(networth.value))}",
                "emphasis": eur(num(networth.value)),
                "status": "Al día",
                "priority": 30,
            }
        )
    if waiting:
        headlines.append(
            {
                "text": labelling(waiting),
                "emphasis": str(waiting),
                "tone": "warning",
                "status": "Por etiquetar",
                "priority": 40,
            }
        )

    summary: list[dict] = []
    if networth and networth.value is not None:
        change = None
        if networth.previous:
            change = num(networth.value) / num(networth.previous) - 1
        summary.append(
            {
                "type": "figure",
                "label": "Patrimonio",
                "value": eur(num(networth.value)),
                **(
                    {
                        "delta": f"{percent(change, sign=True)} en 12 meses",
                        "tone": "positive" if change >= 0 else "warning",
                    }
                    if change is not None
                    else {}
                ),
            }
        )
    if len(points) >= 2:
        summary.append(
            {
                "type": "trend",
                "label": "Patrimonio a final de cada mes",
                "points": points,
                "unit": "money",
            }
        )
    if entered > 0:
        parts = [
            {"label": "Gastas", "value": eur(spent), "share": max(0.0, spent), "hue": 4},
            {"label": "Inviertes", "value": eur(invested), "share": max(0.0, invested), "hue": 5},
            {
                "label": "Queda" if left >= 0 else "Tiras de ahorros",
                "value": eur(left),
                "share": max(0.0, left),
                "hue": 2,
            },
        ]
        summary.append(
            {
                "type": "split",
                "label": f"{MONTHS[today.month - 1].capitalize()}, hasta hoy",
                "total": f"entran {eur(entered)}",
                "parts": parts,
            }
        )
    tiles: list[dict] = []
    if emergency and emergency.value is not None and emergency.target:
        monthly = num(emergency.target) / max(1, lo.settings.emergency_months)
        covered = num(emergency.value) / monthly if monthly else 0
        tiles.append(
            {
                "label": "Colchón",
                "value": months_text(covered),
                "foot": f"de {lo.settings.emergency_months} · {eur(num(emergency.value))}",
                "tone": "positive"
                if covered >= lo.settings.emergency_months
                else "warning"
                if covered < lo.settings.emergency_months / 2
                else "neutral",
            }
        )
    if rate is not None and entered > 0:
        tiles.append(
            {
                "label": "Ahorras",
                "value": percent(num(rate)),
                "foot": "de lo que entra este mes",
                "tone": "positive" if num(rate) > 0 else "warning",
            }
        )
    if open_years:
        if abs(owed) < Decimal("0.005"):
            tiles.append(
                {
                    "label": "Lo común",
                    "value": "a cero",
                    "foot": f"con {other}",
                    "href": "/money/compartido",
                }
            )
        else:
            tiles.append(
                {
                    "label": f"{other} te debe" if owed > 0 else f"Debes a {other}",
                    "value": eur(abs(num(owed))),
                    "foot": "Liquidar",
                    "tone": "neutral" if owed > 0 else "warning",
                    "href": "/money/compartido",
                }
            )
    if liquid and liquid.value is not None:
        tiles.append(
            {"label": "Líquido", "value": eur(num(liquid.value)), "foot": "lo que puedes sacar ya"}
        )
    if tiles:
        summary.append({"type": "tiles", "items": tiles[:4]})
    if waiting:
        summary.append(
            {
                "type": "alert",
                "text": labelling(waiting),
                "href": "/money/movimientos?estado=pendiente",
            }
        )

    gasto: list[dict] = []
    if month_spent or average:
        gasto.append(
            {
                "type": "figure",
                "label": f"Gastado en {MONTHS[today.month - 1]}",
                "value": eur(month_spent),
                **(
                    {
                        "delta": f"acabas en {eur(projected)}",
                        "tone": "positive" if average and projected <= average else "warning",
                    }
                    if month_spent
                    else {}
                ),
                **({"foot": f"Tu media, {eur(average)} al mes"} if average else {}),
            }
        )
    if rows:
        gasto.append(
            {
                "type": "treemap",
                "label": "En qué",
                "items": [
                    {
                        "label": row["name"][:60],
                        "value": round(num(row["total"]), 2),
                        "hue": HUES[i % len(HUES)],
                    }
                    for i, row in enumerate(rows[:8])
                ],
            }
        )
        off = [row for row in rows if row.get("average") is not None and num(row["average"]) > 0]
        off.sort(key=lambda row: num(row["total"]) - num(row["average"]), reverse=True)
        if off:
            gasto.append(
                {
                    "type": "list",
                    "label": "Contra su media",
                    "rows": [
                        {
                            "label": row["name"][:200],
                            "value": eur(num(row["total"]) - num(row["average"]), sign=True),
                            "tone": "warning"
                            if num(row["total"]) > num(row["average"])
                            else "positive",
                        }
                        for row in off[:4]
                    ],
                }
            )
        gasto.append(
            {
                "type": "list",
                "label": "Todas las categorías",
                "rows": [
                    {"label": row["name"][:200], "value": eur(num(row["total"]))}
                    for row in rows[:12]
                ],
                "detail": True,
            }
        )

    patrimonio: list[dict] = []
    if networth and networth.value is not None:
        patrimonio.append(
            {
                "type": "figure",
                "label": "Hoy",
                "value": eur(num(networth.value)),
                "foot": "Sin la vivienda; las cuentas comunes, por tu parte",
            }
        )
    if len(points) >= 2:
        patrimonio.append(
            {
                "type": "trend",
                "label": "Patrimonio a final de cada mes",
                "points": points,
                "unit": "money",
            }
        )
    last = worth.get("points", [])[-1] if worth.get("points") else None
    if last:
        groups = [(group, num(last["by_group"].get(group, 0))) for group in worth.get("groups", [])]
        groups = [(group, value) for group, value in groups if value > 0]
        groups.sort(key=lambda one: one[1], reverse=True)
        if groups:
            patrimonio.append(
                {
                    "type": "split",
                    "label": "Dónde está",
                    "parts": [
                        {
                            "label": group[:60],
                            "value": eur(value),
                            "share": value,
                            "hue": GROUP_HUES.get(group, 8),
                        }
                        for group, value in groups[:8]
                    ],
                }
            )
    more = [
        {"label": "Líquido", "value": eur(num(liquid.value))}
        if liquid and liquid.value is not None
        else None,
        {"label": "Cash", "value": eur(num(cash.value)), "foot": "en cuentas, sin el colchón"}
        if cash and cash.value is not None
        else None,
    ]
    more = [one for one in more if one]
    if more:
        patrimonio.append({"type": "tiles", "items": more})

    comun: list[dict] = []
    if open_years:
        if abs(owed) < Decimal("0.005"):
            comun.append({"type": "figure", "label": f"Con {other}", "value": "Estáis a cero"})
        else:
            comun.append(
                {
                    "type": "figure",
                    "label": "Lo común por saldar",
                    "value": eur(abs(num(owed))),
                    "foot": f"{other} te debe" if owed > 0 else f"Debes a {other}",
                }
            )
        comun.append(
            {
                "type": "list",
                "rows": [{"label": f"{year}", "value": "sin liquidar"} for year in open_years],
            }
        )

    tabs = [
        {
            "id": "resumen",
            "label": "Resumen",
            "blocks": summary,
            "actions": [
                *(
                    [
                        {
                            "label": "Etiquetar",
                            "href": "/money/movimientos?estado=pendiente",
                            "primary": True,
                        }
                    ]
                    if waiting
                    else []
                ),
                {"label": "Abrir Money", "href": "/money/"},
            ],
        },
        {
            "id": "gasto",
            "label": "Gasto",
            "blocks": gasto,
            "actions": [{"label": "Ver movimientos", "href": "/money/movimientos"}],
        },
        {
            "id": "patrimonio",
            "label": "Patrimonio",
            "blocks": patrimonio,
            "actions": [{"label": "Análisis", "href": "/money/analisis"}],
        },
    ]
    if comun:
        tabs.append(
            {
                "id": "comun",
                "label": "Común",
                "blocks": comun,
                "actions": [{"label": "Liquidar", "href": "/money/compartido", "primary": True}],
            }
        )

    questions = [
        {
            "text": "¿Cuánto tengo?",
            "words": ["patrimonio", "cuanto tengo", "dinero", "ahorros"],
            "tab": "resumen",
            "block": 0,
        },
        {
            "text": "¿Llego a fin de mes?",
            "words": ["fin de mes", "llego", "gasto del mes", "presupuesto"],
            "tab": "gasto",
            "block": 0,
        },
        {
            "text": "¿En qué se me va el dinero?",
            "words": ["gasto", "gastos", "categorias", "en que gasto"],
            "tab": "gasto",
            "block": 1 if rows else 0,
        },
        {
            "text": "¿Cuánto colchón tengo?",
            "words": ["colchon", "fondo de emergencia", "contingencia", "ahorro"],
            "tab": "resumen",
            "block": max(0, len(summary) - (2 if waiting else 1)),
        },
    ]
    if comun:
        questions.append(
            {
                "text": "¿Quién debe a quién?",
                "words": ["debe", "deuda", "comun", "compartido", "liquidar"],
                "tab": "comun",
                "block": 0,
            }
        )
    return panel("money", order=10, headlines=headlines, tabs=tabs, questions=questions)


MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
