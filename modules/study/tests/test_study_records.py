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
                "name": "Synthetic master",
                "kind": "master",
                "institution": "Example University",
                "subjects": [{"name": "Optics", "credits": 6, "teacher": "Dr Example"}],
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
        json={"subject_id": subject_id, "title": "Midterm", "kind": "exam", "due_on": "2026-10-15"},
    )

    found = await built()

    card = found[f"course:{course_id}"]
    assert card["title"] == "Synthetic master"
    assert card["folder"] == "Synthetic master"
    assert card["kind"] == "Master" and card["href"] == f"/study/course/{course_id}"
    assert card["properties"]["institution"] == "Example University"
    assert f"- [[study:subject:{subject_id}|Optics]] · 6 credits · Dr Example" in card["body"]
    assert "| Midterm | Exam | Optics | 2026-10-15 | pending |" in card["body"]

    optics = found[f"subject:{subject_id}"]
    assert optics["folder"] == "Synthetic master/Optics" and optics["title"] == "Optics"
    assert optics["properties"]["teacher"] == "Dr Example"
    assert "- 2026-09-28 18:00" in optics["body"]

    assert found["day:2026-09-28"]["body"] == (
        f"- Session: [[study:subject:{subject_id}|Optics]] · 18:00–20:00"
    )
    assert found["day:2026-10-15"]["body"] == (
        f"- Exam: Midterm · [[study:course:{course_id}|Synthetic master]]"
    )
