from __future__ import annotations

from arga_module import i18n, preferences
from money import texts


def person(**chosen: str) -> preferences.Preferences:
    headers = {preferences.HEADERS[key]: value for key, value in chosen.items()}
    return preferences.from_headers(headers)


def said(**chosen: str):
    token = preferences.use(person(**chosen))
    try:
        return (
            texts.amount(1234.4),
            texts.amount(-50, sign=True),
            texts.percent(0.126, sign=True),
            texts.number(1234.5, 1),
            texts.month(3),
            texts.t("kpi.networth"),
        )
    finally:
        preferences.reset(token)


def test_amounts_and_words_follow_the_person() -> None:
    assert said(locale="en", currency="USD") == (
        "$1,234",
        "−$50",
        "+13%",
        "1,234.5",
        "March",
        "Net worth",
    )
    spanish = i18n.catalogs(texts.CATALOGS)["es"]
    assert said(locale="es", currency="EUR") == (
        "1.234 €",
        "−50 €",
        "+13 %",
        "1.234,5",
        spanish["month.3"],
        spanish["kpi.networth"],
    )


def test_an_unknown_currency_is_shown_by_its_code() -> None:
    assert said(locale="en", currency="SEK")[0] == "SEK1,234"


def test_both_catalogs_have_the_same_keys() -> None:
    assert i18n.missing(texts.CATALOGS) == []
