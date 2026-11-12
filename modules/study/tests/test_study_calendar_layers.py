from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from study import outbox
from study.publisher import PUBLISHER
from study.studies import today


async def a_course(api, name: str) -> tuple[str, str]:
    created = (
        await api.post(
            "/courses",
            json={"name": name, "tone": 3, "subjects": [{"name": "Álgebra", "credits": 6}]},
        )
    ).json()
    return created["course"]["id"], created["subjects"][0]["id"]


async def with_class_and_exam(api, name: str) -> str:
    course_id, subject_id = await a_course(api, name)
    await api.post(
        f"/courses/{course_id}/schedules",
        json={
            "subject_id": subject_id,
            "rule": {"freq": "weekly", "count": 1},
            "starts_on": (today() + timedelta(days=1)).isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
        },
    )
    await api.post(
        f"/courses/{course_id}/assessments",
        json={
            "subject_id": subject_id,
            "title": "Parcial",
            "kind": "exam",
            "due_on": (today() + timedelta(days=5)).isoformat(),
        },
    )
    return course_id


async def last_layers(schema) -> dict[tuple[str, str], str]:
    async with schema.begin() as connection:
        rows = await connection.execute(
            text("""
                select distinct on (payload->'agenda'->>'uid')
                       type, payload->>'course_id' as course_id, payload->>'layer' as layer
                from study.study_outbox
                where payload ? 'agenda'
                order by payload->'agenda'->>'uid', id desc
            """)
        )
        return {(row.course_id, row.type): row.layer for row in rows}


async def test_each_course_asks_for_its_own_layer(api, schema) -> None:
    master = await with_class_and_exam(api, "Grado en Historia")
    german = await with_class_and_exam(api, "Inglés C1")

    assert await last_layers(schema) == {
        (master, "study.session"): "Grado en Historia",
        (master, "study.assessment"): "Grado en Historia",
        (german, "study.session"): "Inglés C1",
        (german, "study.assessment"): "Inglés C1",
    }


async def test_renaming_a_course_moves_its_things_to_the_new_layer(api, schema) -> None:
    course_id = await with_class_and_exam(api, "Inglés C1")
    current = (await api.get(f"/courses/{course_id}")).json()["course"]
    edit = {
        key: current[key]
        for key in ("kind", "modality", "status", "scale_max", "tone", "tz")
        if key in current
    }

    renamed = await api.put(f"/courses/{course_id}", json={**edit, "name": "Inglés C2"})

    assert renamed.status_code == 200, renamed.text
    assert set((await last_layers(schema)).values()) == {"Inglés C2"}


async def count_queued(schema) -> int:
    async with schema.begin() as connection:
        return int(await connection.scalar(text("select count(*) from study.study_outbox")))


async def test_what_was_published_before_layers_goes_to_its_course_once(api, schema) -> None:
    course_id = await with_class_and_exam(api, "Inglés C1")
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "update study.study_outbox "
                "set payload = payload - 'layer', dedup_hash = md5(dedup_hash)"
            )
        )

    async with PUBLISHER.as_module() as connection:
        await outbox.republish(connection)
    queued = await count_queued(schema)
    async with PUBLISHER.as_module() as connection:
        await outbox.republish(connection)

    assert await last_layers(schema) == {
        (course_id, "study.session"): "Inglés C1",
        (course_id, "study.assessment"): "Inglés C1",
    }
    assert await count_queued(schema) == queued


def test_a_long_name_is_cut_to_what_the_calendar_takes() -> None:
    layer = outbox.course_layer("Máster   universitario en " + "x" * 60)
    assert len(layer) == outbox.LAYER_MAX
    assert layer.startswith("Máster universitario en x")
