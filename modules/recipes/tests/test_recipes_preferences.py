from __future__ import annotations

from arga_module import i18n, preferences
from recipes import catalog, nutrition


def person(**chosen: str) -> preferences.Preferences:
    headers = {preferences.HEADERS[key]: value for key, value in chosen.items()}
    return preferences.from_headers(headers)


def test_server_texts_follow_the_locale_of_the_person() -> None:
    spanish = i18n.catalogs(catalog.CATALOGS)["es"]
    total = nutrition.Totals(
        kcal=0,
        protein=0,
        fat=0,
        carbs=0,
        fiber=None,
        salt=None,
        grams=0,
        counted=2,
        total=3,
        missing=("sofrito",),
    )

    token = preferences.use(person(locale="en"))
    try:
        assert nutrition.uncertainty(total) == "1 of 3 ingredients missing (sofrito)"
    finally:
        preferences.reset(token)

    token = preferences.use(person(locale="es"))
    try:
        expected = spanish["nutrition.missing.one"].format(count=1, total=3)
        assert nutrition.uncertainty(total) == f"{expected} (sofrito)"
    finally:
        preferences.reset(token)


def test_both_catalogs_have_the_same_keys() -> None:
    assert i18n.missing(catalog.CATALOGS) == []
