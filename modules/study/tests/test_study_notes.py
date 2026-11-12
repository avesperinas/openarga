from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from study.studies import today

MADRID = ZoneInfo("Europe/Madrid")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def course_with_a_class(api, name: str) -> tuple[str, str]:
    course_id = (await api.post("/courses", json={"name": name})).json()["course"]["id"]
    at = datetime.combine(today(), time(18), tzinfo=MADRID)
    session = await api.post(
        f"/courses/{course_id}/sessions",
        json={
            "kind": "class",
            "starts_at": at.isoformat(),
            "ends_at": (at + timedelta(hours=2)).isoformat(),
        },
    )
    return course_id, session.json()["session"]["id"]


async def test_a_word_finds_the_notes_of_a_class_in_another_course_with_its_fragment(
    api, notebook
) -> None:
    master, _ = await course_with_a_class(api, "Máster en Finanzas")
    other, class_id = await course_with_a_class(api, "Curso de Cálculo")
    await api.post(
        "/notes",
        json={"course_id": master, "title": "Presupuestos", "body": "Nada que ver con esto."},
    )
    written = await api.post(
        "/notes",
        json={
            "course_id": other,
            "session_id": class_id,
            "title": "Clase 3",
            "body": "# Límites\n\nHoy vimos **las derivadas** de funciones compuestas y la regla "
            "de la cadena, con muchos ejemplos.",
        },
    )
    assert written.status_code == 201, written.text

    hits = (await api.get("/notes", params={"q": "derivada"})).json()

    assert len(hits) == 1
    hit = hits[0]
    assert (hit["course"], hit["session_id"]) == ("Curso de Cálculo", class_id)
    assert "«derivadas»" in hit["fragment"]
    assert "**" not in hit["fragment"]


async def test_notes_are_edited_and_listed_newest_first(api, notebook) -> None:
    course_id, _ = await course_with_a_class(api, "Curso")
    first = (await api.post("/notes", json={"course_id": course_id, "title": "Uno"})).json()
    await api.post("/notes", json={"course_id": course_id, "title": "Dos"})

    edited = await api.put(f"/notes/{first['id']}", json={"title": "Uno bis", "body": "- a\n- b"})

    assert edited.json()["excerpt"] == "a b"
    assert [n["title"] for n in (await api.get("/notes")).json()] == ["Uno bis", "Dos"]


async def test_a_pasted_image_belongs_to_its_notes_and_goes_with_them(api, notebook) -> None:
    course_id, _ = await course_with_a_class(api, "Curso")
    image = await api.post(
        "/attachments?filename=pizarra.png", content=PNG, headers={"content-type": "image/png"}
    )
    assert image.status_code == 201, image.text
    url = image.json()["url"]
    note = (
        await api.post(
            "/notes",
            json={"course_id": course_id, "title": "Con foto", "body": f"![pizarra]({url})"},
        )
    ).json()

    assert (await api.get(url.removeprefix("/api/study"))).content == PNG
    await api.delete(f"/notes/{note['id']}")
    assert (await api.get(url.removeprefix("/api/study"))).status_code == 404


async def test_a_file_that_lies_about_its_type_is_not_served_as_that(api) -> None:
    html = b"<script>alert(1)</script>"
    saved = (
        await api.post(
            "/attachments?filename=x.png", content=html, headers={"content-type": "image/png"}
        )
    ).json()

    served = await api.get(f"/attachments/{saved['id']}")

    assert served.headers["content-type"] == "application/octet-stream"
    assert served.headers["content-disposition"].startswith("attachment")


async def test_materials_are_links_or_files(api) -> None:
    course_id, _ = await course_with_a_class(api, "Curso")
    link = await api.post(
        f"/courses/{course_id}/materials", json={"title": "Guía docente", "url": "example.org/guia"}
    )
    upload = await api.post(
        f"/courses/{course_id}/materials/file?filename=temario.pdf",
        content=b"%PDF-1.4 temario",
        headers={"content-type": "application/pdf"},
    )
    assert (link.status_code, upload.status_code) == (201, 201), upload.text

    found = (await api.get(f"/courses/{course_id}/materials")).json()

    assert {(m["title"], m["url"], m["filename"]) for m in found} == {
        ("Guía docente", "https://example.org/guia", None),
        ("temario.pdf", None, "temario.pdf"),
    }
    await api.delete(f"/materials/{upload.json()['id']}")
    assert len((await api.get(f"/courses/{course_id}/materials")).json()) == 1
