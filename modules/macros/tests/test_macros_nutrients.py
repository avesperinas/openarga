from __future__ import annotations

from pathlib import Path

import arga_nutrients
from arga_module import i18n, preferences
from macros import catalog

CATALOGS = Path(__file__).resolve().parents[1] / "src" / "macros" / "i18n"


def test_every_nutrient_has_an_english_and_a_spanish_name() -> None:
    loaded = i18n.catalogs(CATALOGS)
    keys = [f"nutrient.{one['key']}" for one in arga_nutrients.catalogue()]
    for locale in ("en", "es"):
        assert [key for key in keys if key not in loaded[locale]] == []
    assert sorted(loaded["en"]) == sorted(loaded["es"])


def test_a_nutrient_is_named_in_the_person_language() -> None:
    names = {}
    for locale in ("en", "es"):
        token = preferences.use(preferences.from_headers({"x-arga-locale": locale}))
        try:
            names[locale] = catalog.nutrient("protein")
        finally:
            preferences.reset(token)
    assert names["en"] == "Protein"
    assert names["es"] != names["en"]
