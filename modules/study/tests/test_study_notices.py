from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from test_study_studies import create

from study import notices
from study.db import engine
from study.studies import today


async def built() -> list[dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_study"'))
        return await notices.build(connection)


async def test_the_evening_before_each_pending_assessment(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    soon = today() + timedelta(days=3)
    entrega = (
        await api.post(
            f"/courses/{course_id}/assessments",
            json={"title": "Entrega 1", "due_on": soon.isoformat()},
        )
    ).json()
    await api.post(f"/courses/{course_id}/assessments", json={"title": "Sin fecha"})

    [notice] = await built()
    assert notice["title"] == "Mañana: Entrega 1" and notice["kind"] == "assessment"
    assert notice["at"].startswith((soon - timedelta(days=1)).isoformat())
    assert "T19:00:00+0" in notice["at"]

    await api.put(f"/assessments/{entrega['id']}/grade", json={"grade": 8})
    assert await built() == []
