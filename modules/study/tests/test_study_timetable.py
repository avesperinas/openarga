from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from study.studies import today

MADRID = ZoneInfo("Europe/Madrid")


async def a_course(api) -> tuple[str, str]:
    created = (
        await api.post(
            "/courses",
            json={"name": "Máster", "tone": 5, "subjects": [{"name": "Estadística", "credits": 6}]},
        )
    ).json()
    return created["course"]["id"], created["subjects"][0]["id"]


def tuesdays_and_thursdays(start, until) -> dict:
    return {
        "freq": "weekly",
        "by_day": [{"weekday": "TU"}, {"weekday": "TH"}],
        "until": until.isoformat(),
    }


async def test_changing_the_timetable_midterm_moves_future_classes_and_keeps_touched_ones(
    api,
    notebook,
) -> None:
    course_id, subject_id = await a_course(api)
    start = today() - timedelta(weeks=6)
    until = today() + timedelta(weeks=6)
    block = {
        "subject_id": subject_id,
        "rule": tuesdays_and_thursdays(start, until),
        "starts_on": start.isoformat(),
        "start_time": "18:00",
        "end_time": "20:00",
        "place": "Study 2.3",
    }
    created = await api.post(f"/courses/{course_id}/schedules", json=block)
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert schedule["phrase"].startswith("cada semana, martes y jueves")
    total = schedule["sessions"]
    assert 22 <= total <= 26

    sessions = (await api.get(f"/courses/{course_id}/sessions")).json()
    now = datetime.now(MADRID)
    past = [s for s in sessions if datetime.fromisoformat(s["starts_at"]) < now]
    future = [s for s in sessions if datetime.fromisoformat(s["starts_at"]) > now]
    assert {datetime.fromisoformat(s["starts_at"]).astimezone(MADRID).time() for s in sessions} == {
        time(18)
    }
    with_notes, attended_past = future[1], past[0]
    note = await api.post(
        "/notes",
        json={
            "course_id": course_id,
            "session_id": with_notes["id"],
            "title": "Tema 7",
            "body": "Lo que se vio",
        },
    )
    assert note.status_code == 201, note.text
    await api.put(f"/sessions/{attended_past['id']}/attendance", json={"attendance": "present"})

    moved = await api.put(
        f"/schedules/{schedule['id']}",
        json={**block, "start_time": "10:00", "end_time": "12:00", "place": "Study 1.1"},
    )
    assert moved.status_code == 200, moved.text

    after = (await api.get(f"/courses/{course_id}/sessions")).json()
    by_id = {s["id"]: s for s in after}
    kept = by_id[with_notes["id"]]
    assert datetime.fromisoformat(kept["starts_at"]).astimezone(MADRID).time() == time(18)
    assert kept["place"] == "Study 2.3"
    assert kept["has_notes"] is True
    for old in past:
        assert by_id[old["id"]]["place"] == "Study 2.3"
    assert by_id[attended_past["id"]]["attendance"] == "present"
    upcoming = [
        s
        for s in after
        if datetime.fromisoformat(s["starts_at"]) > now and s["id"] != with_notes["id"]
    ]
    assert upcoming
    assert all(s["place"] == "Study 1.1" for s in upcoming)
    assert {datetime.fromisoformat(s["starts_at"]).astimezone(MADRID).time() for s in upcoming} == {
        time(10)
    }
    assert len(after) == total


async def test_a_class_is_moved_or_cancelled_on_its_own(api) -> None:
    course_id, subject_id = await a_course(api)
    start = today() + timedelta(days=1)
    block = {
        "subject_id": subject_id,
        "rule": {"freq": "weekly", "count": 4},
        "starts_on": start.isoformat(),
        "start_time": "09:00",
        "end_time": "11:00",
    }
    schedule = (await api.post(f"/courses/{course_id}/schedules", json=block)).json()
    first = (await api.get(f"/courses/{course_id}/sessions")).json()[0]

    later = datetime.fromisoformat(first["starts_at"]) + timedelta(hours=3)
    moved = await api.put(
        f"/sessions/{first['id']}",
        json={
            "starts_at": later.isoformat(),
            "ends_at": (later + timedelta(hours=2)).isoformat(),
            "place": "Salón de actos",
            "status": "cancelled",
        },
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["session"]["status"] == "cancelled"

    await api.put(f"/schedules/{schedule['id']}", json={**block, "place": "Study 3"})
    again = {s["id"]: s for s in (await api.get(f"/courses/{course_id}/sessions")).json()}
    assert again[first["id"]]["status"] == "cancelled"
    assert again[first["id"]]["place"] == "Salón de actos"
    assert len(again) == 4

    refused = await api.put(f"/sessions/{first['id']}/attendance", json={"attendance": "present"})
    assert refused.status_code == 409
    assert (await api.delete(f"/sessions/{first['id']}")).status_code == 409


async def test_loose_sessions_and_the_week_on_the_home(api, notebook) -> None:
    course_id, _ = await a_course(api)
    at = datetime.combine(today(), time(12), tzinfo=MADRID)
    added = await api.post(
        f"/courses/{course_id}/sessions",
        json={
            "kind": "tutorial",
            "title": "Tutoría del TFM",
            "starts_at": at.isoformat(),
            "ends_at": (at + timedelta(minutes=30)).isoformat(),
            "url": "meet.example.org/abc",
        },
    )
    assert added.status_code == 201, added.text

    home = (await api.get("/home")).json()
    today_ = next(day for day in home["days"] if day["today"])
    assert [s["title"] for s in today_["sessions"]] == ["Tutoría del TFM"]
    assert today_["sessions"][0]["tone"] == 5
    assert today_["sessions"][0]["url"] == "https://meet.example.org/abc"

    session_id = added.json()["session"]["id"]
    page = (await api.get(f"/sessions/{session_id}")).json()
    assert page["detail"]["course_name"] == "Máster"
    assert (await api.delete(f"/sessions/{session_id}")).status_code == 204


async def test_deleting_a_block_keeps_what_already_happened(api, schema) -> None:
    course_id, subject_id = await a_course(api)
    start = today() - timedelta(weeks=2)
    block = {
        "subject_id": subject_id,
        "rule": {"freq": "weekly", "until": (today() + timedelta(weeks=2)).isoformat()},
        "starts_on": start.isoformat(),
        "start_time": "09:00",
        "end_time": "10:00",
    }
    schedule = (await api.post(f"/courses/{course_id}/schedules", json=block)).json()

    removed = (await api.delete(f"/schedules/{schedule['id']}")).json()["removed_sessions"]

    left = (await api.get(f"/courses/{course_id}/sessions")).json()
    assert removed >= 2
    assert all(datetime.fromisoformat(s["starts_at"]) < datetime.now(MADRID) for s in left)
    async with schema.begin() as connection:
        cancelled = await connection.scalar(
            text(
                "select count(*) from study.study_outbox "
                "where type = 'study.session' and payload->'agenda'->>'status' = 'cancelled'"
            )
        )
    assert cancelled == removed


async def test_the_schedule_cannot_end_before_it_starts(api) -> None:
    course_id, _ = await a_course(api)
    response = await api.post(
        f"/courses/{course_id}/schedules",
        json={
            "rule": {"freq": "weekly"},
            "starts_on": "2026-10-01",
            "start_time": "10:00",
            "end_time": "09:00",
        },
    )

    assert response.status_code == 422
    assert "acabar después de empezar" in response.text
