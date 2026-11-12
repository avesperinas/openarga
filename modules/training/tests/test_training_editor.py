from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import install
from training import db
from training.main import MODULE_ID, app

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)


@pytest.fixture
async def api(database_url: str):

    from arga_testing import fresh_modules

    engine = install(create_async_engine(database_url))
    async with engine.begin() as connection:
        await fresh_modules(connection, MODULE_ID, root=ROOT)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as client:
        yield client
    async with engine.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": MODULE_ID})
    await engine.dispose()
    await db.engine().dispose()
    db.engine.cache_clear()


async def exercise(api, name: str, implement: str = "barbell", pattern: str = "isolation") -> str:
    response = await api.post(
        "/exercises",
        json={
            "name": name,
            "pattern": pattern,
            "muscles": {"chest": 1.0},
            "variant": {"name": f"{name} ({implement})", "implement": implement},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["variants"][0]["id"]


def day(name: str, kind: str, *variants: list[str]) -> dict:
    return {
        "name": name,
        "kind": kind,
        "slots": [
            {"target_sets": 3, "rep_min": 6, "rep_max": 10, "variant_ids": ids} for ids in variants
        ],
    }


async def test_with_nothing_everything_answers_empty_and_not_broken(api) -> None:
    editor = (await api.get("/plan")).json()
    catalogue = (await api.get("/catalogue")).json()
    history = (await api.get("/sessions")).json()
    today = (await api.get("/today")).json()

    assert editor == {"plan": None, "published": None, "draft": None, "rotation_version": None}
    assert catalogue["exercises"] == [] and catalogue["gyms"] == []
    assert len(catalogue["muscles"]) > 10
    assert history == []
    assert today["rotation"] is None


async def test_from_zero_to_training_a_plan_made_in_the_app(api) -> None:
    created = await api.post("/plan", json={"name": "Torso pierna"})
    assert created.status_code == 201
    assert created.json()["draft"]["number"] == 1

    press = await exercise(api, "Press banca", pattern="horizontal_push")
    squat = await exercise(api, "Sentadilla", pattern="knee_dominant")
    leg_press = (
        await api.post(
            f"/exercises/{(await api.get('/catalogue')).json()['exercises'][1]['id']}/variants",
            json={"name": "Prensa", "implement": "machine"},
        )
    ).json()
    assert leg_press["min_increment"] == 5

    saved = await api.put(
        "/plan/draft",
        json={
            "days": [day("Torso", "push", [press]), day("Pierna", "leg", [squat, leg_press["id"]])]
        },
    )
    assert [d["name"] for d in saved.json()["draft"]["days"]] == ["Torso", "Pierna"]

    published = (await api.post("/plan/draft/publish")).json()
    assert published["draft"] is None and published["published"]["number"] == 1

    today = (await api.get("/today")).json()
    assert today["next"]["name"] == "Torso"
    assert [d["name"] for d in today["rotation"]["days"]] == ["Torso", "Pierna"]


async def test_a_plan_cannot_be_published_with_an_empty_day(api) -> None:
    await api.post("/plan", json={"name": "Plan"})
    press = await exercise(api, "Press banca")
    await api.put(
        "/plan/draft", json={"days": [day("Torso", "push", [press]), day("Vacío", "other")]}
    )

    response = await api.post("/plan/draft/publish")

    assert response.status_code == 409
    assert "Vacío" in response.json()["detail"]


async def test_editing_copies_the_plan_and_the_past_keeps_its_version(api) -> None:
    await api.post("/plan", json={"name": "Plan"})
    press = await exercise(api, "Press banca")
    curl = await exercise(api, "Curl")
    await api.put("/plan/draft", json={"days": [day("Torso", "push", [press])]})
    await api.post("/plan/draft/publish")
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]

    draft = (await api.post("/plan/draft")).json()["draft"]
    assert draft["number"] == 2
    assert [s["options"][0]["variant_id"] for s in draft["days"][0]["slots"]] == [press]

    await api.put("/plan/draft", json={"days": [day("Torso", "push", [press], [curl])]})
    after = (await api.post("/plan/draft/publish")).json()

    assert after["published"]["number"] == 2
    assert after["rotation_version"] == 1
    assert len((await api.get(f"/sessions/{session}")).json()["slots"]) == 1


async def test_a_draft_can_be_discarded(api) -> None:
    await api.post("/plan", json={"name": "Plan"})
    press = await exercise(api, "Press banca")
    await api.put("/plan/draft", json={"days": [day("Torso", "push", [press])]})
    await api.post("/plan/draft/publish")
    await api.post("/plan/draft")

    after = (await api.delete("/plan/draft")).json()

    assert after["draft"] is None and after["published"]["number"] == 1


async def test_names_repeated_and_unknown_variants_are_refused_with_a_reason(api) -> None:
    await api.post("/plan", json={"name": "Plan"})
    await exercise(api, "Press banca")

    repeated = await api.post(
        "/exercises",
        json={
            "name": "press BANCA",
            "pattern": "isolation",
            "variant": {"name": "x", "implement": "cable"},
        },
    )
    unknown = await api.put(
        "/plan/draft",
        json={"days": [day("Torso", "push", ["00000000-0000-0000-0000-000000000000"])]},
    )
    backwards = await api.put(
        "/plan/draft",
        json={
            "days": [
                {
                    "name": "T",
                    "kind": "push",
                    "slots": [
                        {"target_sets": 3, "rep_min": 12, "rep_max": 6, "variant_ids": ["x"]}
                    ],
                }
            ]
        },
    )

    assert repeated.status_code == 409
    assert unknown.status_code == 409
    assert backwards.status_code == 422


async def test_a_second_plan_is_not_created_on_top_of_the_first(api) -> None:
    await api.post("/plan", json={"name": "Plan"})

    assert (await api.post("/plan", json={"name": "Otro"})).status_code == 409


async def test_gyms_and_weekly_goal(api) -> None:
    gym = (await api.post("/gyms", json={"name": "Centro"})).json()
    goal = (await api.put("/settings", json={"weekly_goal": 4})).json()
    closed = (await api.put(f"/gyms/{gym['id']}", json={"name": "Centro", "active": False})).json()

    assert goal["weekly_goal"] == 4
    assert closed["active"] is False
    assert (await api.put("/settings", json={"weekly_goal": 0})).status_code == 422


async def published_plan(api) -> tuple[str, str]:
    await api.post("/plan", json={"name": "Plan"})
    press = await exercise(api, "Press banca")
    squat = await exercise(api, "Sentadilla")
    await api.put(
        "/plan/draft", json={"days": [day("Torso", "push", [press]), day("Pierna", "leg", [squat])]}
    )
    editor = (await api.post("/plan/draft/publish")).json()
    return tuple(d["id"] for d in editor["published"]["days"])  # type: ignore[return-value]


async def test_the_recommendation_does_not_force_the_day(api) -> None:
    _, legs = await published_plan(api)

    started = await api.post("/sessions", json={"started_at": T0.isoformat(), "plan_day_id": legs})
    session = (await api.get(f"/sessions/{started.json()['id']}")).json()

    assert session["day_name"] == "Pierna"
    assert (await api.post("/sessions", json={"plan_day_id": "nada"})).status_code == 409


async def test_history_lists_sessions_with_their_sets_most_recent_first(api) -> None:
    torso, legs = await published_plan(api)
    for offset, plan_day in ((0, torso), (2, legs)):
        start = T0 + timedelta(days=offset)
        sid = (
            await api.post(
                "/sessions", json={"started_at": start.isoformat(), "plan_day_id": plan_day}
            )
        ).json()["id"]
        detail = (await api.get(f"/sessions/{sid}")).json()
        slot = detail["slots"][0]
        eid = (
            await api.post(
                f"/sessions/{sid}/exercises",
                json={"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]},
            )
        ).json()["id"]
        for number in (1, 2):
            await api.put(
                f"/sessions/{sid}/exercises/{eid}/sets/{number}",
                json={"reps": 8, "weight": 60, "confirmed_at": start.isoformat()},
            )
        await api.post(
            f"/sessions/{sid}/finish", json={"ended_at": (start + timedelta(hours=1)).isoformat()}
        )

    history = (
        await api.get("/sessions", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json()
    outside = (
        await api.get("/sessions", params={"since": "2026-10-01", "until": "2026-10-31"})
    ).json()

    assert [(h["day"], h["day_name"], h["sets"], h["duration_seconds"]) for h in history] == [
        ("2026-09-16", "Pierna", 2, 3600),
        ("2026-09-14", "Torso", 2, 3600),
    ]
    assert outside == []


async def test_a_start_pressed_by_mistake_is_discarded_only_without_sets(api) -> None:
    await published_plan(api)
    sid = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]

    assert (await api.delete(f"/sessions/{sid}")).status_code == 204
    assert (await api.get("/today")).json()["in_progress"] is None


async def test_muscles_are_set_on_creation_and_can_be_corrected(api) -> None:
    await exercise(api, "Remo")
    remo = (await api.get("/catalogue")).json()["exercises"][0]
    assert remo["muscles"] == {"chest": 1.0}

    corrected = await api.put(
        f"/exercises/{remo['id']}/muscles", json={"muscles": {"upper_back": 1.0, "biceps": 0.5}}
    )
    unknown = await api.put(f"/exercises/{remo['id']}/muscles", json={"muscles": {"alas": 1.0}})
    wrong_level = await api.put(f"/exercises/{remo['id']}/muscles", json={"muscles": {"lats": 0.7}})

    two_primaries = await api.put(
        f"/exercises/{remo['id']}/muscles", json={"muscles": {"upper_back": 1.0, "lats": 1.0}}
    )

    assert corrected.json()["muscles"] == {"upper_back": 1.0, "biceps": 0.5}
    assert unknown.status_code == 409 and "alas" in unknown.json()["detail"]
    assert two_primaries.status_code == 422
    assert wrong_level.status_code == 422
    assert (await api.get("/catalogue")).json()["exercises"][0]["muscles"] == {
        "upper_back": 1.0,
        "biceps": 0.5,
    }


async def test_an_exercise_in_a_session_can_carry_a_note(api) -> None:
    await published_plan(api)
    sid = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    slot = (await api.get(f"/sessions/{sid}")).json()["slots"][0]
    eid = (
        await api.post(
            f"/sessions/{sid}/exercises",
            json={"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]},
        )
    ).json()["id"]

    saved = await api.put(f"/sessions/{sid}/exercises/{eid}/notes", json={"notes": " polea rara "})
    detail = (await api.get(f"/sessions/{sid}")).json()
    cleared = await api.put(f"/sessions/{sid}/exercises/{eid}/notes", json={"notes": ""})

    assert saved.json() == {"notes": "polea rara"}
    assert detail["exercises"][0]["notes"] == "polea rara"
    assert detail["source"] == "app"
    assert cleared.json() == {"notes": None}
    wrong = await api.put(
        f"/sessions/{sid}/exercises/00000000-0000-0000-0000-000000000000/notes", json={"notes": "x"}
    )
    assert wrong.status_code == 404


async def test_activities_live_apart_from_the_routine(api) -> None:
    climbing = (await api.post("/activity-types", json={"name": "Escalada"})).json()
    again = (await api.post("/activity-types", json={"name": " escalada "})).json()
    assert again["id"] == climbing["id"]

    logged = await api.post(
        "/activities",
        json={
            "activity_type_id": climbing["id"],
            "day": "2026-09-15",
            "duration_seconds": 5400,
            "notes": "bloque",
        },
    )
    assert logged.status_code == 201
    listed = (
        await api.get("/activities", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json()
    assert [(a["name"], a["day"], a["duration_seconds"]) for a in listed] == [
        ("Escalada", "2026-09-15", 5400)
    ]
    assert (
        await api.get("/sessions", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json() == []

    assert (await api.delete(f"/activities/{listed[0]['id']}")).status_code == 204
    assert (
        await api.get("/activities", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json() == []
    unknown = await api.post(
        "/activities",
        json={"activity_type_id": "00000000-0000-0000-0000-000000000000", "day": "2026-09-15"},
    )
    assert unknown.status_code == 409


async def train_one(api, day: int, plan_day: str | None = None) -> str:
    start = T0 + timedelta(days=day)
    body = {"started_at": start.isoformat()} | ({"plan_day_id": plan_day} if plan_day else {})
    sid = (await api.post("/sessions", json=body)).json()["id"]
    slot = (await api.get(f"/sessions/{sid}")).json()["slots"][0]
    eid = (
        await api.post(
            f"/sessions/{sid}/exercises",
            json={"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]},
        )
    ).json()["id"]
    for number in (1, 2, 3):
        await api.put(
            f"/sessions/{sid}/exercises/{eid}/sets/{number}",
            json={"reps": 8, "weight": 60, "confirmed_at": start.isoformat()},
        )
    return sid


async def test_a_session_with_sets_is_only_deleted_when_asked_explicitly(api, database_url) -> None:
    await published_plan(api)
    sid = await train_one(api, 0)

    refused = await api.delete(f"/sessions/{sid}")
    assert refused.status_code == 409 and "3 series" in refused.json()["detail"]
    assert (await api.get(f"/sessions/{sid}")).status_code == 200

    assert (await api.delete(f"/sessions/{sid}", params={"with_sets": "true"})).status_code == 204
    assert (await api.get(f"/sessions/{sid}")).status_code == 404
    engine = install(create_async_engine(database_url))
    async with engine.connect() as connection:
        leftovers = await connection.scalar(text("select count(*) from training.training_set_log"))
        event = await connection.scalar(
            text(
                "select payload from training.training_outbox where type = 'training.session_deleted'"
            )
        )
    await engine.dispose()
    assert leftovers == 0
    assert event["sets"] == 3


async def test_deleting_a_session_keeps_the_rotation_honest(api) -> None:
    torso, legs = await published_plan(api)
    first = await train_one(api, 0, torso)
    await api.post(
        f"/sessions/{first}/finish", json={"ended_at": (T0 + timedelta(hours=1)).isoformat()}
    )
    second = await train_one(api, 1, legs)
    await api.post(
        f"/sessions/{second}/finish",
        json={"ended_at": (T0 + timedelta(days=1, hours=1)).isoformat()},
    )
    assert (await api.get("/today")).json()["next"]["rotation_number"] == 2

    await api.delete(f"/sessions/{second}", params={"with_sets": "true"})
    today = (await api.get("/today")).json()
    assert (today["next"]["rotation_number"], today["next"]["name"]) == (1, "Pierna")

    await api.delete(f"/sessions/{first}", params={"with_sets": "true"})
    today = (await api.get("/today")).json()
    assert (today["next"]["rotation_number"], today["next"]["name"]) == (1, "Torso")
    assert (
        await api.get("/sessions", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json() == []


async def test_someone_who_never_changed_the_settings_sees_the_defaults_and_can_change_them(
    api,
) -> None:
    headers = {"x-arga-user": "0b7e3d51-2c4a-4f6e-9d8b-1a2c3e4f5a6b"}

    before = (await api.get("/today", headers=headers)).json()
    changed = await api.put("/settings", json={"weekly_goal": 3}, headers=headers)
    after = (await api.get("/today", headers=headers)).json()

    assert before["week"]["goal"] == 5
    assert changed.status_code == 200
    assert changed.json()["weekly_goal"] == 3
    assert after["week"]["goal"] == 3
    assert (await api.get("/today")).json()["week"]["goal"] == 5
