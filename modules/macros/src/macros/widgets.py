from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from macros import catalog, meals, summary
from macros import goals as ranges
from macros.catalog import t
from macros.common import now, today


def _n(value: float) -> str:
    return catalog.number(value)


async def for_today(connection: AsyncConnection) -> dict:
    found = await summary.day(connection, today())
    kcal = found.nutrients.get("kcal", 0.0)
    protein = found.nutrients.get("protein")
    detail = t("widget.protein", value=_n(protein)) if protein is not None else None
    goal = found.target.kcal if found.target else None
    if not found.entries:
        return envelope("ring", "empty", {"detail": t("widget.nothing_today")})
    if not goal:
        return envelope("ring", "empty", {"detail": t("widget.set_goal", kcal=_n(kcal))})
    body = {"value": round(kcal), "target": round(goal), "unit": "kcal", "show": "value"}
    if detail:
        body["detail"] = detail
    if found.target and found.target.protein:
        body["label"] = t(
            "widget.protein_of", value=_n(protein or 0), target=_n(found.target.protein)
        )
    return envelope("ring", "ready", body)


async def macros_today(connection: AsyncConnection) -> dict:
    found = await summary.day(connection, today())
    if not found.entries:
        return envelope("stats", "empty", {"detail": t("widget.nothing_today")})
    labels = [(key, catalog.nutrient(key)) for key in ("protein", "carbs", "fat")]
    return envelope(
        "stats",
        "ready",
        {
            "stats": [
                {"label": label, "value": round(found.nutrients.get(key, 0.0)), "unit": "g"}
                for key, label in labels
            ]
        },
    )


async def week_short(connection: AsyncConnection) -> dict:
    found = await summary.week(connection, today())
    if not found.days_logged:
        return envelope("list", "empty", {"detail": t("widget.nothing_week")})
    if all(micro.value is None for micro in found.micros):
        return envelope("list", "empty", {"detail": t("widget.no_micros")})
    low = [micro for micro in found.micros if micro.status == "low"]
    if not low:
        return envelope("list", "empty", {"detail": t("widget.all_front")})
    rows = []
    for micro in low:
        assert micro.value is not None
        floor = micro.goal.low if micro.goal is not None else None
        if floor is None and micro.reference is not None and micro.reference.kind == "min":
            floor = micro.reference.value
        share = round(micro.value / floor * 100) if floor else 0
        rows.append(
            {
                "label": micro.name,
                "value": f"{share} %" + (f" · {t('widget.data_missing')}" if micro.partial else ""),
                "tone": "neutral" if micro.partial else "warning",
            }
        )
    return envelope(
        "list",
        "ready",
        {"rows": rows, "detail": t("widget.week_mean", days=found.days_logged)},
    )


TONES = {"ok": "positive", "low": "warning", "high": "negative"}
FRONT = ("kcal", "protein", "carbs", "fat", "fiber", "sugars", "saturated_fat", "sodium")


async def goals_today(connection: AsyncConnection) -> dict:
    found = await summary.day(connection, today())
    if not found.entries:
        return envelope("list", "empty", {"detail": t("widget.nothing_today")})
    states = {one.nutrient: one for one in found.goals}
    rows = []
    for key in FRONT:
        one = states.get(key)
        if one is None or one.value is None:
            continue
        rows.append(
            {
                "label": one.name,
                "value": _figure(one),
                "tone": TONES.get(one.status, "neutral"),
            }
        )
    if not rows:
        return envelope("list", "empty", {"detail": t("widget.no_goals")})
    ok = sum(1 for one in found.goals if one.status == "ok")
    measured = sum(1 for one in found.goals if one.status != "none")
    return envelope(
        "list", "ready", {"rows": rows, "detail": t("widget.in_range", ok=ok, measured=measured)}
    )


def _figure(one: ranges.GoalState) -> str:
    unit = one.unit
    digits = 0 if unit == "kcal" or (one.value or 0) >= 100 else 1
    value = catalog.number(one.value or 0, digits)
    if one.basis == "kcal_pct" and one.share is not None:
        return f"{value} {unit} · {one.share:.0f} %"
    return f"{value} {unit}"


async def compliance(connection: AsyncConnection) -> dict:
    last = today()
    values = []
    any_logged = False
    for offset in range(27, -1, -1):
        found = await summary.day(connection, last - timedelta(days=offset))
        measured = [one for one in found.goals if one.status != "none"]
        if found.entries:
            any_logged = True
        values.append(
            round(sum(1 for one in measured if one.status == "ok") / len(measured), 2)
            if measured
            else 0.0
        )
    if not any_logged:
        return envelope("heatmap", "empty", {"detail": t("widget.nothing_four_weeks")})
    return envelope(
        "heatmap",
        "ready",
        {"values": values, "columns": 7, "detail": t("widget.compliance")},
    )


async def log_shortcut(connection: AsyncConnection) -> dict:
    del connection
    meal = meals.label(meals.meal_of(now())).lower()
    return envelope(
        "shortcuts",
        "ready",
        {
            "actions": [
                {"label": t("widget.log_meal", meal=meal), "href": "/macros/log", "icon": "plus"}
            ]
        },
    )


RENDERERS = {
    "today": for_today,
    "macros_today": macros_today,
    "week_short": week_short,
    "goals_today": goals_today,
    "compliance": compliance,
    "log": log_shortcut,
}
