from __future__ import annotations

from datetime import UTC, datetime

from arga_module import i18n, preferences
from training import panel, text, training


def person(**chosen: str) -> preferences.Preferences:
    return preferences.from_headers(
        {preferences.HEADERS[key]: value for key, value in chosen.items()}
    )


def test_the_day_of_a_moment_depends_on_the_time_zone_of_the_person() -> None:
    moment = datetime(2026, 9, 14, 23, 30, tzinfo=UTC)

    token = preferences.use(person(timezone="Europe/Madrid"))
    try:
        assert training.local_day(moment).isoformat() == "2026-09-15"
    finally:
        preferences.reset(token)

    token = preferences.use(person(timezone="America/New_York"))
    try:
        assert training.local_day(moment).isoformat() == "2026-09-14"
    finally:
        preferences.reset(token)


def test_server_texts_follow_the_locale_of_the_person() -> None:
    token = preferences.use(person(locale="es"))
    try:
        spanish = i18n.catalogs(text.CATALOGS)["es"]
        assert text.t("panel.next") == spanish["panel.next"] != "Next session"
        assert panel.nothing().detail == spanish["panel.empty"]
    finally:
        preferences.reset(token)

    token = preferences.use(person(locale="en"))
    try:
        assert text.t("panel.due", name="Push") == "Up next: Push"
    finally:
        preferences.reset(token)


def test_both_catalogs_have_the_same_keys() -> None:
    assert i18n.missing(text.CATALOGS) == []
