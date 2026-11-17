from __future__ import annotations

from datetime import UTC, datetime

from arga_module import preferences
from goals import records, tasks, widgets

LATE = datetime(2026, 3, 1, 23, 30, tzinfo=UTC)


def person(**chosen: str) -> preferences.Preferences:
    headers = {preferences.HEADERS[key]: value for key, value in chosen.items()}
    return preferences.from_headers(headers)


def ticked_late() -> tasks.Task:
    return tasks.Task(
        id="t1",
        category_id="c1",
        category="Home",
        hue=2,
        title="Hang the laundry",
        notes=None,
        due_on=None,
        due_time=None,
        rule=None,
        repeats=None,
        status="done",
        done_at=LATE,
        done_by_me=True,
        space_id=None,
    )


def test_a_task_done_late_counts_on_the_day_of_the_person_time_zone() -> None:
    for zone, day in (("Europe/Madrid", "2026-03-02"), ("America/New_York", "2026-03-01")):
        token = preferences.use(person(timezone=zone))
        try:
            (found,) = records.days([ticked_late()])
        finally:
            preferences.reset(token)
        assert found["id"] == f"day:{day}"


def test_figures_follow_the_person_language() -> None:
    token = preferences.use(person(locale="en"))
    try:
        assert widgets._figure(8000, "steps") == "8,000 steps"
        assert widgets._figure(82.5, "kg") == "82.5 kg"
    finally:
        preferences.reset(token)
    token = preferences.use(person(locale="es"))
    try:
        assert widgets._figure(8000, "steps") == "8.000 pasos"
        assert widgets._figure(82.5, "kg") == "82,5 kg"
    finally:
        preferences.reset(token)


async def test_the_first_categories_are_named_in_the_person_language(api) -> None:
    response = await api.get("/categories", headers={"x-arga-locale": "es"})
    assert response.status_code == 200, response.text
    names = [one["name"] for one in response.json()]
    assert names[:3] == ["Trabajo", "Casa", "Personal"]


async def test_the_overdue_line_moves_with_the_time_zone(api) -> None:
    created = await api.get("/categories")
    category = created.json()[0]["id"]
    now = datetime.now(UTC)
    for zone in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
        local = now.astimezone(preferences.from_headers({"x-arga-timezone": zone}).zone)
        task = await api.post(
            "/tasks",
            json={"category_id": category, "title": zone, "due_on": local.date().isoformat()},
            headers={"x-arga-timezone": zone},
        )
        assert task.status_code == 201, task.text
        assert task.json()["status"] == "today"
