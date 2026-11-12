from __future__ import annotations

from datetime import timedelta

import httpx

from study.studies import today

WRITE = {"x-arga-scopes": "study:write"}
READ = {"x-arga-scopes": "study:read"}


async def call(api, name: str, body: dict, headers=WRITE) -> httpx.Response:
    return await api.post(f"/tools/{name}", json=body, headers=headers)


def a_guide() -> dict:
    start = today() - timedelta(weeks=1)
    end = today() + timedelta(weeks=14)
    return {
        "name": "Máster en Inteligencia Artificial",
        "kind": "master",
        "institution": "Universidad de Ejemplo",
        "starts_on": start.isoformat(),
        "ends_on": end.isoformat(),
        "credits": 60,
        "tone": 2,
        "subjects": [
            {
                "name": "Redes neuronales",
                "credits": 6,
                "teacher": "Prof. Inventado",
                "schedule": [
                    {
                        "rule": {
                            "freq": "weekly",
                            "by_day": [{"weekday": "MO"}, {"weekday": "WE"}],
                            "until": end.isoformat(),
                        },
                        "starts_on": start.isoformat(),
                        "start_time": "16:00",
                        "end_time": "18:00",
                        "place": "Study 4",
                    }
                ],
                "assessments": [
                    {
                        "title": "Práctica 1",
                        "weight": 20,
                        "due_on": (today() + timedelta(days=10)).isoformat(),
                    },
                    {"title": "Práctica 2", "weight": 20},
                    {"title": "Examen", "kind": "exam", "weight": 60, "min_grade": 4},
                ],
            },
            {
                "name": "Ética de la IA",
                "credits": 3,
                "assessments": [{"title": "Ensayo", "weight": 100}],
            },
        ],
        "assessments": [{"title": "Defensa del TFM", "kind": "exam"}],
    }


async def test_claude_builds_a_course_from_a_guide_and_it_shows_in_the_app(api) -> None:
    response = await call(api, "create_course", a_guide())
    assert response.status_code == 200, response.text
    content = response.json()["content"]
    course_id = content["course"]["course_id"]

    assert content["sessions_created"] >= 25
    assert content["assessments"] == 5
    app = (await api.get(f"/courses/{course_id}")).json()
    assert [s["name"] for s in app["subjects"]] == ["Redes neuronales", "Ética de la IA"]
    schedules = (await api.get(f"/courses/{course_id}/schedules")).json()
    assert schedules[0]["phrase"].startswith("cada semana, lunes y miércoles")
    assert schedules[0]["subject"] == "Redes neuronales"


async def test_grades_read_the_same_for_claude_and_the_app(api) -> None:
    course_id = (await call(api, "create_course", a_guide())).json()["content"]["course"][
        "course_id"
    ]
    detail = (await api.get(f"/courses/{course_id}")).json()
    practice = next(a for a in detail["assessments"] if a["title"] == "Práctica 1")

    graded = await call(api, "record_grade", {"assessment_id": practice["id"], "grade": 7})
    assert graded.status_code == 200, graded.text

    subject_id = practice["subject_id"]
    claude = (await call(api, "get_grades", {"subject_id": subject_id}, READ)).json()["content"]
    app = (await api.get(f"/subjects/{subject_id}")).json()["subject"]["grade"]
    assert claude["grade"]["summary"] == app["sentence"]
    assert claude["grade"]["needed_to_pass"] == app["needed_to_pass"]


async def test_the_week_notes_and_attendance(api, notebook) -> None:
    await call(api, "create_course", a_guide())
    week = (await call(api, "get_week", {}, READ)).json()["content"]
    first = week["sessions"][0]

    noted = await call(
        api, "add_note", {"session_id": first["session_id"], "body": "Retropropagación y gradiente"}
    )
    marked = await call(
        api, "mark_attendance", {"session_id": first["session_id"], "attendance": "present"}
    )
    found = (await call(api, "find_notes", {"query": "gradientes"}, READ)).json()["content"]
    courses = (await call(api, "get_courses", {}, READ)).json()["content"]["courses"]

    assert noted.status_code == 200, noted.text
    assert marked.json()["content"]["session"]["attendance"] == "present"
    assert found["notes"][0]["subject"] == "Redes neuronales"
    assert courses[0]["name"] == "Máster en Inteligencia Artificial"
    assert [s["name"] for s in courses[0]["subjects"]] == ["Redes neuronales", "Ética de la IA"]


async def test_reading_scope_cannot_write(api) -> None:
    refused = await call(api, "create_course", a_guide(), READ)

    assert refused.status_code == 403


async def test_without_an_study_scope_nothing_runs(api) -> None:
    assert (
        await call(api, "get_courses", {}, {"x-arga-scopes": "library:read"})
    ).status_code == 403


async def test_the_widgets_show_the_current_course(api) -> None:
    course_id = (await call(api, "create_course", a_guide())).json()["content"]["course"][
        "course_id"
    ]
    detail = (await api.get(f"/courses/{course_id}")).json()
    ethics = next(s for s in detail["subjects"] if s["name"] == "Ética de la IA")
    await call(api, "record_grade", {"subject_id": ethics["id"], "grade": 9})

    progress = (await api.get("/widgets/progress")).json()
    average = (await api.get("/widgets/average")).json()
    upnext = (await api.get("/widgets/upnext")).json()

    assert progress["body"] == {
        "value": 3.0,
        "target": 60.0,
        "unit": "créditos",
        "label": "Máster en Inteligencia Artificial",
    }
    assert average["body"]["value"] == "9"
    assert upnext["state"] == "ready"
    assert upnext["body"]["events"]
