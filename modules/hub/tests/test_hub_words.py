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
