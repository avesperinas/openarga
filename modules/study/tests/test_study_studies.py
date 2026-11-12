from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from study.studies import today

MASTER = {
    "name": "Máster en Ciencia de Datos",
    "kind": "master",
    "institution": "Universidad Inventada",
    "modality": "hybrid",
    "starts_on": "2026-09-14",
    "ends_on": "2027-07-15",
    "credits": 60,
    "tone": 3,
    "campus_url": "campus.example.org",
    "subjects": [
        {"name": "Estadística", "credits": 6, "period": "1.er cuatrimestre"},
        {"name": "Aprendizaje automático", "credits": 6, "teacher": "Dra. Ejemplo"},
        {"name": "Visualización", "credits": 3},
        {"name": "Trabajo Fin de Máster", "credits": 15},
    ],
}


async def create(api, body=MASTER) -> dict:
    response = await api.post("/courses", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_master_with_four_subjects_is_created_at_once(api) -> None:
    created = await create(api)

    course = created["course"]
    assert course["name"] == "Máster en Ciencia de Datos"
    assert course["campus_url"] == "https://campus.example.org"
    assert course["pass_mark"] == 5
    assert [s["name"] for s in created["subjects"]] == [
        "Estadística",
        "Aprendizaje automático",
        "Visualización",
        "Trabajo Fin de Máster",
    ]
    assert course["progress"]["label"] == "0 de 60 créditos"
    home = (await api.get("/home")).json()
    assert [c["name"] for c in home["courses"]] == ["Máster en Ciencia de Datos"]
    assert len(home["days"]) == 7


async def test_a_hundred_point_scale_passes_at_fifty(api) -> None:
    created = await create(api, {"name": "Curso de inglés", "kind": "language", "scale_max": 100})

    assert created["course"]["pass_mark"] == 50


async def test_the_forms_explain_what_is_wrong(api) -> None:
    response = await api.post(
        "/courses", json={"name": "X", "starts_on": "2026-10-01", "ends_on": "2026-09-01"}
    )

    assert response.status_code == 422
    assert "antes de empezar" in response.text


async def test_with_forty_percent_graded_it_says_what_is_needed(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    stats = created["subjects"][0]["id"]

    for body in (
        {"title": "Práctica 1", "weight": 20, "grade": 6, "subject_id": stats},
        {"title": "Práctica 2", "weight": 20, "grade": 5, "subject_id": stats},
        {"title": "Examen final", "kind": "exam", "weight": 60, "subject_id": stats},
    ):
        response = await api.post(f"/courses/{course_id}/assessments", json=body)
        assert response.status_code == 201, response.text

    subject = (await api.get(f"/subjects/{stats}")).json()["subject"]
    assert subject["grade"]["verdict"] == "in_progress"
    assert subject["grade"]["current"] == 5.5
    assert subject["grade"]["remaining_weight"] == 60
    assert subject["grade"]["sentence"] == (
        "Necesitas un 4,7 de media en lo que queda (60 %) para aprobar."
    )

    ids = {a["title"]: a["id"] for a in (await api.get(f"/subjects/{stats}")).json()["assessments"]}
    first, second, exam = ids["Práctica 1"], ids["Práctica 2"], ids["Examen final"]
    await api.put(f"/assessments/{first}/grade", json={"grade": 0})
    await api.put(f"/assessments/{second}/grade", json={"grade": 0})
    subject = (await api.get(f"/subjects/{stats}")).json()["subject"]
    assert subject["grade"]["verdict"] == "in_progress"

    await api.put(
        f"/assessments/{first}",
        json={"title": "Práctica 1", "weight": 70, "grade": 0, "subject_id": stats},
    )
    await api.put(
        f"/assessments/{second}",
        json={"title": "Práctica 2", "weight": 0.01, "grade": 0, "subject_id": stats},
    )
    await api.put(
        f"/assessments/{exam}",
        json={"title": "Examen final", "kind": "exam", "weight": 29.99, "subject_id": stats},
    )
    subject = (await api.get(f"/subjects/{stats}")).json()["subject"]
    assert subject["grade"]["verdict"] == "impossible"
    assert subject["grade"]["sentence"].startswith("Aprobar ya no es posible")


async def test_the_record_grade_rules_and_feeds_the_average_by_credits(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    stats, ml = created["subjects"][0]["id"], created["subjects"][1]["id"]

    await api.put(f"/subjects/{stats}/record", json={"final_grade": 8})
    await api.post(
        f"/courses/{course_id}/assessments",
        json={"title": "Proyecto", "weight": 100, "grade": 6, "subject_id": ml},
    )

    course = (await api.get(f"/courses/{course_id}")).json()["course"]
    assert course["average"]["average"] == 7.0
    assert course["average"]["counted"] == 2
    assert course["progress"]["label"] == "12 de 60 créditos"


async def test_a_grade_above_the_scale_is_refused(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]

    response = await api.post(f"/courses/{course_id}/assessments", json={"title": "X", "grade": 11})

    assert response.status_code == 409
    assert "no puede pasar de 10" in response.json()["detail"]


async def test_upcoming_deadlines_count_down_on_the_home(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    soon = today() + timedelta(days=3)
    await api.post(
        f"/courses/{course_id}/assessments",
        json={"title": "Entrega 1", "due_on": soon.isoformat(), "due_time": "23:59"},
    )
    await api.post(f"/courses/{course_id}/assessments", json={"title": "Sin fecha"})

    home = (await api.get("/home")).json()

    assert [(a["title"], a["days_left"]) for a in home["upcoming"]] == [("Entrega 1", 3)]
    window = await api.get(
        "/assessments",
        params={"from": today().isoformat(), "to": (soon + timedelta(days=1)).isoformat()},
    )
    assert [a["title"] for a in window.json()] == ["Entrega 1"]


async def test_finishing_sends_it_to_the_archive_and_reopening_brings_it_back(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]

    closed = await api.post(
        f"/courses/{course_id}/close", json={"status": "finished", "final_grade": 8.4}
    )
    assert closed.status_code == 200, closed.text
    assert (await api.get("/courses")).json() == []
    archive = (await api.get("/courses?scope=archive")).json()
    assert [(c["name"], c["status"], c["average"]["average"]) for c in archive] == [
        ("Máster en Ciencia de Datos", "finished", 8.4)
    ]
    assert (await api.get("/home")).json()["archived"] == 1

    await api.post(f"/courses/{course_id}/reopen")
    assert [c["status"] for c in (await api.get("/courses")).json()] == ["active"]


async def test_the_certificate_is_kept_and_served(api) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    pdf = b"%PDF-1.4 un certificado inventado"

    saved = await api.put(
        f"/courses/{course_id}/certificate?filename=titulo.pdf",
        content=pdf,
        headers={"content-type": "application/pdf"},
    )
    assert saved.status_code == 201, saved.text
    served = await api.get(f"/attachments/{saved.json()['id']}")

    assert served.content == pdf
    assert served.headers["content-type"] == "application/pdf"
    course = (await api.get(f"/courses/{course_id}")).json()["course"]
    assert (course["has_certificate"], course["certificate_name"]) == (True, "titulo.pdf")
    assert (await api.get(f"/courses/{course_id}/certificate")).content == pdf


async def test_what_changes_goes_to_the_outbox_with_the_common_shape(api, schema) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    await api.post(
        f"/courses/{course_id}/assessments",
        json={
            "title": "Examen parcial",
            "kind": "exam",
            "due_on": "2026-11-10",
            "due_time": "10:00",
        },
    )

    async with schema.begin() as connection:
        rows = (
            await connection.execute(
                text("select type, payload from study.study_outbox order by id")
            )
        ).all()
    types = [row.type for row in rows]
    assert types[0] == "study.course"
    agenda = rows[-1].payload["agenda"]
    assert agenda["title"] == "Examen: Examen parcial"
    assert agenda["start"] == "2026-11-10T10:00:00+01:00"
    assert agenda["href"].startswith("/study/evaluable/")


async def test_deleting_a_course_takes_everything_with_it(api, notebook) -> None:
    created = await create(api)
    course_id = created["course"]["id"]
    await api.post("/notes", json={"course_id": course_id, "title": "Algo", "body": "texto"})

    assert (await api.delete(f"/courses/{course_id}")).status_code == 204
    assert (await api.get(f"/courses/{course_id}")).status_code == 404
    assert (await api.get("/notes")).json() == []


async def test_each_study_says_what_is_followed_and_a_language_starts_with_nothing(api) -> None:
    master = (await create(api))["course"]
    german = (await create(api, {"name": "Alemán", "kind": "language"}))["course"]

    assert master["tracks"] == ["grades", "progress", "attendance"]
    assert german["tracks"] == []

    average = (await api.get("/widgets/average")).json()
    assert "Alemán" not in str(average)

    body = {**{k: v for k, v in german.items() if k in ("name", "kind")}, "tracks": ["grades"]}
    changed = (await api.put(f"/courses/{german['id']}", json=body)).json()["course"]
    assert changed["tracks"] == ["grades"]
    untouched = (
        await api.put(f"/courses/{german['id']}", json={"name": "Alemán B2", "kind": "language"})
    ).json()["course"]
    assert (untouched["name"], untouched["tracks"]) == ("Alemán B2", ["grades"])

    refused = await api.post("/courses", json={"name": "X", "tracks": ["karma"]})
    assert refused.status_code == 422
