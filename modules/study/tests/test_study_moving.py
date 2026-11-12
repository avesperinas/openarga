from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from study.studies import today

MADRID = ZoneInfo("Europe/Madrid")

TOKEN = "probe-token"


@pytest.fixture(autouse=True)
def token(monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)


async def move(api, uid: str, start, end, **extra):
    return await api.post(
        "/capabilities/agenda.move",
        json={"uid": uid, "start": str(start), "end": str(end), **extra},
        headers={"x-module-token": TOKEN, "x-arga-module": "planner"},
    )


async def a_course(api) -> tuple[str, str]:
    created = (
        await api.post(
            "/courses",
            json={"name": "Máster", "tone": 5, "subjects": [{"name": "Estadística", "credits": 6}]},
        )
    ).json()
    return created["course"]["id"], created["subjects"][0]["id"]


async def a_class(api) -> tuple[str, dict]:
    course_id, subject_id = await a_course(api)
    block = {
        "subject_id": subject_id,
        "rule": {"freq": "weekly", "count": 2},
        "starts_on": (today() + timedelta(days=1)).isoformat(),
        "start_time": "09:00",
        "end_time": "11:00",
    }
    await api.post(f"/courses/{course_id}/schedules", json=block)
    return course_id, (await api.get(f"/courses/{course_id}/sessions")).json()[0]


async def published(schema, type_: str) -> list[dict]:
    async with schema.begin() as connection:
        rows = await connection.execute(
            text("select payload from study.study_outbox where type = :t order by id"), {"t": type_}
        )
        return [row.payload["agenda"] for row in rows if "agenda" in row.payload]


async def test_a_class_moves_and_back_and_the_calendar_hears_both(api, schema) -> None:
    course_id, first = await a_class(api)
    uid = f"study:session:{first['id']}"
    at = datetime.fromisoformat(first["starts_at"])
    later = at + timedelta(hours=3)

    moved = await move(api, uid, later.isoformat(), (later + timedelta(hours=1)).isoformat())
    back = await move(api, uid, at.isoformat(), (at + timedelta(hours=2)).isoformat())

    assert moved.status_code == 200, moved.text
    assert datetime.fromisoformat(moved.json()["agenda"]["start"]) == later
    assert datetime.fromisoformat(back.json()["agenda"]["start"]) == at
    mine = [p for p in await published(schema, "study.session") if p["uid"] == uid]
    assert [datetime.fromisoformat(p["start"]) for p in mine][-2:] == [later, at]
    sessions = {s["id"]: s for s in (await api.get(f"/courses/{course_id}/sessions")).json()}
    assert datetime.fromisoformat(sessions[first["id"]]["starts_at"]) == at


async def test_a_class_has_a_time(api) -> None:
    _, first = await a_class(api)
    day = today() + timedelta(days=3)
    refused = await move(
        api,
        f"study:session:{first['id']}",
        day.isoformat(),
        (day + timedelta(days=1)).isoformat(),
        all_day=True,
    )
    assert refused.status_code == 409


async def test_an_assessment_keeps_the_start_or_becomes_a_whole_day(api) -> None:
    course_id, subject_id = await a_course(api)
    created = (
        await api.post(
            f"/courses/{course_id}/assessments",
            json={
                "subject_id": subject_id,
                "title": "Parcial",
                "kind": "exam",
                "due_on": (today() + timedelta(days=5)).isoformat(),
                "due_time": "10:00",
            },
        )
    ).json()
    uid = f"study:assessment:{created['id']}"
    at = datetime.combine(today() + timedelta(days=6), datetime.min.time(), MADRID).replace(hour=12)

    timed = await move(api, uid, at.isoformat(), (at + timedelta(minutes=15)).isoformat())
    day = today() + timedelta(days=7)
    whole = await move(
        api, uid, day.isoformat(), (day + timedelta(days=1)).isoformat(), all_day=True
    )

    assert timed.status_code == 200, timed.text
    assert timed.json()["agenda"]["start"] == timed.json()["agenda"]["end"]
    assert datetime.fromisoformat(timed.json()["agenda"]["start"]) == at
    assert (whole.json()["agenda"]["all_day"], whole.json()["agenda"]["start"]) == (
        True,
        day.isoformat(),
    )
    stored = (await api.get(f"/assessments/{created['id']}")).json()
    assert (stored["due_on"], stored["due_time"]) == (day.isoformat(), None)


async def test_only_the_kernel_asks_and_only_for_what_is_studys(api) -> None:
    _, first = await a_class(api)
    at = datetime.fromisoformat(first["starts_at"])
    body = {
        "uid": f"study:session:{first['id']}",
        "start": at.isoformat(),
        "end": (at + timedelta(hours=1)).isoformat(),
    }

    forged = await api.post(
        "/capabilities/agenda.move", json=body, headers={"x-module-token": "no"}
    )
    other = await move(api, "training:activity:1", body["start"], body["end"])
    missing = await move(
        api, "study:session:00000000-0000-0000-0000-000000000000", body["start"], body["end"]
    )

    assert forged.status_code == 401
    assert other.status_code == 404
    assert missing.status_code == 404
