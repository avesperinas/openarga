from __future__ import annotations

from conftest import OTHER, PERSON

from arga_tenancy import as_user


async def test_each_person_sees_only_their_own_readings(api) -> None:
    with as_user(PERSON):
        await api.post("/readings", json={"label": "peso", "value": 71})
    with as_user(OTHER):
        await api.post("/readings", json={"label": "pasos", "value": 9000})

    with as_user(PERSON):
        mine = (await api.get("/readings")).json()
    with as_user(OTHER):
        theirs = (await api.get("/readings")).json()

    assert [one["label"] for one in mine] == ["peso"]
    assert [one["label"] for one in theirs] == ["pasos"]


async def test_the_same_label_has_a_target_for_each_person(api) -> None:
    with as_user(PERSON):
        await api.put("/targets", json={"label": "peso", "value": 70})
    with as_user(OTHER):
        await api.put("/targets", json={"label": "peso", "value": 60})
        assert (await api.put("/targets", json={"label": "peso", "value": 61})).status_code == 200
