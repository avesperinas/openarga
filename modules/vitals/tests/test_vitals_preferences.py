from __future__ import annotations

from datetime import UTC, date, datetime

from arga_module import i18n, preferences
from vitals import panel, steps, text, widgets


def person(**chosen: str) -> preferences.Preferences:
    headers = {preferences.HEADERS[key]: value for key, value in chosen.items()}
    return preferences.from_headers(headers)


def test_the_day_of_a_moment_depends_on_the_time_zone_of_the_person() -> None:
    moment = datetime(2026, 9, 14, 23, 30, tzinfo=UTC)

    token = preferences.use(person(timezone="Europe/Madrid"))
    try:
        assert moment.astimezone(steps.zone()).date() == date(2026, 9, 15)
    finally:
        preferences.reset(token)

    token = preferences.use(person(timezone="America/New_York"))
    try:
        assert moment.astimezone(steps.zone()).date() == date(2026, 9, 14)
    finally:
        preferences.reset(token)


def test_server_texts_and_numbers_follow_the_locale_of_the_person() -> None:
    spanish = i18n.catalogs(text.CATALOGS)["es"]
    today = date(2026, 9, 28)

    token = preferences.use(person(locale="en"))
    try:
        assert widgets.which_day(date(2026, 9, 12), today) == "September 12"
        assert text.number(9432.5, 1) == "9,432.5"
    finally:
        preferences.reset(token)

    token = preferences.use(person(locale="es"))
    try:
        assert widgets.which_day(date(2026, 9, 27), today) == spanish["day.yesterday"]
        assert text.number(9432.5, 1) == "9.432,5"
        assert panel.nothing().detail == spanish["panel.empty"]
    finally:
        preferences.reset(token)


def test_both_catalogs_have_the_same_keys() -> None:
    assert i18n.missing(text.CATALOGS) == []
