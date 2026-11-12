from __future__ import annotations

from sqlalchemy import text
from test_study_studies import create

import arga_contracts as contracts
from arga_contracts import metrics as publish
from study import metrics
from study.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_study"'))
        found = await metrics.build(connection)
    for one in found:
        assert one == contracts.metric("study", **one)
    return {one["key"]: one for one in found}


async def test_the_average_and_the_subjects_passed_of_a_course(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    stats, ml = created["subjects"][0]["id"], created["subjects"][1]["id"]
    await api.put(f"/subjects/{stats}/record", json={"final_grade": 8})
    await api.put(f"/subjects/{ml}/record", json={"final_grade": 4})

    found = await built()

    assert found[f"study.average:{course_id}"]["value"] == 6.0
    assert found[f"study.subjects_passed:{course_id}"]["value"] == 1
    assert found[f"study.passed:{course_id}"]["value"] == 0


async def test_finishing_it_passes_it_the_day_it_closed(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    closed = await api.post(
        f"/courses/{course_id}/close", json={"status": "finished", "final_grade": 8.4}
    )
    day = closed.json()["course"]["closed_on"]

    found = await built()
    passed = found[f"study.passed:{course_id}"]

    assert passed["value"] == 1 and passed["day"] == day
    assert found[f"study.finished:{course_id}"]["value"] == 1


async def test_an_unchanged_average_keeps_its_day(api) -> None:
    created = await create(api)
    await api.put(f"/subjects/{created['subjects'][0]['id']}/record", json={"final_grade": 8})
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_study"'))
        first = await publish.publish(connection, "study", await metrics.build(connection))
        again = await publish.publish(connection, "study", await metrics.build(connection))
    assert first["added"] >= 4
    assert again == {"added": 0, "changed": 0, "zeroed": 0}
