from __future__ import annotations

from datetime import date
from pathlib import Path

from arga_module import i18n, preferences

CATALOGS = Path(__file__).parent / "i18n"


def t(key: str, **values: object) -> str:
    return i18n.t(CATALOGS, key, preferences.current().locale, **values)


def number(value: float, decimals: int = 1) -> str:
    grouped = f"{value:,.{decimals}f}"
    return (
        grouped.replace(",", "\0")
        .replace(".", t("number.decimal"))
        .replace("\0", t("number.group"))
    )


def weekday(day: date) -> str:
    return t(f"weekday.{day.weekday()}")


def day_month(day: date) -> str:
    return t("date.day_month", day=day.day, month=t(f"month.{day.month}"))


def full_date(day: date) -> str:
    return t("date.full", day=day.day, month=t(f"month.{day.month}"), year=day.year)
