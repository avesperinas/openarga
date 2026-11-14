from __future__ import annotations

from pathlib import Path

from arga_module import preferences
from arga_module.i18n import t

CATALOGS = Path(__file__).resolve().parent / "i18n"


def say(key: str, **values: object) -> str:
    return t(CATALOGS, key, preferences.current().locale, **values)


def words(key: str) -> list[str]:
    return [one.strip() for one in say(key).split(",") if one.strip()]
