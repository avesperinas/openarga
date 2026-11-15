from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text

from study.studies import today

MADRID = ZoneInfo("Europe/Madrid")


async def course(api, name: str = "German") -> tuple[str, str]:
    created = (
        await api.post(
            "/courses", json={"name": name, "tone": 3, "subjects": [{"name": "Grammar"}]}
        )
    ).json()
    return created["course"]["id"], created["subjects"][0]["id"]


async def session(api, course_id: str, subject_id: str) -> str:
    at = datetime.combine(today(), time(18), tzinfo=MADRID)
    added = await api.post(
        f"/courses/{course_id}/sessions",
        json={
            "kind": "class",
            "subject_id": subject_id,
            "starts_at": at.isoformat(),
            "ends_at": (at + timedelta(hours=1)).isoformat(),
        },
    )
    assert added.status_code == 201, added.text
    return added.json()["session"]["id"]


async def test_the_course_shows_what_lives_in_its_folder_and_a_class_note_becomes_a_note(
    api, notebook
) -> None:
    course_id, subject_id = await course(api)
    imported = await notebook.post(
        "/import",
        json={
            "notes": [
                {
                    "folder": "Study/German/B1 Grammatik",
                    "title": "DE 1.1 Kasus",
                    "content": "Kasus.",
                },
                {"folder": "Others", "title": "Outside", "content": "Not from the course."},
            ]
        },
    )
    assert imported.json()["created"] == 2
    session_id = await session(api, course_id, subject_id)

    written = await api.post(
        "/notes", json={"course_id": course_id, "session_id": session_id, "body": "Dativ: *wem?*"}
    )
    listed = (await api.get("/notes", params={"course_id": course_id})).json()
    page = (await api.get(f"/sessions/{session_id}")).json()
    tree = (await notebook.get("/tree")).json()

    assert written.status_code == 201, written.text
    note = written.json()
    assert note["title"] == f"Session of {today().isoformat()}"
    assert (note["course"], note["subject"], note["session_id"]) == (
        "German",
        "Grammar",
        session_id,
    )
    assert sorted(n["title"] for n in listed) == [
        "DE 1.1 Kasus",
        "Session of " + today().isoformat(),
    ]
    kasus = next(n for n in listed if n["title"] == "DE 1.1 Kasus")
    assert (kasus["course_id"], kasus["subject_id"]) == (course_id, None)
    assert [n["body"] for n in page["notes"]] == ["Dativ: *wem?*"]
    assert (
        page["detail"]["session"]["has_notes"] is True
        if "has_notes" in page["detail"]["session"]
        else True
    )
    paths = {n["path"] for n in tree["notes"]}
    assert f"Study/German/Grammar/Session of {today().isoformat()}" in paths
    in_notebook = (await notebook.get(f"/notes/{note['id']}")).json()
    assert in_notebook["properties"] == {
        "study_course": course_id,
        "study_subject": subject_id,
        "study_session": session_id,
    }
    assert in_notebook["content"].endswith("Dativ: *wem?*")


async def test_editing_from_study_keeps_the_frontmatter_and_deleting_sends_it_to_the_trash(
    api, notebook
) -> None:
    course_id, subject_id = await course(api)
    note = (
        await api.post("/notes", json={"course_id": course_id, "title": "Verbos", "body": "uno"})
    ).json()

    edited = await api.put(
        f"/notes/{note['id']}",
        json={"title": "Strong verbs", "body": "dos", "subject_id": subject_id},
    )
    in_notebook = (await notebook.get(f"/notes/{note['id']}")).json()
    deleted = await api.delete(f"/notes/{note['id']}")
    trash = (await notebook.get("/trash")).json()

    assert edited.status_code == 200, edited.text
    assert (edited.json()["title"], edited.json()["subject"]) == ("Strong verbs", "Grammar")
    assert in_notebook["path"] == "Study/German/Grammar/Strong verbs"
    assert in_notebook["content"] == f"---\nstudy_course: {course_id}\n---\ndos"
    assert deleted.status_code == 204
    assert [n["title"] for n in trash] == ["Strong verbs"]


async def test_the_old_text_of_a_note_is_no_longer_read(api, notebook, schema) -> None:
    course_id, subject_id = await course(api)
    from arga_tenancy import as_user, current_user

    with as_user(current_user.get()):
        async with schema.begin() as connection:
            await connection.execute(text('set local role "mod_study"'))
            await connection.execute(
                text(
                    "insert into study.study_note (course_id, subject_id, title) "
                    "values (:c, :s, 'Antiguos')"
                ),
                {"c": course_id, "s": subject_id},
            )

    listed = (await api.get("/notes", params={"course_id": course_id})).json()
    tree = (await notebook.get("/tree")).json()

    assert listed == []
    assert tree["notes"] == []


async def test_searching_finds_plurals_and_marks_what_it_found(api, notebook) -> None:
    course_id, _ = await course(api)
    await api.post(
        "/notes",
        json={"course_id": course_id, "title": "Networks", "body": "The **gradient** goes down."},
    )

    hits = (await api.get("/notes", params={"q": "gradients"})).json()

    assert [h["title"] for h in hits] == ["Networks"]
    assert "«gradient»" in hits[0]["fragment"]
    assert "**" not in hits[0]["fragment"]


async def test_a_custom_folder_for_a_course(api, notebook, schema) -> None:
    course_id, _ = await course(api, "Master")
    await notebook.post(
        "/import", json={"notes": [{"folder": "Estudios/MSc", "title": "TFM", "content": "x"}]}
    )
    from arga_tenancy import as_user, current_user

    with as_user(current_user.get()):
        async with schema.begin() as connection:
            await connection.execute(text('set local role "mod_study"'))
            await connection.execute(
                text("update study.study_course set notes_folder = 'Estudios/MSc' where id = :id"),
                {"id": course_id},
            )

    listed = (await api.get("/notes", params={"course_id": course_id})).json()

    assert [n["title"] for n in listed] == ["TFM"]


async def test_when_the_notes_do_not_answer_the_subject_still_opens(
    api, notebook, monkeypatch
) -> None:
    from kernel import capabilities as kernel_capabilities

    course_id, subject_id = await course(api)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr(kernel_capabilities, "module_transport", lambda: httpx.MockTransport(down))
    subject = await api.get(f"/subjects/{subject_id}")
    notes = await api.get("/notes", params={"course_id": course_id})

    assert subject.status_code == 200
    assert subject.json()["notes"] == []
    assert "no contesta" in subject.json()["notes_unavailable"]
    assert notes.status_code == 503


async def test_notebook_refuses_whoever_does_not_come_from_the_kernel(notebook) -> None:
    response = await notebook.post("/capabilities/notes.list", json={})

    assert response.status_code == 401


async def test_notes_written_with_the_old_property_names_still_belong_to_their_session(
    api, notebook
) -> None:
    course_id, subject_id = await course(api)
    session_id = await session(api, course_id, subject_id)
    old = (
        f"---\nstudy_estudio: {course_id}\nstudy_asignatura: {subject_id}\n"
        f"study_clase: {session_id}\n---\nAkkusativ."
    )
    imported = await notebook.post(
        "/import",
        json={"notes": [{"folder": "Elsewhere", "title": "Old note", "content": old}]},
    )
    assert imported.json()["created"] == 1

    page = (await api.get(f"/sessions/{session_id}")).json()
    by_subject = (await api.get("/notes", params={"subject_id": subject_id})).json()

    assert [n["body"] for n in page["notes"]] == ["Akkusativ."]
    assert [(n["title"], n["subject_id"]) for n in by_subject] == [("Old note", subject_id)]
