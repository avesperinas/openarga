from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import install
from training import db, seed
from training.main import MODULE_ID, app

MODULES = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
READ = {"x-arga-scopes": "training:read"}


@pytest.fixture
async def setup(database_url: str):
    from arga_testing import fresh_modules

    engine = install(create_async_engine(database_url))
    async with engine.begin() as connection:
        await fresh_modules(connection, MODULE_ID, root=MODULES)
        await connection.execute(text('set local role "mod_training"'))
        await seed.seed(connection)
    yield engine
    async with engine.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": MODULE_ID})
    await engine.dispose()
    await db.engine().dispose()
    db.engine.cache_clear()


@pytest.fixture
async def api(setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as client:
        yield client


async def train(api, *, reps: int = 8, weight: str = "60", day_offset: int = 0) -> str:
    started = T0 + timedelta(days=day_offset)
    session = (await api.post("/sessions", json={"started_at": started.isoformat()})).json()["id"]
    detail = (await api.get(f"/sessions/{session}")).json()
    for slot in detail["slots"]:
        exercise = (
            await api.post(
                f"/sessions/{session}/exercises",
                json={"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]},
            )
        ).json()["id"]
        await api.put(
            f"/sessions/{session}/exercises/{exercise}/sets/1",
            json={"reps": reps, "weight": weight, "confirmed_at": started.isoformat()},
        )
    await api.post(
        f"/sessions/{session}/finish",
        json={"ended_at": (started + timedelta(hours=1)).isoformat()},
    )
    return session


async def call(api, name: str, arguments: dict, headers: dict = READ):
    return await api.post(f"/tools/{name}", json=arguments, headers=headers)


async def test_the_listed_tools_are_the_ones_the_manifest_declares(api) -> None:
    import yaml

    manifest = yaml.safe_load((MODULES / MODULE_ID / "manifest.yaml").read_text())
    served = (await api.get("/tools")).json()

    assert {tool["name"] for tool in served} == {tool["name"] for tool in manifest["tools"]}
    assert all(tool["scope"] == f"{MODULE_ID}:read" for tool in manifest["tools"])
    assert {tool["name"] for tool in served} == {
        "find_exercises",
        "get_sessions",
        "get_progress",
        "summarise_training",
        "get_activities",
        "get_muscles",
    }
    assert all("properties" in tool["input_schema"] for tool in served)


async def test_without_a_scope_nothing_runs(api) -> None:
    assert (await call(api, "find_exercises", {}, headers={})).status_code == 403
    assert (
        await call(api, "find_exercises", {}, headers={"x-arga-scopes": "chuping:read"})
    ).status_code == 403


async def test_a_tool_that_does_not_exist_is_a_404(api) -> None:
    response = await call(api, "delete_everything", {})
    assert response.status_code == 404
    assert "delete_everything" in response.json()["detail"]


async def test_bad_arguments_are_a_422_and_not_a_500(api) -> None:
    assert (await call(api, "get_progress", {"variant_id": "not-a-uuid"})).status_code == 422
    assert (await call(api, "get_sessions", {"limit": 9999})).status_code == 422


async def test_the_index_translates_a_name_into_a_variant(api) -> None:
    response = await call(api, "find_exercises", {"query": "press"})

    assert response.status_code == 200, response.text
    variants = response.json()["content"]["variants"]
    assert variants, "the seeded catalogue has presses"
    found = variants[0]
    assert {"variant_id", "exercise", "variant", "implement", "pattern"} <= set(found)
    assert "press" in f"{found['exercise']} {found['variant']}".lower()


async def test_the_sessions_are_the_finished_ones_with_what_was_done(api) -> None:
    await train(api)

    sessions = (await call(api, "get_sessions", {"limit": 5})).json()["content"]["sessions"]

    assert len(sessions) == 1
    done = sessions[0]
    assert done["day"] == T0.date().isoformat()
    assert done["sets"] >= 1
    assert done["volume_kg"] > 0
    assert done["duration_minutes"] == 60
    assert "exercises" not in done

    with_sets = (await call(api, "get_sessions", {"limit": 5, "with_sets": True})).json()[
        "content"
    ]["sessions"][0]
    assert with_sets["exercises"]
    assert with_sets["exercises"][0]["sets"][0]["reps"] == 8


async def test_a_session_in_progress_is_not_answered_as_done(api) -> None:
    await api.post("/sessions", json={"started_at": T0.isoformat()})

    sessions = (await call(api, "get_sessions", {})).json()["content"]["sessions"]

    assert sessions == []


async def bench(api) -> str:
    found = (await call(api, "find_exercises", {"query": "bench"})).json()["content"]["variants"]
    return next(v["variant_id"] for v in found if v["variant"] == "Barbell bench press")


async def test_progress_is_per_variant_and_says_how_reliable_the_estimate_is(api) -> None:
    await train(api, reps=8, weight="60")
    variant = await bench(api)

    progress = (await call(api, "get_progress", {"variant_id": variant})).json()["content"]

    assert progress["variant"]["variant_id"] == variant
    best = progress["best_sets"][0]
    assert best["reps"] == 8
    assert best["load_kg"] == 60.0
    assert best["e1rm_kg"] == pytest.approx(76.0, abs=0.1)
    assert best["e1rm_reliable"] is True


async def test_an_estimate_over_ten_reps_is_marked_unreliable(api) -> None:
    await train(api, reps=12, weight="40")
    variant = await bench(api)

    best = (await call(api, "get_progress", {"variant_id": variant})).json()["content"]["best_sets"]

    assert best[0]["e1rm_reliable"] is False


async def test_a_variant_that_does_not_exist_answers_instead_of_failing(api) -> None:
    response = await call(
        api, "get_progress", {"variant_id": "00000000-0000-4000-8000-000000000000"}
    )

    assert response.status_code == 200
    assert response.json()["content"]["variant"] is None


async def test_counting_a_year_does_not_depend_on_how_many_fit_in_a_page(api) -> None:
    for offset in range(3):
        await train(api, day_offset=offset * 7)

    summary = (await call(api, "summarise_training", {"by": "year"})).json()["content"]

    assert summary["total_sessions"] == 3
    year = [bucket for bucket in summary["buckets"] if bucket["bucket"] == "2026"][0]
    assert year["sessions"] == 3
    assert year["hours"] == 3.0
    assert year["volume_kg"] > 0


async def test_a_truncated_list_says_how_many_there_really_are(api) -> None:
    for offset in range(3):
        await train(api, day_offset=offset * 7)

    page = (await call(api, "get_sessions", {"limit": 1})).json()["content"]

    assert page["returned"] == 1
    assert page["total"] == 3
    assert page["first_day"] and page["last_day"]


async def test_a_range_narrows_both_the_list_and_the_count(api) -> None:
    await train(api, day_offset=0)
    await train(api, day_offset=30)

    first = T0.date().isoformat()
    only_first = (await call(api, "get_sessions", {"since": first, "until": first})).json()[
        "content"
    ]

    assert only_first["total"] == 1
    assert only_first["sessions"][0]["day"] == first


async def test_it_groups_by_month_and_by_kind(api) -> None:
    await train(api, day_offset=0)

    by_month = (await call(api, "summarise_training", {"by": "month"})).json()["content"]
    by_kind = (await call(api, "summarise_training", {"by": "kind"})).json()["content"]

    assert by_month["buckets"][0]["bucket"] == T0.strftime("%Y-%m")
    assert by_kind["buckets"][0]["sessions"] == 1
    assert by_kind["buckets"][0]["bucket"] in {"push", "pull", "leg", "full", "other"}


async def test_progress_says_the_best_day_of_the_period(api) -> None:
    for offset, weight in enumerate(["60", "60", "60", "70"]):
        await train(api, reps=8, weight=weight, day_offset=offset)
    variant = await bench(api)

    progress = (await call(api, "get_progress", {"variant_id": variant})).json()["content"]

    assert progress["sessions"] >= 1
    assert progress["best"]["load_kg"] == 70.0


async def test_progress_says_where_each_day_was_and_whether_it_counts(api) -> None:
    await train(api, reps=8, weight="60")
    variant = await bench(api)

    progress = (await call(api, "get_progress", {"variant_id": variant})).json()["content"]

    (day,) = progress["best_sets"]
    assert day["gym"]
    assert day["counts"] is True
    assert day["why_not"] is None
    assert day["machine_changed"] is False
    assert progress["by_gym"][0]["sessions"] == 1


async def test_the_index_says_where_each_variant_was_trained(api) -> None:
    await train(api)

    found = (await call(api, "find_exercises", {"query": "bench"})).json()["content"]["variants"]

    trained = next(v for v in found if v["variant"] == "Barbell bench press")
    assert trained["trained_at"] == [seed.GYM]


async def test_muscles_come_with_their_sets_and_what_trained_them(api) -> None:
    await train(api, day_offset=0)
    day = T0.date().isoformat()

    content = (await call(api, "get_muscles", {"since": day, "until": day})).json()["content"]
    muscles = {muscle["muscle"]: muscle for muscle in content["muscles"]}

    assert muscles["chest"]["sets_per_week"] == 2
    assert muscles["triceps"]["sets_per_week"] == 0
    assert {e["exercise"] for e in muscles["chest"]["exercises"]} == {
        "Barbell bench press",
        "Weighted dips",
    }
    assert content["bodyweight_kg"] is None
    assert muscles["chest"]["strength_change_pct"] is None


async def test_activities_come_with_their_count_by_type(api) -> None:
    kind = (await api.post("/activity-types", json={"name": "Climbing"})).json()
    await api.post(
        "/activities",
        json={
            "activity_type_id": kind["id"],
            "day": T0.date().isoformat(),
            "duration_seconds": 5400,
        },
    )

    activities = (await call(api, "get_activities", {})).json()["content"]

    assert activities["total"] == 1
    assert activities["by_type"] == {"Climbing": 1}
    assert activities["activities"][0]["minutes"] == 90
