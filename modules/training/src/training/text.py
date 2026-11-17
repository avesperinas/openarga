from __future__ import annotations

import json
from pathlib import Path

from arga_module import i18n, preferences

CATALOGS = Path(__file__).parent / "i18n"


def t(key: str, **values: object) -> str:
    return i18n.t(CATALOGS, key, preferences.current().locale, **values)


def shown_names() -> str:
    found = i18n.catalogs(CATALOGS).get(preferences.current().locale, {})
    return json.dumps(
        {key: value for key, value in found.items() if key.startswith(("exercise.", "variant."))}
    )


def shown(kind: str, alias: str) -> str:
    return f"coalesce(cast(:names as jsonb) ->> ('{kind}.' || {alias}.key), {alias}.name)"
