from pathlib import Path

import pytest

from arga_module import demo

ROOT = Path(__file__).resolve().parents[3]


def test_the_demo_cast_is_two_people_who_share_a_space() -> None:
    cast = demo.load(ROOT / "demo" / "personas.yaml")

    assert [person.name for person in cast.people] == ["Alex", "Sam"]
    assert {person.locale for person in cast.people} == {"en", "es"}
    assert len({person.id for person in cast.people}) == 2


def test_a_module_takes_part_in_the_demo_by_having_a_demo_module(tmp_path) -> None:
    (tmp_path / "probe" / "src" / "probe").mkdir(parents=True)
    (tmp_path / "probe" / "manifest.yaml").write_text("id: probe\n")

    assert demo.seeds(tmp_path) == {}


def test_demo_text_is_localized_for_spanish_personas_only(tmp_path) -> None:
    (tmp_path / "es.json").write_text('{"Lentil stew": "Estofado de lentejas"}')
    say = demo.localizer(tmp_path)
    alex, sam = demo.load(ROOT / "demo" / "personas.yaml").people

    assert say(alex, "Lentil stew") == "Lentil stew"
    assert say(sam, "Lentil stew") == "Estofado de lentejas"
    assert say(sam, "Unlisted") == "Unlisted"
    assert demo.localized(say, sam, {"names": ["Lentil stew", 3]}) == {
        "names": ["Estofado de lentejas", 3]
    }


def test_localizing_reaches_into_dataclasses_and_nested_tuples(tmp_path) -> None:
    from dataclasses import dataclass

    @dataclass
    class Trip:
        title: str
        stays: list[tuple[str, int]]

    (tmp_path / "es.json").write_text('{"Beach": "Playa"}')
    say = demo.localizer(tmp_path)
    sam = demo.load(ROOT / "demo" / "personas.yaml").people[1]

    assert demo.localized(say, sam, Trip("Beach", [("Beach", 2)])) == Trip("Playa", [("Playa", 2)])


def test_a_copy_of_the_cast_has_its_own_ids_names_and_language() -> None:
    cast = demo.load(ROOT / "demo" / "personas.yaml")
    copy = demo.copy_of(cast, "k3x9q2m7", "es")
    again = demo.copy_of(cast, "k3x9q2m7", "es")
    other = demo.copy_of(cast, "z8w1v4b6")

    assert copy == again
    assert copy.copy == "k3x9q2m7" and cast.copy is None
    assert {person.id for person in copy.people}.isdisjoint(person.id for person in cast.people)
    assert {person.id for person in copy.people}.isdisjoint(person.id for person in other.people)
    assert copy.space_id not in (cast.space_id, other.space_id)
    assert [person.key for person in copy.people] == ["alex", "sam"]
    assert [person.username for person in copy.people] == ["k3x9q2m7-alex", "k3x9q2m7-sam"]
    assert {person.locale for person in copy.people} == {"es"}
    assert [person.locale for person in other.people] == ["en", "es"]


def test_seed_keys_stay_as_they_were_for_the_cast_and_differ_per_copy() -> None:
    cast = demo.load(ROOT / "demo" / "personas.yaml")
    alex = cast.people[0]
    copied = demo.copy_of(cast, "k3x9q2m7").people[0]

    assert alex.seed_key == "alex"
    assert copied.seed_key == "k3x9q2m7:alex"
    assert alex.id_of("sam") == cast.people[1].id
    assert copied.id_of("sam") == demo.copy_of(cast, "k3x9q2m7").people[1].id


def test_a_copy_tag_is_short_lowercase_letters_and_digits() -> None:
    cast = demo.load(ROOT / "demo" / "personas.yaml")
    for bad in ("", "abc", "UPPER123", "has-dash1", "a" * 17, "x'; drop"):
        with pytest.raises(ValueError):
            demo.copy_of(cast, bad)
