from __future__ import annotations

from sqlalchemy import text

import arga_contracts as contracts
from study import records
from study.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_study"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def test_a_course_its_subjects_and_its_class_days(api) -> None:
    created = (
        await api.post(
            "/courses",
            json={
                "name": "Máster sintético",
                "kind": "master",
                "institution": "Universidad de Ejemplo",
                "subjects": [{"name": "Óptica", "credits": 6, "teacher": "Dra. Ejemplo"}],
            },
        )
    ).json()
    course_id = created["course"]["id"]
    subject_id = created["subjects"][0]["id"]
    await api.post(
        f"/courses/{course_id}/sessions",
        json={
            "kind": "class",
            "subject_id": subject_id,
            "starts_at": "2026-09-28T18:00:00+02:00",
            "ends_at": "2026-09-28T20:00:00+02:00",
        },
    )
    await api.post(
        f"/courses/{course_id}/assessments",
        json={"subject_id": subject_id, "title": "Parcial", "kind": "exam", "due_on": "2026-10-15"},
    )

    found = await built()

    ficha = found[f"course:{course_id}"]
    assert ficha["title"] == "Máster sintético"
    assert ficha["folder"] == "Máster sintético"
    assert ficha["kind"] == "Máster" and ficha["href"] == f"/study/estudio/{course_id}"
    assert ficha["properties"]["centro"] == "Universidad de Ejemplo"
    assert f"- [[study:subject:{subject_id}|Óptica]] · 6 créditos · Dra. Ejemplo" in ficha["body"]
    assert "| Parcial | Examen | Óptica | 2026-10-15 | pendiente |" in ficha["body"]

    optics = found[f"subject:{subject_id}"]
    assert optics["folder"] == "Máster sintético/Óptica" and optics["title"] == "Óptica"
    assert optics["properties"]["profesor"] == "Dra. Ejemplo"
    assert "- 2026-09-28 18:00" in optics["body"]

    assert found["day:2026-09-28"]["body"] == (
        f"- Clase: [[study:subject:{subject_id}|Óptica]] · 18:00–20:00"
    )
    assert found["day:2026-10-15"]["body"] == (
        f"- Examen: Parcial · [[study:course:{course_id}|Máster sintético]]"
    )
