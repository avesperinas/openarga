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
