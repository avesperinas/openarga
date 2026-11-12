from __future__ import annotations

from datetime import timedelta

from test_study_tools import READ, a_guide, call

from study.studies import today


async def a_course(api) -> dict:
    content = (await call(api, "create_course", a_guide())).json()["content"]
    return (
        await call(api, "get_course", {"course_id": content["course"]["course_id"]}, READ)
    ).json()["content"]


async def test_editing_a_course_changes_only_what_is_said(api, notebook) -> None:
    course = (await a_course(api))["course"]

    edited = await call(
        api,
        "update_course",
        {"course_id": course["course_id"], "name": "Máster en IA", "hours": 1500},
    )
    cleared = await call(
        api, "update_course", {"course_id": course["course_id"], "institution": None}
    )
    app = (await api.get(f"/courses/{course['course_id']}")).json()["course"]

    assert edited.status_code == 200, edited.text
    assert cleared.status_code == 200, cleared.text
    assert app["name"] == "Máster en IA"
    assert app["hours"] == 1500
    assert app["institution"] is None
    assert app["credits"] == 60
    assert app["tone"] == 2
    assert app["starts_on"] == course["starts_on"]


async def test_an_edit_that_does_not_add_up_is_a_conflict_not_a_crash(api, notebook) -> None:
    course = (await a_course(api))["course"]
    before = (today() - timedelta(days=400)).isoformat()

    refused = await call(
        api, "update_course", {"course_id": course["course_id"], "ends_on": before}
    )

    assert refused.status_code == 409
    assert "antes de empezar" in refused.json()["detail"]


async def test_archiving_and_reopening_a_course(api, notebook) -> None:
    course_id = (await a_course(api))["course"]["course_id"]

    archived = await call(
        api, "archive_course", {"course_id": course_id, "outcome": "finished", "final_grade": 8.5}
    )
    current = (await call(api, "get_courses", {}, READ)).json()["content"]["courses"]
    archive = (await call(api, "get_courses", {"scope": "archive"}, READ)).json()["content"]
    reopened = await call(api, "reopen_course", {"course_id": course_id})

    assert archived.json()["content"]["course"]["status"] == "finished"
    assert current == []
    assert archive["courses"][0]["final_grade"] == 8.5
    assert reopened.json()["content"]["course"]["status"] == "active"


async def test_deleting_a_course_asks_for_its_name(api, notebook) -> None:
    course = (await a_course(api))["course"]

    wrong = (
        await call(api, "delete_course", {"course_id": course["course_id"], "name": "Otro máster"})
    ).json()["content"]
    still = await api.get(f"/courses/{course['course_id']}")
    right = (
        await call(
            api,
            "delete_course",
            {"course_id": course["course_id"], "name": "máster en inteligencia artificial"},
        )
    ).json()["content"]
    gone = await api.get(f"/courses/{course['course_id']}")

    assert wrong["deleted"] is None
    assert "Máster en Inteligencia Artificial" in wrong["note"]
    assert still.status_code == 200
    assert right["deleted"]["subjects"] == 2
    assert gone.status_code == 404


async def test_subjects_are_added_edited_moved_and_deleted(api, notebook) -> None:
    course = await a_course(api)
    course_id = course["course"]["course_id"]

    added = (
        await call(
            api,
            "add_subject",
            {
                "course_id": course_id,
                "name": "Visión por computador",
                "credits": 4.5,
                "assessments": [{"title": "Proyecto", "weight": 100}],
            },
        )
    ).json()["content"]
    moved = (
        await call(
            api,
            "update_subject",
            {"subject_id": added["subject_id"], "teacher": "Prof. Ficticia", "position": 0},
        )
    ).json()["content"]
    names = [s["name"] for s in (await api.get(f"/courses/{course_id}")).json()["subjects"]]
    ethics = next(s for s in course["subjects"] if s["name"] == "Ética de la IA")
    deleted = (
        await call(
            api, "delete_subject", {"subject_id": ethics["subject_id"], "name": "Ética de la IA"}
        )
    ).json()["content"]
    after = [s["name"] for s in (await api.get(f"/courses/{course_id}")).json()["subjects"]]

    assert added["assessments"] == 1
    assert moved["teacher"] == "Prof. Ficticia"
    assert moved["credits"] == 4.5
    assert names == ["Visión por computador", "Redes neuronales", "Ética de la IA"]
    assert deleted["deleted"]["name"] == "Ética de la IA"
    assert after == ["Visión por computador", "Redes neuronales"]


async def test_the_timetable_is_edited_block_by_block(api, notebook) -> None:
    course = await a_course(api)
    course_id = course["course"]["course_id"]
    block = course["schedules"][0]

    moved = (
        await call(
            api,
            "update_schedule",
            {"schedule_id": block["schedule_id"], "start_time": "17:00", "end_time": "19:00"},
        )
    ).json()["content"]["schedule"]
    added = await call(
        api,
        "add_schedule",
        {
            "course_id": course_id,
            "rule": {"freq": "weekly", "by_day": [{"weekday": "FR"}]},
            "starts_on": today().isoformat(),
            "start_time": "10:00",
            "end_time": "12:00",
            "place": "Laboratorio",
        },
    )
    removed = (
        await call(
            api,
            "delete_schedule",
            {"schedule_id": added.json()["content"]["schedule"]["schedule_id"]},
        )
    ).json()["content"]
    blocks = (await api.get(f"/courses/{course_id}/schedules")).json()

    assert moved["start_time"] == "17:00"
    assert moved["place"] == "Study 4"
    assert moved["repeats"] == block["repeats"]
    assert added.status_code == 200, added.text
    assert removed["deleted"]["removed_sessions"] >= 1
    assert [b["id"] for b in blocks] == [block["schedule_id"]]


async def test_a_class_is_moved_cancelled_and_given_a_topic(api, notebook) -> None:
    await a_course(api)
    first = (await call(api, "get_week", {}, READ)).json()["content"]["sessions"][0]

    topic = (
        await call(api, "update_session", {"session_id": first["session_id"], "topic": "Backprop"})
    ).json()["content"]["session"]
    cancelled = (
        await call(
            api, "update_session", {"session_id": first["session_id"], "status": "cancelled"}
        )
    ).json()["content"]["session"]
    refused = await call(api, "delete_session", {"session_id": first["session_id"]})

    assert topic["topic"] == "Backprop"
    assert topic["starts_at"] == first["starts_at"]
    assert cancelled["status"] == "cancelled"
    assert cancelled["topic"] == "Backprop"
    assert cancelled["place"] == "Study 4"
    assert refused.status_code == 409


async def test_a_loose_session_is_added_moved_and_deleted(api, notebook) -> None:
    course_id = (await a_course(api))["course"]["course_id"]
    day = today() + timedelta(days=3)

    added = (
        await call(
            api,
            "add_session",
            {
                "course_id": course_id,
                "kind": "tutorial",
                "title": "Tutoría del TFM",
                "starts_at": f"{day.isoformat()}T12:00:00",
                "ends_at": f"{day.isoformat()}T12:30:00",
            },
        )
    ).json()["content"]["session"]
    moved = (
        await call(
            api,
            "update_session",
            {"session_id": added["session_id"], "starts_at": f"{day.isoformat()}T13:00:00"},
        )
    ).json()["content"]["session"]
    deleted = await call(api, "delete_session", {"session_id": added["session_id"]})
    gone = await api.get(f"/sessions/{added['session_id']}")

    assert added["starts_at"].startswith(f"{day.isoformat()}T12:00:00")
    assert moved["starts_at"].startswith(f"{day.isoformat()}T13:00:00")
    assert moved["ends_at"].startswith(f"{day.isoformat()}T13:30:00")
    assert moved["title"] == "Tutoría del TFM"
    assert deleted.status_code == 200, deleted.text
    assert gone.status_code == 404


async def test_an_assessment_is_edited_and_deleted_by_its_title(api, notebook) -> None:
    course = await a_course(api)
    practice = next(a for a in course["assessments"] if a["title"] == "Práctica 1")
    await call(api, "record_grade", {"assessment_id": practice["assessment_id"], "grade": 7})

    edited = (
        await call(
            api,
            "update_assessment",
            {"assessment_id": practice["assessment_id"], "weight": 25, "due_on": None},
        )
    ).json()["content"]["assessment"]
    wrong = (
        await call(
            api,
            "delete_assessment",
            {"assessment_id": practice["assessment_id"], "title": "Examen"},
        )
    ).json()["content"]
    right = (
        await call(
            api,
            "delete_assessment",
            {"assessment_id": practice["assessment_id"], "title": "Práctica 1"},
        )
    ).json()["content"]
    gone = await api.get(f"/assessments/{practice['assessment_id']}")

    assert edited["weight_percent"] == 25
    assert edited["due_on"] is None
    assert edited["grade"] == 7
    assert edited["status"] == "graded"
    assert edited["title"] == "Práctica 1"
    assert wrong["deleted"] is None
    assert right["deleted"]["title"] == "Práctica 1"
    assert gone.status_code == 404


async def test_notes_are_read_whole_extended_and_sent_to_the_bin(api, notebook) -> None:
    course = await a_course(api)
    subject = next(s for s in course["subjects"] if s["name"] == "Redes neuronales")
    note_id = (
        await call(
            api,
            "add_note",
            {"subject_id": subject["subject_id"], "title": "Tema 1", "body": "Perceptrón."},
        )
    ).json()["content"]["note_id"]

    extended = await call(
        api, "update_note", {"note_id": note_id, "append": "Descenso de gradiente."}
    )
    whole = (await call(api, "get_note", {"note_id": note_id}, READ)).json()["content"]
    listed = (
        await call(api, "get_course", {"course_id": course["course"]["course_id"]}, READ)
    ).json()["content"]["notes"]
    binned = await call(api, "delete_note", {"note_id": note_id})
    gone = await api.get(f"/notes/{note_id}")

    assert extended.status_code == 200, extended.text
    assert whole["body"] == "Perceptrón.\n\nDescenso de gradiente."
    assert whole["title"] == "Tema 1"
    assert whole["subject"] == "Redes neuronales"
    assert [n["note_id"] for n in listed] == [note_id]
    assert binned.status_code == 200, binned.text
    assert gone.status_code == 404


async def test_materials_are_links_added_and_removed(api, notebook) -> None:
    course_id = (await a_course(api))["course"]["course_id"]

    added = (
        await call(
            api,
            "add_material",
            {"course_id": course_id, "title": "Guía docente", "url": "example.org/guia"},
        )
    ).json()["content"]["material"]
    removed = await call(api, "delete_material", {"material_id": added["material_id"]})
    left = (await api.get(f"/courses/{course_id}/materials")).json()

    assert added["url"] == "https://example.org/guia"
    assert removed.status_code == 200, removed.text
    assert left == []


async def test_reading_scope_cannot_edit_archive_or_delete(api, notebook) -> None:
    course = (await a_course(api))["course"]
    course_id = course["course_id"]

    for name, body in (
        ("update_course", {"course_id": course_id, "name": "Otro"}),
        ("archive_course", {"course_id": course_id, "outcome": "abandoned"}),
        ("delete_course", {"course_id": course_id, "name": course["name"]}),
    ):
        assert (await call(api, name, body, READ)).status_code == 403, name


async def test_renaming_a_course_keeps_its_notes(api, notebook) -> None:
    course = await a_course(api)
    course_id = course["course"]["course_id"]
    note_id = (
        await call(api, "add_note", {"course_id": course_id, "body": "Bibliografía."})
    ).json()["content"]["note_id"]

    await call(api, "update_course", {"course_id": course_id, "name": "Máster en IA"})
    listed = (await call(api, "get_course", {"course_id": course_id}, READ)).json()["content"]
    new = (await call(api, "add_note", {"course_id": course_id, "body": "Otra."})).json()["content"]

    assert note_id in [n["note_id"] for n in listed["notes"]]
    assert new["course"] == "Máster en IA"
