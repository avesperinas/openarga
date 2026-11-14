from __future__ import annotations

from datetime import UTC, datetime, timedelta

from arga_module import preferences
from arga_module.i18n import missing
from hub import connections
from hub.words import CATALOGS

NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)


def test_every_key_is_in_both_catalogs() -> None:
    assert missing(CATALOGS) == []


def test_connection_texts_follow_the_person_language() -> None:
    expiring = NOW + timedelta(days=3)
    assert connections.reason_of("BBVA", "expiring", expiring, None, NOW) == (
        "Access to BBVA expires in 3 days."
    )
    assert connections.brief("paused") == "Paused"
    token = preferences.use(preferences.from_headers({"x-arga-locale": "es"}))
    try:
        assert "BBVA" in connections.reason_of("BBVA", "expiring", expiring, None, NOW)
        assert connections.reason_of("BBVA", "expiring", expiring, None, NOW) != (
            "Access to BBVA expires in 3 days."
        )
        assert connections.brief("paused") != "Paused"
    finally:
        preferences.reset(token)


def test_the_catalogue_speaks_the_person_language() -> None:
    from hub import catalogue, plugs

    holidays = catalogue.provider("holidays")
    assert catalogue.listed()[0]["name"] == "Finance"
    assert catalogue.offer_of(holidays)["title"] == "Public holidays"
    token = preferences.use(preferences.from_headers({"x-arga-locale": "es"}))
    try:
        assert catalogue.listed()[0]["name"] != "Finance"
        assert catalogue.offer_of(holidays)["title"] != "Public holidays"
        assert {group["id"] for group in plugs.groups()} == {g.id for g in catalogue.GROUPS}
    finally:
        preferences.reset(token)


def test_every_spanish_catalogue_text_names_a_declared_text() -> None:
    import json
    from dataclasses import fields, is_dataclass

    from hub import catalogue
    from hub.words import CATALOGUE

    declared: set[str] = set()

    def walk(prefix: str, one: object) -> None:
        for field in fields(one):
            value = getattr(one, field.name)
            if isinstance(value, str) and value:
                declared.add(f"{prefix}.{field.name}")
            elif field.name == "offer" and is_dataclass(value):
                walk(f"{prefix}.offer", value)
            elif isinstance(value, tuple):
                for item in value:
                    if is_dataclass(item):
                        key = getattr(item, "key", None) or getattr(item, "value", None)
                        walk(f"{prefix}.{field.name.removesuffix('s')}.{key}", item)

    for provider in catalogue.PROVIDERS:
        walk(f"provider.{provider.id}", provider)
    declared |= {f"category.{one.id}" for one in catalogue.CATEGORIES}
    declared |= {f"group.{one.id}" for one in catalogue.GROUPS}
    spanish = json.loads((CATALOGUE / "es.json").read_text(encoding="utf-8"))
    assert sorted(set(spanish) - declared) == []
