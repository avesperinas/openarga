from __future__ import annotations

from pathlib import Path

from arga_module import i18n, preferences

CATALOGS = Path(__file__).parent / "i18n"


def t(key: str, **values: object) -> str:
    return i18n.t(CATALOGS, key, preferences.current().locale, **values)
