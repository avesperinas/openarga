from __future__ import annotations

from pathlib import Path

from test_training_tools import api, setup  # noqa: F401

from arga_module import i18n
from training import seed

CATALOGS = Path(__file__).resolve().parents[1] / "src" / "training" / "i18n"


def test_every_seeded_exercise_and_variant_has_an_english_and_a_spanish_name() -> None:
    loaded = i18n.catalogs(CATALOGS)
    keys = [f"exercise.{seed.key_of(one[0])}" for one in seed.EXERCISES]
    keys += [f"variant.{seed.key_of(one[1])}" for one in seed.VARIANTS]
    for locale in ("en", "es"):
        assert [key for key in keys if key not in loaded[locale]] == []
    assert [loaded["en"][key] for key in keys] == [one[0] for one in seed.EXERCISES] + [
        one[1] for one in seed.VARIANTS
    ]


async def test_the_catalogue_speaks_the_person_language(api) -> None:  # noqa: F811
    spanish = (await api.get("/catalogue", headers={"x-arga-locale": "es"})).json()
    english = (await api.get("/catalogue", headers={"x-arga-locale": "en"})).json()

    spoken = {one["name"] for one in spanish["exercises"]}
    assert "Press de banca" in spoken and "Bench press" not in spoken
    assert "Bench press" in {one["name"] for one in english["exercises"]}
    variants = {variant["name"] for one in spanish["exercises"] for variant in one["variants"]}
    assert "Prensa de piernas" in variants
