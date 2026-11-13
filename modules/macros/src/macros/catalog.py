from __future__ import annotations

from pathlib import Path

from arga_module import i18n, preferences

CATALOGS = Path(__file__).parent / "i18n"


def t(key: str, **values: object) -> str:
    return i18n.t(CATALOGS, key, preferences.current().locale, **values)


def number(value: float, decimals: int = 0) -> str:
    grouped = f"{value:,.{decimals}f}"
    return (
        grouped.replace(",", "\0")
        .replace(".", t("number.decimal"))
        .replace("\0", t("number.group"))
    )


def short(value: float) -> str:
    return f"{value:g}".replace(".", t("number.decimal"))


def nutrient(key: str) -> str:
    return t(f"nutrient.{key}")
