from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import arga_agenda
from arga_tenancy import install
from training import activities, agenda, db, plan, seed, training
from training.main import MODULE_ID, app

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
SCALE = "probe_scale"


@pytest.fixture
async def setup(database_url: str):
    from arga_testing import fresh_modules

    engine = install(create_async_engine(database_url))
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from kernel.events where module = :m"), {"m": MODULE_ID}
        )
        await connection.execute(text("delete from kernel.events where module = :s"), {"s": SCALE})
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:s, '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {
                "s": SCALE,
                "manifest": json.dumps(
                    {
                        "publishes": [
                            {"type": f"{SCALE}.weight", "contract": "body_weight"},
                            {"type": f"{SCALE}.activity", "contract": "activity"},
                        ]
                    }
                ),
            },
        )
        await fresh_modules(connection, MODULE_ID, root=ROOT)
        await connection.execute(text('set local role "mod_training"'))
        await seed.seed(connection)
    yield engine
    async with engine.begin() as connection:
        for module in (MODULE_ID, SCALE):
            await connection.execute(
                text("delete from kernel.modules where id = :m"), {"m": module}
            )
            await connection.execute(
                text("delete from kernel.events where module = :m"), {"m": module}
            )
    await engine.dispose()
    await db.engine().dispose()


@pytest.fixture
async def api(setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as client:
        yield client


async def as_training(engine, statement: str, **params) -> list:
    async with engine.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        return (await connection.execute(text(statement), params)).all()


async def published(engine) -> list[dict]:
    rows = await as_training(
        engine,
        "select payload from training.training_outbox where type = 'training.session' order by id",
    )
    return [row.payload for row in rows]


async def trained(api, start: datetime, minutes: int = 60) -> str:
    session = (await api.post("/sessions", json={"started_at": start.isoformat()})).json()["id"]
    end = start + timedelta(minutes=minutes)
    await api.post(f"/sessions/{session}/finish", json={"ended_at": end.isoformat()})
    return session


async def test_a_finished_session_is_published_as_something_with_a_date(setup, api) -> None:
    session = await trained(api, T0)

    [payload] = await published(setup)
    item = arga_agenda.check_event(payload)
    assert item["uid"] == f"training:session:{session}"
    assert item["start"] == "2026-09-14T19:00:00+02:00"
    assert item["end"] == "2026-09-14T20:00:00+02:00"
    assert item["status"] == "confirmed"
    assert item["href"] == f"/training/sesion/{session}"


async def test_a_session_in_progress_is_not_in_the_calendar(setup, api) -> None:
    await api.post("/sessions", json={"started_at": T0.isoformat()})

    assert await published(setup) == []


async def test_changing_its_times_publishes_the_new_version(setup, api) -> None:
    session = await trained(api, T0)
    await api.put(
        f"/sessions/{session}/times",
        json={
            "started_at": T0.isoformat(),
            "ended_at": (T0 + timedelta(minutes=45)).isoformat(),
        },
    )

    first, second = await published(setup)
    assert first["agenda"]["uid"] == second["agenda"]["uid"]
    assert second["agenda"]["end"] == "2026-09-14T19:45:00+02:00"


async def test_deleting_it_takes_it_out_with_the_same_uid(setup, api) -> None:
    session = await trained(api, T0)
    await api.delete(f"/sessions/{session}")

    finished, removed = await published(setup)
    assert removed["agenda"]["uid"] == finished["agenda"]["uid"]
    assert removed["agenda"]["status"] == "cancelled"


async def test_what_was_trained_before_is_published_once(setup, api) -> None:
    await trained(api, T0)
    await trained(api, T0 + timedelta(days=2))
    async with setup.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        await connection.execute(text("delete from training.training_outbox"))

    for _ in range(2):
        async with setup.begin() as connection:
            await connection.execute(text('set local role "mod_training"'))
            await agenda.backfill(connection)

    assert len(await published(setup)) == 2


async def weighed(engine, weight_id: str, day: date, kg: float, at: datetime) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash) "
                "values (:ts, :m, 'app', :type, cast(:payload as jsonb), :dedup)"
            ),
            {
                "ts": at,
                "m": SCALE,
                "type": f"{SCALE}.weight",
                "payload": json.dumps(
                    {"body_weight": {"id": weight_id, "day": day.isoformat(), "kg": kg}}
                ),
                "dedup": f"{weight_id}:{kg}",
            },
        )


async def bodyweight(engine) -> float | None:
    async with engine.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        return (await plan.settings(connection)).bodyweight


async def test_the_weight_another_app_publishes_reaches_training(setup) -> None:
    await weighed(setup, "w1", date(2026, 9, 20), 81.2, T0)

    assert await bodyweight(setup) == 81.2


async def test_a_correction_is_the_one_that_counts(setup) -> None:
    await weighed(setup, "w1", date(2026, 9, 20), 81.2, T0)
    await weighed(setup, "w1", date(2026, 9, 20), 80.2, T0 + timedelta(hours=1))

    assert await bodyweight(setup) == 80.2


async def test_on_the_same_day_what_the_keeper_published_wins(setup, api) -> None:
    today = training.local_day(datetime.now(UTC))
    await api.put("/bodyweight", json={"kg": 79.5})
    assert await bodyweight(setup) == 79.5

    await weighed(setup, "w1", today, 79.8, datetime.now(UTC))

    assert await bodyweight(setup) == 79.8


async def test_two_weighings_the_same_day_read_as_their_mean_like_everywhere(setup) -> None:
    await weighed(setup, "w1", date(2026, 9, 20), 81.0, T0)
    await weighed(setup, "w2", date(2026, 9, 20), 80.0, T0 + timedelta(hours=1))

    assert await bodyweight(setup) == 80.5


async def test_the_weight_history_has_the_shape_every_app_shows(setup, api) -> None:
    await weighed(setup, "w1", date(2026, 9, 20), 81.2, T0)

    logged = (await api.post("/weight", json={"kg": 80.4, "day": "2026-09-22"})).json()
    found = (await api.get("/weight")).json()

    assert logged["pending"] is True
    assert logged["latest"] == {"day": "2026-09-22", "kg": 80.4}
    assert found["days"] == [
        {"day": "2026-09-20", "kg": 81.2},
        {"day": "2026-09-22", "kg": 80.4},
    ]


async def test_what_was_typed_here_is_asked_again_until_the_keeper_has_it(setup, api) -> None:
    from training import bodyweight as weights

    await api.post("/weight", json={"kg": 80.4, "day": "2026-09-22"})
    asked: list[dict] = []

    def keeper(request: httpx.Request) -> httpx.Response:
        asked.append(json.loads(request.content))
        return httpx.Response(
            200, json={"id": "w9", "day": "2026-09-22", "kg": 80.4, "already": False}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(keeper)) as client:
        async with setup.begin() as connection:
            await connection.execute(text('set local role "mod_training"'))
            assert await weights.forward(connection, client) == 1
        await weighed(setup, "w9", date(2026, 9, 22), 80.4, T0)
        async with setup.begin() as connection:
            await connection.execute(text('set local role "mod_training"'))
            assert await weights.forward(connection, client) == 0

    assert asked == [{"kg": 80.4, "day": "2026-09-22"}]


async def test_a_newer_day_from_elsewhere_is_the_latest(setup, api) -> None:
    await api.put("/bodyweight", json={"kg": 79.5})
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    await weighed(setup, "w2", tomorrow, 78.9, datetime.now(UTC))

    assert await bodyweight(setup) == 78.9


async def test_what_is_not_published_under_the_contract_never_arrives(setup) -> None:
    async with setup.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash) "
                "values (now(), :m, 'app', :type, cast(:payload as jsonb), 'other')"
            ),
            {
                "m": SCALE,
                "type": f"{SCALE}.fat",
                "payload": json.dumps({"body_weight": {"id": "x", "day": "2026-09-20", "kg": 150}}),
            },
        )

    assert await bodyweight(setup) is None


async def activities_published(engine) -> list[dict]:
    rows = await as_training(
        engine,
        "select payload from training.training_outbox where type = 'training.activity' order by id",
    )
    return [row.payload for row in rows]


async def test_an_activity_has_its_time_and_goes_to_the_calendar(setup, api) -> None:
    climbing = (await api.post("/activity-types", json={"name": "Escalada"})).json()
    logged = (
        await api.post(
            "/activities",
            json={
                "activity_type_id": climbing["id"],
                "day": "2026-09-15",
                "start_time": "18:30",
                "duration_seconds": 5400,
            },
        )
    ).json()
    assert logged["start_time"] == "18:30:00"

    [payload] = await activities_published(setup)
    item = arga_agenda.check_event(payload)
    assert item["uid"] == f"training:activity:{logged['id']}"
    assert item["title"] == "Escalada"
    assert (item["start"], item["end"]) == (
        "2026-09-15T18:30:00+02:00",
        "2026-09-15T20:00:00+02:00",
    )

    assert (await api.delete(f"/activities/{logged['id']}")).status_code == 204
    cancelled = arga_agenda.check_event((await activities_published(setup))[-1])
    assert cancelled["uid"] == item["uid"] and cancelled["status"] == "cancelled"


async def test_without_a_time_it_is_half_past_six_in_the_evening(setup, api) -> None:
    climbing = (await api.post("/activity-types", json={"name": "Escalada"})).json()
    logged = (
        await api.post(
            "/activities", json={"activity_type_id": climbing["id"], "day": "2026-09-15"}
        )
    ).json()
    assert logged["start_time"] == "18:30:00"


async def sport_done(engine, activity_id: str, start: str, minutes: int = 60, **extra) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash) "
                "values (now(), :m, 'app', :type, cast(:payload as jsonb), :dedup)"
            ),
            {
                "m": SCALE,
                "type": f"{SCALE}.activity",
                "payload": json.dumps(
                    {
                        "activity": {
                            "id": activity_id,
                            "name": "Natación",
                            "start": start,
                            "minutes": minutes,
                            "tz": "Europe/Madrid",
                            **extra,
                        }
                    }
                ),
                "dedup": f"{activity_id}:{extra}",
            },
        )


async def receive(engine) -> int:
    async with engine.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        return await activities.receive(connection)


async def test_sport_done_in_another_app_is_logged_once_and_does_not_come_back(setup, api) -> None:
    await sport_done(setup, "swim:1", "2026-09-15T19:00:00+02:00")
    await sport_done(setup, "swim:2", "2026-09-17T19:00:00+02:00", minutes=45)

    assert await receive(setup) == 2
    assert await receive(setup) == 0

    listed = (
        await api.get("/activities", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json()
    assert [
        (a["name"], a["day"], a["start_time"], a["duration_seconds"], a["source"]) for a in listed
    ] == [
        ("Natación", "2026-09-17", "19:00:00", 2700, "received"),
        ("Natación", "2026-09-15", "19:00:00", 3600, "received"),
    ]
    kinds = (await api.get("/activity-types")).json()
    assert [k["name"] for k in kinds] == ["Natación"]
    assert len(await activities_published(setup)) == 2

    assert (await api.delete(f"/activities/{listed[0]['id']}")).status_code == 204
    assert await receive(setup) == 0
    left = (
        await api.get("/activities", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json()
    assert [a["day"] for a in left] == ["2026-09-15"]


async def test_what_was_withdrawn_before_arriving_is_not_logged(setup, api) -> None:
    await sport_done(setup, "swim:3", "2026-09-22T19:00:00+02:00", removed=True)

    assert await receive(setup) == 0
    listed = (
        await api.get("/activities", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json()
    assert listed == []


async def band_workout(
    engine, workout_id: str, kind: str, start: str, end: str | None = None, **extra
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash) "
                "values (now(), 'hub', 'google_health', 'health.exercise', "
                "cast(:payload as jsonb), :dedup)"
            ),
            {
                "payload": json.dumps(
                    {
                        "id": workout_id,
                        "kind": kind,
                        "name": "Workout",
                        "start": start,
                        "end": end or start,
                        "minutes": 40.0,
                        "kcal": 180.4,
                        "distance_km": 3.2,
                        "heart_rate_avg": 104.0,
                        **extra,
                    }
                ),
                "dedup": f"google:exercise:{workout_id}:{extra}",
            },
        )


async def receive_band(engine) -> int:
    async with engine.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        return await activities.receive_exercises(connection)


@pytest.fixture
async def band(setup):
    yield setup
    async with setup.begin() as connection:
        await connection.execute(text("delete from kernel.events where source = 'google_health'"))


async def listed_activities(api) -> list[dict]:
    return (
        await api.get("/activities", params={"since": "2026-09-01", "until": "2026-09-30"})
    ).json()


async def test_a_band_workout_is_logged_once_with_what_it_measured(band, api) -> None:
    await band_workout(
        band,
        "ex:2",
        "BIKING",
        "2026-09-16T20:30:00+02:00",
        minutes=90.0,
        heart=[{"s": 0, "bpm": 98.0}, {"s": 5, "bpm": 151.0}],
        hr_zone_min={"light": 30.0, "vigorous": 20.0},
    )

    assert await receive_band(band) == 1
    assert await receive_band(band) == 0

    [bike] = await listed_activities(api)
    assert (bike["name"], bike["day"], bike["start_time"], bike["duration_seconds"]) == (
        "Bici",
        "2026-09-16",
        "20:30:00",
        5400,
    )
    assert (bike["source"], bike["from_band"], bike["notes"]) == ("received", True, None)
    assert bike["band"] == {
        "kcal": 180.4,
        "distance_km": 3.2,
        "heart_rate_avg": 104.0,
        "hr_zone_min": {"light": 30.0, "vigorous": 20.0},
        "heart_rate_max": 151.0,
    }


async def test_a_walk_never_becomes_an_activity(band, api) -> None:
    await band_workout(band, "ex:1", "WALKING", "2026-09-15T18:00:00+02:00")

    assert await receive_band(band) == 0
    assert await receive_band(band) == 0
    assert await listed_activities(api) == []


async def test_only_a_bike_from_the_band_is_logged_on_its_own(band, api) -> None:
    await band_workout(band, "ex:12", "RUNNING", "2026-09-15T18:00:00+02:00")
    await band_workout(band, "ex:13", "PADEL", "2026-09-16T20:30:00+02:00")
    await band_workout(band, "ex:14", "MOUNTAIN_BIKE", "2026-09-17T10:00:00+02:00")

    assert await receive_band(band) == 1
    assert await receive_band(band) == 0
    assert [one["name"] for one in await listed_activities(api)] == ["Bici"]
    assert [k["name"] for k in (await api.get("/activity-types")).json()] == ["Bici"]


async def test_what_the_band_measured_joins_what_was_logged_whatever_it_is(band, api) -> None:
    padel = (await api.post("/activity-types", json={"name": "Pádel"})).json()
    await api.post(
        "/activities",
        json={"activity_type_id": padel["id"], "day": "2026-09-16", "start_time": "20:30"},
    )
    await band_workout(
        band, "ex:15", "PADEL", "2026-09-16T20:34:00+02:00", end="2026-09-16T22:00:00+02:00"
    )

    assert await receive_band(band) == 1
    [one] = await listed_activities(api)
    assert (one["name"], one["start_time"], one["from_band"]) == ("Pádel", "20:34:00", True)


async def test_the_same_activity_from_training_and_the_band_is_one(band, api) -> None:
    bike = (await api.post("/activity-types", json={"name": "Bici"})).json()
    await api.post(
        "/activities",
        json={
            "activity_type_id": bike["id"],
            "day": "2026-09-20",
            "start_time": "12:00",
            "duration_seconds": 1800,
            "notes": "intervalos",
        },
    )
    end = "2026-09-20T12:39:00+02:00"
    await band_workout(band, "ex:5", "STATIONARY_BIKE", "2026-09-20T12:07:00+02:00", end=end)

    assert await receive_band(band) == 1
    [one] = await listed_activities(api)
    assert (one["name"], one["start_time"], one["duration_seconds"]) == ("Bici", "12:07:00", 1920)
    assert (one["from_band"], one["notes"]) == (True, "intervalos")
    calendar = await as_training(
        band,
        "select payload from training.training_outbox where type = 'training.activity' order by id",
    )
    assert calendar[-1].payload["agenda"]["start"] == "2026-09-20T12:07:00+02:00"


async def test_logging_what_the_band_already_brought_does_not_duplicate_it(band, api) -> None:
    await band_workout(
        band, "ex:6", "BIKING", "2026-09-21T19:04:00+02:00", end="2026-09-21T20:31:00+02:00"
    )
    assert await receive_band(band) == 1
    [bike] = await listed_activities(api)

    again = await api.post(
        "/activities",
        json={
            "activity_type_id": bike["activity_type_id"],
            "day": "2026-09-21",
            "start_time": "19:00",
            "duration_seconds": 5400,
            "notes": "con Íñigo",
        },
    )

    assert again.status_code == 201
    assert again.json()["id"] == bike["id"]
    [one] = await listed_activities(api)
    assert (one["start_time"], one["duration_seconds"], one["notes"]) == (
        "19:04:00",
        5220,
        "con Íñigo",
    )


async def test_a_type_says_what_it_is_called_on_the_band(band, api) -> None:
    spin = (await api.post("/activity-types", json={"name": "Spinning casa"})).json()
    saved = await api.put(
        f"/activity-types/{spin['id']}",
        json={"name": "Spinning casa", "band_kinds": ["STATIONARY_BIKE"]},
    )
    assert saved.json()["band_kinds"] == ["STATIONARY_BIKE"]
    await band_workout(band, "ex:7", "STATIONARY_BIKE", "2026-09-22T08:00:00+02:00")

    assert await receive_band(band) == 1
    assert [one["name"] for one in await listed_activities(api)] == ["Spinning casa"]
    renamed = await api.put(f"/activity-types/{spin['id']}", json={"name": "Spinning"})
    assert renamed.json()["band_kinds"] == ["STATIONARY_BIKE"]


async def test_strength_from_the_band_joins_its_session(band, api) -> None:
    session = await trained(api, datetime(2026, 9, 18, 5, 0, tzinfo=UTC), minutes=70)
    await band_workout(
        band, "ex:3", "WEIGHTLIFTING", "2026-09-18T07:05:00+02:00", end="2026-09-18T08:05:00+02:00"
    )

    assert await receive_band(band) == 0
    assert await listed_activities(api) == []
    [row] = await as_training(
        band, "select band_id from training.training_session where id = :id", id=session
    )
    assert row.band_id == "ex:3"
    workouts = await as_training(
        band,
        "select payload from training.training_outbox where type = 'training.workout' order by id",
    )
    assert workouts[-1].payload["workout"]["band_id"] == "ex:3"


async def test_strength_from_the_band_waits_for_its_session(band, api) -> None:
    await band_workout(
        band, "ex:8", "WEIGHTLIFTING", "2026-09-18T07:05:00+02:00", end="2026-09-18T08:05:00+02:00"
    )
    async with band.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        soon = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
        assert await activities.receive_exercises(connection, now=soon) == 0
    session = await trained(api, datetime(2026, 9, 18, 5, 0, tzinfo=UTC), minutes=70)

    assert await receive_band(band) == 0
    [row] = await as_training(
        band, "select band_id from training.training_session where id = :id", id=session
    )
    assert row.band_id == "ex:8"


async def test_sport_from_another_app_and_the_band_at_the_same_time_is_one(band, api) -> None:
    await sport_done(band, "swim:9", "2026-09-19T19:00:00+02:00")
    assert await receive(band) == 1
    await band_workout(
        band,
        "ex:4",
        "SWIMMING_POOL",
        "2026-09-19T19:10:00+02:00",
        end="2026-09-19T19:55:00+02:00",
    )

    assert await receive_band(band) == 1
    [swim] = await listed_activities(api)
    assert (swim["name"], swim["start_time"], swim["duration_seconds"]) == (
        "Natación",
        "19:10:00",
        2700,
    )


async def test_a_generic_band_sport_is_what_was_logged_at_that_hour(band, api) -> None:
    await sport_done(band, "padel:1", "2026-09-22T18:30:00+02:00", name="Padel")
    assert await receive(band) == 1
    await band_workout(
        band, "ex:9", "SPORT", "2026-09-22T18:32:00+02:00", end="2026-09-22T19:35:00+02:00"
    )

    assert await receive_band(band) == 1
    [padel] = await listed_activities(api)
    assert (padel["name"], padel["start_time"], padel["duration_seconds"]) == (
        "Padel",
        "18:32:00",
        3780,
    )
    assert padel["from_band"] is True
    assert [k["name"] for k in (await api.get("/activity-types")).json()] == ["Padel"]


async def test_a_generic_band_sport_with_nothing_logged_is_not_logged(band, api) -> None:
    await band_workout(band, "ex:10", "SPORT", "2026-09-23T18:00:00+02:00", name="Deporte")

    assert await receive_band(band) == 0
    assert await listed_activities(api) == []


async def test_logging_what_another_app_announced_keeps_your_hour(band, api) -> None:
    await sport_done(band, "padel:2", "2026-09-24T18:30:00+02:00", name="Padel")
    assert await receive(band) == 1
    [announced] = await listed_activities(api)

    logged = await api.post(
        "/activities",
        json={
            "activity_type_id": announced["activity_type_id"],
            "day": "2026-09-24",
            "start_time": "19:30",
            "duration_seconds": 5400,
        },
    )

    assert logged.json()["id"] == announced["id"]
    [one] = await listed_activities(api)
    assert (one["start_time"], one["duration_seconds"]) == ("19:30:00", 5400)


async def test_what_another_app_announces_after_you_logged_it_is_not_added(band, api) -> None:
    padel = (await api.post("/activity-types", json={"name": "Padel"})).json()
    await api.post(
        "/activities",
        json={"activity_type_id": padel["id"], "day": "2026-09-25", "start_time": "19:30"},
    )
    await sport_done(band, "padel:3", "2026-09-25T18:30:00+02:00", name="Padel")

    assert await receive(band) == 0
    assert [one["start_time"] for one in await listed_activities(api)] == ["19:30:00"]


async def join_twins(engine) -> int:
    async with engine.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        return await activities.join_twins(connection)


async def test_what_came_in_twice_before_is_joined_once(band, api) -> None:
    await band_workout(
        band,
        "ex:11",
        "SPORT",
        "2026-09-26T18:32:00+02:00",
        end="2026-09-26T19:35:00+02:00",
        name="Deporte",
    )
    sport = (await api.post("/activity-types", json={"name": "Deporte"})).json()
    await as_training(
        band,
        "insert into training.training_activity (activity_type_id, day, start_time, duration_seconds, "
        "band_id, band, source) values (cast(:type as uuid), '2026-09-26', '18:32', 3780, "
        "'ex:11', '{}', 'received') returning id",
        type=sport["id"],
    )
    await as_training(
        band,
        "insert into training.training_activity_received (origin_id) values ('ex:11') "
        "returning origin_id",
    )
    padel = (await api.post("/activity-types", json={"name": "Padel"})).json()
    await api.post(
        "/activities",
        json={"activity_type_id": padel["id"], "day": "2026-09-26", "start_time": "18:30"},
    )
    await sport_done(band, "padel:4", "2026-09-27T18:30:00+02:00", name="Padel")
    assert await receive(band) == 1
    await api.post(
        "/activities",
        json={"activity_type_id": padel["id"], "day": "2026-09-28", "start_time": "19:30"},
    )
    await as_training(
        band,
        "update training.training_activity set day = '2026-09-27' where day = '2026-09-28' returning id",
    )
    assert len(await listed_activities(api)) == 4

    assert await join_twins(band) == 2
    assert await join_twins(band) == 0
    assert [
        (one["name"], one["day"], one["start_time"], one["from_band"])
        for one in await listed_activities(api)
    ] == [
        ("Padel", "2026-09-27", "19:30:00", False),
        ("Padel", "2026-09-26", "18:32:00", True),
    ]


async def test_an_activity_started_now_is_finished_later(setup, api, monkeypatch) -> None:
    bike = (await api.post("/activity-types", json={"name": "Bici"})).json()
    started = datetime(2026, 9, 23, 10, 2, 40, tzinfo=UTC)
    monkeypatch.setattr(activities, "datetime", frozen(started))
    open_ = (await api.post("/activities/start", json={"activity_type_id": bike["id"]})).json()

    assert (open_["start_time"], open_["ongoing"], open_["duration_seconds"]) == (
        "12:02:00",
        True,
        None,
    )
    assert [one["id"] for one in (await api.get("/activities/ongoing")).json()] == [open_["id"]]
    assert (
        await as_training(
            setup, "select 1 from training.training_outbox where type = 'training.workout'"
        )
        == []
    )

    monkeypatch.setattr(activities, "datetime", frozen(started + timedelta(minutes=33)))
    done = (await api.post(f"/activities/{open_['id']}/finish")).json()

    assert (done["ongoing"], done["duration_seconds"]) == (False, 33 * 60 + 40)
    assert (await api.get("/activities/ongoing")).json() == []
    [workout] = await as_training(
        setup, "select payload from training.training_outbox where type = 'training.workout'"
    )
    assert workout.payload["workout"]["kind"] == "activity"
    assert workout.payload["workout"]["start"] == "2026-09-23T12:02:00+02:00"


async def test_its_hours_are_corrected_to_the_minute(setup, api) -> None:
    bike = (await api.post("/activity-types", json={"name": "Bici"})).json()
    logged = (
        await api.post(
            "/activities",
            json={"activity_type_id": bike["id"], "day": "2026-09-24", "start_time": "18:30"},
        )
    ).json()

    moved = await api.put(
        f"/activities/{logged['id']}/times",
        json={"start": "2026-09-24T18:47:00+02:00", "end": "2026-09-24T19:21:00+02:00"},
    )

    assert (moved.json()["start_time"], moved.json()["duration_seconds"]) == ("18:47:00", 2040)


def frozen(moment: datetime):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment if tz is None else moment.astimezone(tz)

    return Frozen


async def move(api, uid: str, start: str, end: str, **extra):
    return await api.post(
        "/capabilities/agenda.move",
        json={"uid": uid, "start": start, "end": end, **extra},
        headers={"x-module-token": "probe-token", "x-arga-module": "planner"},
    )


async def test_an_activity_moves_from_the_calendar_and_back(setup, api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "probe-token")
    padel = (await api.post("/activity-types", json={"name": "Pádel"})).json()
    logged = (
        await api.post(
            "/activities",
            json={"activity_type_id": padel["id"], "day": "2026-09-15", "start_time": "18:30"},
        )
    ).json()
    uid = f"training:activity:{logged['id']}"

    moved = await move(api, uid, "2026-09-16T19:00:00+02:00", "2026-09-16T20:00:00+02:00")
    back = await move(api, uid, "2026-09-15T18:30:00+02:00", "2026-09-15T19:30:00+02:00")

    assert moved.status_code == 200
    assert moved.json()["agenda"]["start"] == "2026-09-16T19:00:00+02:00"
    listed = (
        await api.get("/activities", params={"since": "2026-09-15", "until": "2026-09-16"})
    ).json()
    assert [(one["day"], one["duration_seconds"]) for one in listed] == [("2026-09-15", None)]
    starts = [arga_agenda.check_event(p)["start"] for p in await activities_published(setup)]
    assert starts == [
        "2026-09-15T18:30:00+02:00",
        "2026-09-16T19:00:00+02:00",
        "2026-09-15T18:30:00+02:00",
    ]
    assert back.json()["agenda"]["start"] == starts[-1]


async def test_stretching_an_activity_gives_it_a_duration(setup, api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "probe-token")
    padel = (await api.post("/activity-types", json={"name": "Pádel"})).json()
    logged = (
        await api.post(
            "/activities",
            json={"activity_type_id": padel["id"], "day": "2026-09-15", "start_time": "18:30"},
        )
    ).json()

    await move(
        api,
        f"training:activity:{logged['id']}",
        "2026-09-15T18:30:00+02:00",
        "2026-09-15T20:00:00+02:00",
    )

    listed = (
        await api.get("/activities", params={"since": "2026-09-15", "until": "2026-09-15"})
    ).json()
    assert listed[0]["duration_seconds"] == 5400


async def test_a_session_moves_with_the_rules_of_correcting_it(setup, api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "probe-token")
    session = await trained(api, T0)
    uid = f"training:session:{session}"

    moved = await move(api, uid, "2026-09-14T20:00:00+02:00", "2026-09-14T21:30:00+02:00")
    future = await move(api, uid, "2099-01-01T20:00:00+02:00", "2099-01-01T21:00:00+02:00")

    assert moved.status_code == 200
    assert moved.json()["agenda"]["end"] == "2026-09-14T21:30:00+02:00"
    assert future.status_code == 409


async def test_only_the_kernel_asks_and_only_for_what_is_trainings(setup, api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "probe-token")
    session = await trained(api, T0)
    start, end = "2026-09-14T20:00:00+02:00", "2026-09-14T21:00:00+02:00"

    forged = await api.post(
        "/capabilities/agenda.move",
        json={"uid": f"training:session:{session}", "start": start, "end": end},
        headers={"x-module-token": "no"},
    )
    other = await move(api, "study:session:1", start, end)
    whole = await move(api, f"training:session:{session}", "2026-09-14", "2026-09-15", all_day=True)

    assert forged.status_code == 401
    assert other.status_code == 404
    assert whole.status_code == 409
