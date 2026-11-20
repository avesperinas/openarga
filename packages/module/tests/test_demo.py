from pathlib import Path

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
