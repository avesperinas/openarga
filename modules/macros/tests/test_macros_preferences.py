from __future__ import annotations

from datetime import UTC, date, datetime

from arga_module import i18n, preferences
from macros import catalog, common, expenditure, meals


def person(**chosen: str) -> preferences.Preferences:
    headers = {preferences.HEADERS[key]: value for key, value in chosen.items()}
    return preferences.from_headers(headers)


def test_the_day_and_the_meal_of_a_moment_follow_the_time_zone_of_the_person() -> None:
    moment = datetime(2026, 9, 14, 22, 30, tzinfo=UTC)

    token = preferences.use(person(timezone="Europe/Madrid"))
    try:
        assert common.local_day(moment) == date(2026, 9, 15)
        assert meals.meal_of(moment) == "night"
    finally:
        preferences.reset(token)

    token = preferences.use(person(timezone="America/New_York"))
    try:
        assert common.local_day(moment) == date(2026, 9, 14)
        assert meals.meal_of(moment) == "snack"
    finally:
        preferences.reset(token)


def test_server_texts_and_numbers_follow_the_locale_of_the_person() -> None:
    spanish = i18n.catalogs(catalog.CATALOGS)["es"]
    lose = expenditure.Proposal(rate_kg_week=-0.3, kcal=2150, floored=False)

    token = preferences.use(person(locale="en"))
    try:
        assert meals.label("lunch") == "Lunch"
        assert catalog.nutrient("fiber") == "Fibre"
        assert expenditure.proposal_label(lose) == "To lose 0.3 kg a week, 2,150 kcal"
    finally:
        preferences.reset(token)

    token = preferences.use(person(locale="es"))
    try:
        assert meals.label("lunch") == spanish["meal.lunch"]
        assert catalog.nutrient("fiber") == spanish["nutrient.fiber"]
        assert expenditure.proposal_label(lose) == spanish["expenditure.lose"].format(
            amount="0,3", kcal="2.150"
        )
    finally:
        preferences.reset(token)


def test_both_catalogs_have_the_same_keys() -> None:
    assert i18n.missing(catalog.CATALOGS) == []
