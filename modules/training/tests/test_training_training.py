from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from conftest import PERSON
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_contracts.records import Never
from arga_tenancy import install
from training import db, links, publisher, seed, training, widgets
from training.main import MODULE_ID, app

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
SUB = "3f6d2a81-9b4c-4e57-a1d0-6c8e2f5b7a93"


@pytest.fixture
async def setup(database_url: str):
    from arga_testing import fresh_modules

    engine = install(create_async_engine(database_url))
    async with engine.begin() as connection:
        for statement in (
            "delete from kernel.events where module = :m",
            "delete from kernel.users where cast(:m as text) is not null",
        ):
            await connection.execute(text(statement), {"m": MODULE_ID})
        await fresh_modules(connection, MODULE_ID, root=ROOT)
        await connection.execute(text('set local role "mod_training"'))
        await seed.seed(connection)
    yield engine
    async with engine.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": MODULE_ID})
        await connection.execute(
            text("delete from kernel.events where module = :m"), {"m": MODULE_ID}
        )
    await engine.dispose()
    await db.engine().dispose()
    db.engine.cache_clear()


@pytest.fixture
async def api(setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as client:
        yield client


async def scalar(engine, statement: str, **params):
    async with engine.connect() as connection:
        return await connection.scalar(text(statement), params)


async def plan(api) -> dict:
    return (await api.get("/today")).json()["plan"]


async def person_in_kernel(setup) -> dict:
    async with setup.begin() as connection:
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": PERSON, "s": SUB},
        )
    return {"id": str(PERSON)}


async def train(api, day_offset: int = 0, sets: int = 1) -> str:
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
        for number in range(1, sets + 1):
            await api.put(
                f"/sessions/{session}/exercises/{exercise}/sets/{number}",
                json={"reps": 8, "weight": "60", "confirmed_at": started.isoformat()},
            )
    ended = started + timedelta(hours=1)
    await api.post(f"/sessions/{session}/finish", json={"ended_at": ended.isoformat()})
    return session


async def test_starting_with_the_apps_id_can_be_sent_twice(api, setup) -> None:
    session = "6b1f0c3e-2d4a-4e8b-9f17-0a5c3d2e1b40"
    body = {"started_at": T0.isoformat()}

    first = await api.put(f"/sessions/{session}", json=body)
    again = await api.put(f"/sessions/{session}", json=body)

    assert (first.status_code, again.status_code) == (200, 200)
    assert first.json()["id"] == again.json()["id"] == session
    assert await scalar(setup, "select count(*) from training.training_session") == 1
    assert (await api.get(f"/sessions/{session}")).json()["day_name"] == "Push"


async def test_me_says_who_is_looking(api) -> None:
    assert (await api.get("/me")).json() == {"user_id": str(PERSON)}


async def test_the_next_session_is_computed_not_chosen(api) -> None:
    today = (await api.get("/today")).json()

    assert (today["next"]["name"], today["next"]["rotation_number"]) == ("Push", 1)
    assert (today["next"]["remaining"], today["next"]["days_in_rotation"]) == (3, 3)
    assert today["in_progress"] is None


async def test_starting_creates_the_session_before_any_set_and_only_one(api) -> None:
    first = await api.post("/sessions", json={"started_at": T0.isoformat()})
    second = await api.post("/sessions", json={})

    assert first.status_code == 201
    assert second.status_code == 409
    assert (await api.get("/today")).json()["in_progress"] == first.json()["id"]


async def test_the_same_set_sent_twice_is_one_set_and_one_event(api, setup) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    slot = (await plan(api))["days"][0]["slots"][0]
    exercise = (
        await api.post(
            f"/sessions/{session}/exercises",
            json={"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]},
        )
    ).json()["id"]
    body = {"reps": 8, "weight": "62.5", "confirmed_at": T0.isoformat()}

    once = (await api.put(f"/sessions/{session}/exercises/{exercise}/sets/1", json=body)).json()
    twice = (await api.put(f"/sessions/{session}/exercises/{exercise}/sets/1", json=body)).json()

    assert (once["created"], twice["created"]) == (True, False)
    assert once["id"] == twice["id"]
    assert await scalar(setup, "select count(*) from training.training_set_log") == 1
    assert (
        await scalar(
            setup,
            "select count(*) from training.training_outbox where type = 'training.set_logged'",
        )
        == 1
    )


async def test_a_correction_raises_the_revision_and_publishes_again(api, setup) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    slot = (await plan(api))["days"][0]["slots"][0]
    exercise = (
        await api.post(
            f"/sessions/{session}/exercises",
            json={"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]},
        )
    ).json()["id"]
    url = f"/sessions/{session}/exercises/{exercise}/sets/1"

    await api.put(url, json={"reps": 8, "weight": "60", "confirmed_at": T0.isoformat()})
    fixed = (
        await api.put(url, json={"reps": 7, "weight": "60", "confirmed_at": T0.isoformat()})
    ).json()

    assert fixed["revision"] == 2
    assert await scalar(setup, "select reps from training.training_set_log") == 7
    assert (
        await scalar(
            setup,
            "select count(*) from training.training_outbox where type = 'training.set_logged'",
        )
        == 2
    )


async def test_a_completed_set_needs_reps_and_an_incomplete_one_does_not(api) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    slot = (await plan(api))["days"][0]["slots"][0]
    exercise = (
        await api.post(
            f"/sessions/{session}/exercises",
            json={"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]},
        )
    ).json()["id"]
    url = f"/sessions/{session}/exercises/{exercise}"

    missing = await api.put(f"{url}/sets/1", json={"weight": "60", "confirmed_at": T0.isoformat()})
    incomplete = await api.put(
        f"{url}/sets/2", json={"weight": "60", "completed": False, "confirmed_at": T0.isoformat()}
    )

    assert missing.status_code == 422
    assert incomplete.status_code == 200


async def test_a_variant_that_is_not_an_option_of_the_slot_is_refused(api) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    days = (await plan(api))["days"]
    push_slot = days[0]["slots"][0]
    pull_variant = days[1]["slots"][0]["options"][0]["variant_id"]

    response = await api.post(
        f"/sessions/{session}/exercises",
        json={"plan_slot_id": push_slot["id"], "variant_id": pull_variant},
    )

    assert response.status_code == 409


async def test_two_variants_of_a_slot_only_when_the_slot_allows_it(api) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    days = (await plan(api))["days"]
    push = days[0]["slots"][0]
    leg = days[2]["slots"][0]
    url = f"/sessions/{session}/exercises"

    for slot, expected in ((push, 409), (leg, 200)):
        first, second = (option["variant_id"] for option in slot["options"])
        assert (
            await api.post(url, json={"plan_slot_id": slot["id"], "variant_id": first})
        ).status_code == 200
        response = await api.post(url, json={"plan_slot_id": slot["id"], "variant_id": second})
        assert response.status_code == expected, slot["exercise"]


async def test_finishing_the_last_day_closes_the_rotation_and_the_next_opens(api, setup) -> None:
    for offset in range(3):
        await train(api, offset)

    today = (await api.get("/today")).json()

    assert (
        await scalar(setup, "select status from training.training_rotation where number = 1")
        == "complete"
    )
    assert (today["next"]["name"], today["next"]["rotation_number"]) == ("Push", 2)

    await train(api, 3)
    assert (
        await scalar(setup, "select count(*) from training.training_rotation where status = 'open'")
        == 1
    )


async def test_a_rotation_in_course_keeps_its_plan_version(api, setup) -> None:
    await train(api, 0)
    async with setup.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        await connection.execute(
            text(
                "insert into training.training_plan_version (plan_id, number) "
                "select id, 2 from training.training_plan where active"
            )
        )
        await connection.execute(
            text(
                "insert into training.training_plan_day (plan_version_id, name, kind, position) "
                "select id, 'Full', 'full', 1 from training.training_plan_version where number = 2"
            )
        )
        await connection.execute(
            text(
                "update training.training_plan_version "
                "set published_at = now(), valid_from = current_date where number = 2"
            )
        )

    assert (await api.get("/today")).json()["next"]["name"] == "Pull"
    await train(api, 1)
    await train(api, 2)
    assert (await api.get("/today")).json()["next"]["name"] == "Full"


async def test_a_forgotten_finish_is_corrected_with_the_real_times(api, setup) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    await api.post(
        f"/sessions/{session}/finish", json={"ended_at": (T0 + timedelta(hours=14)).isoformat()}
    )

    response = await api.put(
        f"/sessions/{session}/times",
        json={"started_at": "2026-09-14T19:05:00", "ended_at": "2026-09-14T20:15:00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duration_seconds"] == 70 * 60
    assert body["day"] == "2026-09-14"
    assert datetime.fromisoformat(body["started_at"]) == T0 + timedelta(minutes=5)
    assert (
        await scalar(
            setup,
            "select payload->>'duration_seconds' from training.training_outbox "
            "where type = 'training.session_times_changed'",
        )
        == "4200"
    )


async def test_the_times_of_a_session_cannot_be_nonsense(api, setup) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    url = f"/sessions/{session}/times"
    times = {"started_at": T0.isoformat(), "ended_at": (T0 + timedelta(hours=1)).isoformat()}

    assert (await api.put(url, json=times)).status_code == 409

    await api.post(f"/sessions/{session}/finish", json={"ended_at": times["ended_at"]})
    backwards = {"started_at": times["ended_at"], "ended_at": times["started_at"]}
    future = {**times, "ended_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()}
    assert (await api.put(url, json=backwards)).status_code == 409
    assert (await api.put(url, json=future)).status_code == 409
    missing = "/sessions/00000000-0000-0000-0000-000000000000/times"
    assert (await api.put(missing, json=times)).status_code == 404

    assert (await api.put(url, json=times)).status_code == 200
    assert (
        await scalar(
            setup,
            "select count(*) from training.training_outbox where type = 'training.session_times_changed'",
        )
        == 0
    )


async def test_moving_the_end_of_the_session_that_closed_a_rotation_moves_its_close(
    api, setup
) -> None:
    for offset in range(3):
        last = await train(api, offset)
    ended = T0 + timedelta(days=2, hours=1, minutes=10)

    await api.put(
        f"/sessions/{last}/times",
        json={"started_at": (T0 + timedelta(days=2)).isoformat(), "ended_at": ended.isoformat()},
    )

    assert (
        await scalar(setup, "select closed_at from training.training_rotation where number = 1")
        == ended
    )


async def test_the_week_counts_finished_sessions_against_the_goal(api, setup) -> None:
    async with setup.connect() as connection:
        await connection.execute(text('set role "mod_training"'))
    await train(api, 0)
    await train(api, 1)

    async with setup.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        current = await training.week(connection, T0.date())
        next_week = await training.week(connection, T0.date() + timedelta(days=7))

    assert (current.done, current.goal) == (2, 5)
    assert next_week.done == 0


async def test_last_time_brings_the_sets_of_that_variant(api) -> None:
    await train(api, 0, sets=3)
    variant = (await plan(api))["days"][0]["slots"][0]["options"][0]["variant_id"]

    last = (await api.get(f"/variants/{variant}/last")).json()

    assert [(s["reps"], s["weight"]) for s in last["sets"]] == [(8, 60.0)] * 3


async def test_last_time_is_the_one_in_the_same_gym_when_there_is_one(api) -> None:
    days = (await plan(api))["days"]
    push = next(day for day in days if day["kind"] == "push")
    variant = push["slots"][0]["options"][0]["variant_id"]
    here = (await api.get("/catalogue")).json()["gyms"][0]
    there = (await api.post("/gyms", json={"name": "Otro centro"})).json()

    async def bench_at(gym: dict, offset: int, weight: str) -> str:
        started = T0 + timedelta(days=offset)
        session = (
            await api.post(
                "/sessions",
                json={
                    "started_at": started.isoformat(),
                    "gym_id": gym["id"],
                    "plan_day_id": push["id"],
                },
            )
        ).json()["id"]
        exercise = (
            await api.post(
                f"/sessions/{session}/exercises",
                json={"plan_slot_id": push["slots"][0]["id"], "variant_id": variant},
            )
        ).json()["id"]
        await api.put(
            f"/sessions/{session}/exercises/{exercise}/sets/1",
            json={"reps": 8, "weight": weight, "confirmed_at": started.isoformat()},
        )
        ended = (started + timedelta(hours=1)).isoformat()
        await api.post(f"/sessions/{session}/finish", json={"ended_at": ended})
        return session

    await bench_at(here, 0, "60")
    await bench_at(there, 3, "30")

    anywhere = (await api.get(f"/variants/{variant}/last")).json()
    at_home = (await api.get(f"/variants/{variant}/last?gym_id={here['id']}")).json()

    assert anywhere["sets"][0]["weight"] == 30.0
    assert at_home["sets"][0]["weight"] == 60.0
    assert at_home["gym"] == here["name"]
    assert at_home["gym_id"] == here["id"]


async def test_a_session_without_gym_does_not_jump_ahead_of_the_last_one_in_this_gym(
    api, setup
) -> None:
    days = (await plan(api))["days"]
    push = next(day for day in days if day["kind"] == "push")
    slot = push["slots"][0]
    variant = slot["options"][0]["variant_id"]
    here = (await api.get("/catalogue")).json()["gyms"][0]

    async def bench(offset: int, weight: str) -> str:
        started = T0 + timedelta(days=offset)
        session = (
            await api.post(
                "/sessions",
                json={
                    "started_at": started.isoformat(),
                    "gym_id": here["id"],
                    "plan_day_id": push["id"],
                },
            )
        ).json()["id"]
        exercise = (
            await api.post(
                f"/sessions/{session}/exercises",
                json={"plan_slot_id": slot["id"], "variant_id": variant},
            )
        ).json()["id"]
        await api.put(
            f"/sessions/{session}/exercises/{exercise}/sets/1",
            json={"reps": 8, "weight": weight, "confirmed_at": started.isoformat()},
        )
        ended = (started + timedelta(hours=1)).isoformat()
        await api.post(f"/sessions/{session}/finish", json={"ended_at": ended})
        return session

    old = await bench(-700, "40")
    async with setup.begin() as connection:
        await connection.execute(
            text("update training.training_session set gym_id = null where id = :id"), {"id": old}
        )
    await bench(0, "60")

    last = (await api.get(f"/variants/{variant}/last?gym_id={here['id']}")).json()

    assert last["sets"][0]["weight"] == 60.0
    assert last["gym_id"] == here["id"]


async def test_with_the_kernel_down_sets_are_kept_and_published_when_it_returns(
    api, setup, monkeypatch
) -> None:
    monkeypatch.setattr(publisher, "RECORDS", Never())
    monkeypatch.setattr(publisher, "METRICS", Never())
    from kernel.main import app as kernel_app

    await train(api, 0)
    async with db.engine().begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        await links.backfill(connection)
    queued = await scalar(setup, "select count(*) from training.training_outbox")

    person = await person_in_kernel(setup)

    def down(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/users":
            return httpx.Response(200, json=[person])
        raise httpx.ConnectError("el kernel no contesta", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
        failed = await publisher.run_once(client)
    assert failed == {"published": 0, "pending": queued}
    assert await scalar(setup, "select max(attempts) from training.training_outbox") == 1

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=kernel_app)) as client:
        ok = await publisher.run_once(client)
        again = await publisher.run_once(client)

    assert ok == {"published": queued, "pending": 0}
    assert again == {"published": 0, "pending": 0}
    assert (
        await scalar(setup, "select count(*) from kernel.events where module = 'training'")
        == queued
    )
    types = await scalar(
        setup,
        "select string_agg(distinct type, ',' order by type) "
        "from kernel.events where module = 'training'",
    )
    assert types == (
        "training.session,training.session_finished,training.session_started,training.set_logged,training.variant,"
        "training.workout"
    )
    owners = await scalar(
        setup,
        "select string_agg(distinct cast(user_id as text), ',') "
        "from kernel.events where module = 'training'",
    )
    assert owners == str(PERSON)


async def test_what_a_person_trains_is_theirs_and_travels_to_the_log_as_theirs(api, setup) -> None:
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    kernel_db.engine.cache_clear()

    person = await person_in_kernel(setup)

    await train(api, 0)

    for table in (
        "training_session",
        "training_session_exercise",
        "training_set_log",
        "training_outbox",
    ):
        owners = await scalar(
            setup,
            "select string_agg(distinct coalesce(cast(user_id as text), '-'), ',') "
            f"from training.{table}",
        )
        assert owners == person["id"], table

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=kernel_app)) as client:
        await publisher.run_once(client)
    events = await scalar(
        setup,
        "select string_agg(distinct cast(user_id as text), ',') from kernel.events "
        "where module = 'training'",
    )
    assert events == person["id"]
    await kernel_db.engine().dispose()
    kernel_db.engine.cache_clear()


async def test_an_exercise_with_the_app_id_can_be_sent_twice_and_sets_hang_from_it(api) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    slot = (await api.get(f"/sessions/{session}")).json()["slots"][0]
    body = {"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]}
    exercise = "5b0e8f7e-4c1a-4d53-9a53-0d3f0c1e2a11"

    first = await api.put(f"/sessions/{session}/exercises/{exercise}", json=body)
    again = await api.put(f"/sessions/{session}/exercises/{exercise}", json=body)
    logged = await api.put(
        f"/sessions/{session}/exercises/{exercise}/sets/1",
        json={"reps": 8, "weight": "60", "confirmed_at": T0.isoformat()},
    )

    assert first.json() == again.json() == {"id": exercise}
    assert logged.status_code == 200
    detail = (await api.get(f"/sessions/{session}")).json()
    assert [e["id"] for e in detail["exercises"]] == [exercise]


async def test_the_same_slot_and_variant_from_another_device_returns_the_existing_one(api) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    slot = (await api.get(f"/sessions/{session}")).json()["slots"][0]
    body = {"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]}
    first = "5b0e8f7e-4c1a-4d53-9a53-0d3f0c1e2a11"
    other = "0c6a7f3b-1d2e-4f50-8a6b-7c8d9e0f1a22"

    await api.put(f"/sessions/{session}/exercises/{first}", json=body)
    response = await api.put(f"/sessions/{session}/exercises/{other}", json=body)

    assert response.json() == {"id": first}


async def test_the_same_exercise_id_with_other_data_is_refused(api) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]
    slots = (await api.get(f"/sessions/{session}")).json()["slots"]
    exercise = "5b0e8f7e-4c1a-4d53-9a53-0d3f0c1e2a11"
    await api.put(
        f"/sessions/{session}/exercises/{exercise}",
        json={"plan_slot_id": slots[0]["id"], "variant_id": slots[0]["options"][0]["variant_id"]},
    )

    response = await api.put(
        f"/sessions/{session}/exercises/{exercise}",
        json={"plan_slot_id": slots[1]["id"], "variant_id": slots[1]["options"][0]["variant_id"]},
    )

    assert response.status_code == 409


async def test_a_session_brings_the_last_time_of_its_variants_but_not_itself(api) -> None:
    await train(api, 0, sets=2)
    await train(api, 1)
    await train(api, 2)
    session = (
        await api.post("/sessions", json={"started_at": (T0 + timedelta(days=3)).isoformat()})
    ).json()["id"]
    detail = (await api.get(f"/sessions/{session}")).json()
    variant = detail["slots"][0]["options"][0]["variant_id"]

    history = {h["variant_id"]: h for h in detail["history"]}

    assert history[variant]["day"] == T0.date().isoformat()
    assert len(history[variant]["sets"]) == 2


async def test_the_only_gym_is_the_default_the_first_time(api, setup) -> None:
    session = (await api.post("/sessions", json={"started_at": T0.isoformat()})).json()["id"]

    assert (await api.get(f"/sessions/{session}")).json()["gym_id"] is not None


async def test_the_widgets_say_the_week_and_what_comes_next(api) -> None:
    await train(api, 0)

    week = (await api.get("/widgets/week")).json()
    upcoming = (await api.get("/widgets/next")).json()

    assert week["state"] == "ready"
    assert week["body"]["target"] == 5
    assert round(5 / 7, 2) <= week["body"]["expected"] <= 5
    assert upcoming["body"]["value"] == "Pull"
    assert upcoming["body"] == {"value": "Pull", "icon": "pull", "icon_hue": 2}


async def test_a_widget_that_does_not_exist_is_a_404(api) -> None:
    assert (await api.get("/widgets/nada")).status_code == 404


def test_the_desktop_paints_a_day_in_the_same_tone_as_the_app() -> None:
    labels = Path(__file__).resolve().parents[1] / "ui" / "src" / "labels.ts"
    line = labels.read_text(encoding="utf-8").split("HUE_OF_KIND: Record<DayKind, number> =")[1]
    app_hues = {kind: int(hue) for kind, hue in re.findall(r"(\w+): (\d+)", line.split("};")[0])}

    assert app_hues == widgets.HUES
