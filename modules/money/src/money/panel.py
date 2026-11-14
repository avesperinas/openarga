from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from arga_widgets import panel
from money import analysis, kpis
from money.texts import amount, month, number, percent, t

HUES = [1, 2, 7, 6, 4, 3, 5, 8]
GROUP_HUES = {
    "Cash": 2,
    "Funds": 1,
    "Stocks": 6,
    "Pension": 5,
    "Crypto": 3,
    "Property": 4,
    "Deposits": 8,
}


def num(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


eur = amount


def months_text(value: float) -> str:
    rounded = round(value, 1)
    shown = number(rounded, 1).removesuffix(t("number.decimal") + "0")
    return t("panel.months_one" if rounded == 1 else "panel.months_other", value=shown)


def labelling(waiting: int) -> str:
    return t("panel.to_label_one") if waiting == 1 else t("panel.to_label_other", count=waiting)


def group_name(group: str) -> str:
    return t(f"group.{group}") if group in GROUP_HUES else group


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
                    "text": t("panel.margin", amount=eur(margin)),
                    "emphasis": t("panel.about", amount=eur(margin)),
                    "tone": "positive",
                    "status": t("panel.on_track"),
                    "priority": 55,
                }
            )
        else:
            headlines.append(
                {
                    "text": t("panel.over", amount=eur(-margin)),
                    "emphasis": t("panel.about", amount=eur(-margin)),
                    "tone": "warning",
                    "status": t("panel.watch"),
                    "priority": 70,
                }
            )
    elif networth and networth.value is not None:
        headlines.append(
            {
                "text": t("panel.you_have", amount=eur(num(networth.value))),
                "emphasis": eur(num(networth.value)),
                "status": t("panel.up_to_date"),
                "priority": 30,
            }
        )
    if waiting:
        headlines.append(
            {
                "text": labelling(waiting),
                "emphasis": str(waiting),
                "tone": "warning",
                "status": t("panel.to_label"),
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
                "label": t("panel.networth"),
                "value": eur(num(networth.value)),
                **(
                    {
                        "delta": t("panel.in_12_months", change=percent(change, sign=True)),
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
                "label": t("panel.networth_trend"),
                "points": points,
                "unit": "money",
            }
        )
    if entered > 0:
        parts = [
            {
                "label": t("panel.you_spend"),
                "value": eur(spent),
                "share": max(0.0, spent),
                "hue": 4,
            },
            {
                "label": t("panel.you_invest"),
                "value": eur(invested),
                "share": max(0.0, invested),
                "hue": 5,
            },
            {
                "label": t("panel.left") if left >= 0 else t("panel.from_savings"),
                "value": eur(left),
                "share": max(0.0, left),
                "hue": 2,
            },
        ]
        summary.append(
            {
                "type": "split",
                "label": t("panel.so_far", month=month(today.month).capitalize()),
                "total": t("panel.coming_in", amount=eur(entered)),
                "parts": parts,
            }
        )
    tiles: list[dict] = []
    if emergency and emergency.value is not None and emergency.target:
        monthly = num(emergency.target) / max(1, lo.settings.emergency_months)
        covered = num(emergency.value) / monthly if monthly else 0
        tiles.append(
            {
                "label": t("panel.cushion"),
                "value": months_text(covered),
                "foot": t(
                    "panel.cushion_foot",
                    months=lo.settings.emergency_months,
                    amount=eur(num(emergency.value)),
                ),
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
                "label": t("panel.you_save"),
                "value": percent(num(rate)),
                "foot": t("panel.of_income"),
                "tone": "positive" if num(rate) > 0 else "warning",
            }
        )
    if open_years:
        if abs(owed) < Decimal("0.005"):
            tiles.append(
                {
                    "label": t("panel.shared"),
                    "value": t("panel.even"),
                    "foot": t("panel.with", other=other),
                    "href": "/money/shared",
                }
            )
        else:
            tiles.append(
                {
                    "label": t("panel.owes_you", other=other)
                    if owed > 0
                    else t("panel.you_owe", other=other),
                    "value": eur(abs(num(owed))),
                    "foot": t("panel.settle"),
                    "tone": "neutral" if owed > 0 else "warning",
                    "href": "/money/shared",
                }
            )
    if liquid and liquid.value is not None:
        tiles.append(
            {
                "label": t("panel.liquid"),
                "value": eur(num(liquid.value)),
                "foot": t("panel.liquid_foot"),
            }
        )
    if tiles:
        summary.append({"type": "tiles", "items": tiles[:4]})
    if waiting:
        summary.append(
            {
                "type": "alert",
                "text": labelling(waiting),
                "href": "/money/movements?status=pending",
            }
        )

    spending_blocks: list[dict] = []
    if month_spent or average:
        spending_blocks.append(
            {
                "type": "figure",
                "label": t("panel.spent_in", month=month(today.month)),
                "value": eur(month_spent),
                **(
                    {
                        "delta": t("panel.ends_at", amount=eur(projected)),
                        "tone": "positive" if average and projected <= average else "warning",
                    }
                    if month_spent
                    else {}
                ),
                **({"foot": t("panel.average", amount=eur(average))} if average else {}),
            }
        )
    if rows:
        spending_blocks.append(
            {
                "type": "treemap",
                "label": t("panel.on_what"),
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
            spending_blocks.append(
                {
                    "type": "list",
                    "label": t("panel.against_average"),
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
        spending_blocks.append(
            {
                "type": "list",
                "label": t("panel.all_categories"),
                "rows": [
                    {"label": row["name"][:200], "value": eur(num(row["total"]))}
                    for row in rows[:12]
                ],
                "detail": True,
            }
        )

    worth_blocks: list[dict] = []
    if networth and networth.value is not None:
        worth_blocks.append(
            {
                "type": "figure",
                "label": t("panel.today"),
                "value": eur(num(networth.value)),
                "foot": t("panel.today_foot"),
            }
        )
    if len(points) >= 2:
        worth_blocks.append(
            {
                "type": "trend",
                "label": t("panel.networth_trend"),
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
            worth_blocks.append(
                {
                    "type": "split",
                    "label": t("panel.where"),
                    "parts": [
                        {
                            "label": group_name(group)[:60],
                            "value": eur(value),
                            "share": value,
                            "hue": GROUP_HUES.get(group, 8),
                        }
                        for group, value in groups[:8]
                    ],
                }
            )
    more = [
        {"label": t("panel.liquid"), "value": eur(num(liquid.value))}
        if liquid and liquid.value is not None
        else None,
        {
            "label": t("panel.cash"),
            "value": eur(num(cash.value)),
            "foot": t("panel.cash_foot"),
        }
        if cash and cash.value is not None
        else None,
    ]
    more = [one for one in more if one]
    if more:
        worth_blocks.append({"type": "tiles", "items": more})

    shared_blocks: list[dict] = []
    if open_years:
        if abs(owed) < Decimal("0.005"):
            shared_blocks.append(
                {
                    "type": "figure",
                    "label": t("panel.with_title", other=other),
                    "value": t("panel.you_are_even"),
                }
            )
        else:
            shared_blocks.append(
                {
                    "type": "figure",
                    "label": t("panel.to_settle"),
                    "value": eur(abs(num(owed))),
                    "foot": t("panel.owes_you", other=other)
                    if owed > 0
                    else t("panel.you_owe", other=other),
                }
            )
        shared_blocks.append(
            {
                "type": "list",
                "rows": [
                    {"label": f"{year}", "value": t("panel.unsettled")} for year in open_years
                ],
            }
        )

    tabs = [
        {
            "id": "summary",
            "label": t("panel.tab_summary"),
            "blocks": summary,
            "actions": [
                *(
                    [
                        {
                            "label": t("panel.label"),
                            "href": "/money/movements?status=pending",
                            "primary": True,
                        }
                    ]
                    if waiting
                    else []
                ),
                {"label": t("panel.open"), "href": "/money/"},
            ],
        },
        {
            "id": "spending",
            "label": t("panel.tab_spending"),
            "blocks": spending_blocks,
            "actions": [{"label": t("panel.see_movements"), "href": "/money/movements"}],
        },
        {
            "id": "worth",
            "label": t("panel.tab_worth"),
            "blocks": worth_blocks,
            "actions": [{"label": t("panel.analysis"), "href": "/money/analysis"}],
        },
    ]
    if shared_blocks:
        tabs.append(
            {
                "id": "shared",
                "label": t("panel.tab_shared"),
                "blocks": shared_blocks,
                "actions": [{"label": t("panel.settle"), "href": "/money/shared", "primary": True}],
            }
        )

    def question(name: str, tab: str, block: int) -> dict:
        return {
            "text": t(f"panel.q_{name}"),
            "words": t(f"panel.w_{name}").split(","),
            "tab": tab,
            "block": block,
        }

    questions = [
        question("have", "summary", 0),
        question("month", "spending", 0),
        question("where", "spending", 1 if rows else 0),
        question("cushion", "summary", max(0, len(summary) - (2 if waiting else 1))),
    ]
    if shared_blocks:
        questions.append(question("owes", "shared", 0))
    return panel("money", order=10, headlines=headlines, tabs=tabs, questions=questions)
