from __future__ import annotations

from pathlib import Path

from arga_module import preferences
from arga_module.i18n import SOURCE, catalogs, t

CATALOGS = Path(__file__).resolve().parent / "i18n"
CATALOGUE = Path(__file__).resolve().parent / "providers" / "i18n"


def say(key: str, **values: object) -> str:
    return t(CATALOGS, key, preferences.current().locale, **values)


def local(key: str, source: str) -> str:
    locale = preferences.current().locale
    if locale == SOURCE or not source:
        return source
    return catalogs(CATALOGUE).get(locale, {}).get(key) or source
