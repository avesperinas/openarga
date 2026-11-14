from __future__ import annotations

from pathlib import Path

from arga_module import i18n, preferences

CATALOGS = Path(__file__).parent / "i18n"


def t(key: str, **values: object) -> str:
    return i18n.t(CATALOGS, key, preferences.current().locale, **values)


SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "JPY": "¥", "CHF": "CHF", "MXN": "$"}


def currency() -> str:
    return preferences.current().currency


def symbol() -> str:
    return SYMBOLS.get(currency(), currency())


def number(value: float, decimals: int = 0) -> str:
    grouped = f"{abs(value):,.{decimals}f}"
    text = (
        grouped.replace(",", "\0")
        .replace(".", t("number.decimal"))
        .replace("\0", t("number.group"))
    )
    return f"−{text}" if round(value, decimals) < 0 else text


def amount(value: float, sign: bool = False) -> str:
    whole = round(value)
    text = t("money.format", amount=number(abs(whole)), symbol=symbol())
    if whole < 0:
        return f"−{text}"
    return f"+{text}" if sign and whole > 0 else text


def percent(value: float, sign: bool = False) -> str:
    whole = round(value * 100)
    text = t("percent.format", value=abs(whole))
    if whole < 0:
        return f"−{text}"
    return f"+{text}" if sign and whole > 0 else text


def month(index: int) -> str:
    return t(f"month.{index}")
