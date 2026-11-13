from __future__ import annotations

from arga_module.i18n import missing, t
from library import library
from library.words import CATALOGS


def test_both_catalogs_have_the_same_keys() -> None:
    assert missing(CATALOGS) == []


def test_every_genre_has_a_name_in_both_languages() -> None:
    for genre in library.GENRES:
        assert t(CATALOGS, f"genre.{genre}", "en") != f"genre.{genre}"
        assert t(CATALOGS, f"genre.{genre}", "es") != f"genre.{genre}"
