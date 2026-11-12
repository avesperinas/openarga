from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Literal

Locale = Literal["en", "es"]
LOCALES: tuple[Locale, ...] = ("en", "es")
SOURCE: Locale = "en"
_FIELD = re.compile(r"\{(\w+)\}")


@cache
def catalogs(directory: Path) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for locale in LOCALES:
        path = directory / f"{locale}.json"
        found[locale] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return found


def _fill(template: str, values: dict[str, object]) -> str:
    return _FIELD.sub(
        lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), template
    )


def t(directory: Path, key: str, locale: str = SOURCE, **values: object) -> str:
    loaded = catalogs(directory)
    template = loaded.get(locale, {}).get(key) or loaded[SOURCE].get(key) or key
    return _fill(template, values)


def missing(directory: Path) -> list[tuple[str, str]]:
    loaded = catalogs(directory)
    keys = set().union(*(set(catalog) for catalog in loaded.values()))
    return sorted((locale, key) for locale in LOCALES for key in keys if key not in loaded[locale])
