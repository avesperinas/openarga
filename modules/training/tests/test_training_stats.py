from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import install
from training import db, main, seed, stats, strength
from training.main import MODULE_ID, app

MODULES = Path(__file__).resolve().parents[2]
HOY = datetime.now(UTC)
T0 = HOY.replace(hour=17, minute=0, second=0, microsecond=0)
LUNES = date(2026, 9, 14)


def best(variant: str, day: date, reps: int, load: float, weight: int = 3) -> stats.Best:
    return stats.Best(
        variant_id=variant,
        day=day,
        reps=reps,
        load=load,
        e1rm=stats.epley(reps, load),
        weight=weight,
    )


def test_epley_is_the_formula_and_not_an_approximation() -> None:
    assert stats.epley(8, 60) == 76.0
    assert round(stats.epley(1, 100), 1) == 103.3
    assert round(stats.epley(20, 40), 1) == 66.7


def test_the_index_is_a_hundred_when_nothing_moved() -> None:
    since, until = LUNES, LUNES + timedelta(days=90)
    entries = [best("a", since, 8, 60), best("a", until, 8, 60)]

    index = stats.performance_index(entries, since, until)

    assert index.value == 100.0
    assert index.delta == 0.0
    assert index.direction == "flat"


def test_the_index_weights_a_basic_lift_more_than_an_isolation_one() -> None:
    since, until = LUNES, LUNES + timedelta(days=90)
    entries = [
        best("basico", since, 5, 100, weight=3),
        best("basico", until, 5, 100, weight=3),
        best("aislamiento", since, 10, 10, weight=1),
        best("aislamiento", until, 10, 20, weight=1),
    ]

    index = stats.performance_index(entries, since, until)

    assert index.value == 125.0
    assert index.direction == "up"


def test_a_variant_that_appears_halfway_does_not_count() -> None:
    since, until = LUNES, LUNES + timedelta(days=90)
    entries = [
        best("vieja", since, 5, 100),
        best("vieja", until, 5, 100),
        best("nueva", until - timedelta(days=10), 5, 50),
        best("nueva", until, 5, 80),
    ]

    index = stats.performance_index(entries, since, until)

    assert index.variants == 1
    assert index.value == 100.0


def test_without_data_at_both_ends_there_is_no_index_instead_of_a_zero() -> None:
    index = stats.performance_index([], LUNES, LUNES + timedelta(days=30))

    assert index.value is None
    assert index.direction is None
    assert index.trend == []


def test_the_traffic_light_has_a_one_per_cent_threshold() -> None:
    since, until = LUNES, LUNES + timedelta(days=90)

    def direction(load: float) -> str:
        entries = [best("a", since, 5, 100), best("a", until, 5, load)]
        return stats.performance_index(entries, since, until).direction

    assert direction(100.5) == "flat"
    assert direction(102) == "up"
    assert direction(98) == "down"


def test_the_streak_counts_closed_weeks_only() -> None:
    goal = 2
    days = []
    for week in range(1, 4):
        monday = LUNES - timedelta(weeks=week)
        days += [monday, monday + timedelta(days=2)]
    days.append(LUNES)

    current = stats.frequency(days, goal, LUNES)

    assert current.done == 1
    assert current.streak == 3
    assert current.average == 1.5


def test_a_week_below_the_goal_breaks_the_streak() -> None:
    goal = 3
    days = [LUNES - timedelta(weeks=1), LUNES - timedelta(weeks=2)]

    assert stats.frequency(days, goal, LUNES).streak == 0


def test_the_volume_band_is_the_reference_range() -> None:
    assert stats.band(6) == "low"
    assert stats.band(14) == "ok"
    assert stats.band(24) == "high"
    assert stats.per_week(14, LUNES, LUNES + timedelta(weeks=4)) == 3.5


def test_records_are_per_rep_range_and_not_just_the_maximum() -> None:
    rows = [
        (LUNES, 5, 90.0),
        (LUNES, 8, 80.0),
        (LUNES, 20, 65.0),
        (LUNES + timedelta(days=7), 8, 82.5),
    ]

    found = {record.range: record for record in stats.records(rows)}

    assert found["1-5"].load == 90.0
    assert found["6-10"].load == 82.5
    assert found["11+"].load == 65.0
    assert found["11+"].reliable is False
    assert found["1-5"].reliable is True


def test_the_period_decides_where_it_starts() -> None:
    today = date(2026, 9, 18)
    first = date(2024, 1, 15)

    assert stats.starts_on("4w", today, first) == date(2026, 8, 21)
    assert stats.starts_on("all", today, first) == first
    assert stats.starts_on("all", today, None) == today


@pytest.fixture
async def setup(database_url: str):

    from arga_testing import fresh_modules

    engine = install(create_async_engine(database_url))
    async with engine.begin() as connection:
        await fresh_modules(connection, MODULE_ID)
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


async def train(
    api, day_offset: int, reps: int = 8, weight: str = "60", push: bool = False
) -> None:
    started = T0 + timedelta(days=day_offset)
    body: dict = {"started_at": started.isoformat()}
    if push:
        days = (await api.get("/today")).json()["plan"]["days"]
        body["plan_day_id"] = next(day["id"] for day in days if day["kind"] == "push")
    session = (await api.post("/sessions", json=body)).json()["id"]
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


async def test_without_a_single_session_it_answers_empty_instead_of_failing(api) -> None:
    body = (await api.get("/stats")).json()

    assert body["sessions"] == 0
    assert body["index"]["value"] is None
    assert body["frequency"]["done"] == 0
    assert len(body["muscles"]) > 10
    assert all(muscle["sets"] == 0 and muscle["value"] is None for muscle in body["muscles"])
    assert body["movers"] == []


async def test_a_set_counts_only_for_the_main_muscle_of_its_exercise(api) -> None:
    await train(api, day_offset=-1)

    body = (await api.get("/stats?period=all")).json()
    sets = {muscle["muscle"]: muscle["sets"] for muscle in body["muscles"]}

    assert body["sessions"] == 1
    assert sets["chest"] == 2
    assert sets["front_delts"] == 1
    assert sets["triceps"] == 0
    assert {muscle["band"] for muscle in body["muscles"]} <= {"low", "ok", "high"}


async def test_a_variant_that_goes_up_shows_up_as_a_mover(api) -> None:
    for week, weight in enumerate(["60", "60", "60", "70"]):
        await train(api, day_offset=(week - 4) * 7, weight=weight)

    movers = (await api.get("/stats?period=all")).json()["movers"]

    assert movers, "dos sesiones de la misma variante en el mismo centro dan un delta"
    assert movers[0]["delta"] > 0
    assert movers[0]["exercise"]
    assert movers[0]["gym"], "cada máquina es de un centro"


async def test_the_variant_screen_brings_its_points_and_its_records(api) -> None:
    for week, (reps, weight) in enumerate([(8, "60"), (8, "60"), (8, "60"), (5, "80")]):
        await train(api, day_offset=(week - 4) * 7, reps=reps, weight=weight)
    variant = (await api.get("/stats?period=all")).json()["movers"][0]["variant_id"]

    body = (await api.get(f"/stats/variants/{variant}?period=all")).json()

    assert body["variant_id"] == variant
    (machine,) = body["machines"]
    assert len(machine["points"]) == 2
    assert machine["best"]["e1rm"] == max(point["e1rm"] for point in machine["points"])
    assert {record["range"] for record in machine["records"]} == {"1-5", "6-10"}
    assert body["min_increment"] > 0


async def test_a_variant_that_does_not_exist_is_a_404_and_not_a_500(api) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    assert (await api.get(f"/stats/variants/{missing}")).status_code == 404
    assert (await api.get("/stats/muscles/alas")).status_code == 404


async def test_the_period_narrows_the_answer(api) -> None:
    await train(api, day_offset=-120)
    await train(api, day_offset=-1)

    recent = (await api.get("/stats?period=4w")).json()
    everything = (await api.get("/stats?period=all")).json()

    assert recent["sessions"] == 1
    assert everything["sessions"] == 2
    assert recent["since"] > everything["since"]


async def bench(api) -> str:
    catalogue = (await api.get("/catalogue")).json()
    return next(
        variant["id"]
        for exercise in catalogue["exercises"]
        for variant in exercise["variants"]
        if variant["name"] == "Press banca con barra"
    )


async def test_a_typo_is_set_aside_and_you_can_say_it_was_right(api) -> None:
    loads = ["60", "61", "60", "90", "61", "60", "62"]
    for n, weight in enumerate(loads):
        await train(api, day_offset=(n - len(loads)) * 7, weight=weight, push=True)
    variant = await bench(api)

    def odd(body):
        return next(p for p in body["machines"][0]["points"] if p["load"] == 90)

    before = (await api.get(f"/stats/variants/{variant}?period=all")).json()
    assert odd(before)["status"] == "high"
    assert odd(before)["reference"] is not None
    assert before["machines"][0]["excluded"] == 1

    assert (
        await api.put(f"/stats/points/{odd(before)['id']}", json={"verdict": "counted"})
    ).status_code == 204
    judged = (await api.get(f"/stats/variants/{variant}?period=all")).json()
    assert odd(judged)["status"] == "counted"
    assert odd(judged)["verdict"] == "counted"

    assert (await api.delete(f"/stats/points/{odd(before)['id']}")).status_code == 204
    after = (await api.get(f"/stats/variants/{variant}?period=all")).json()
    assert odd(after)["status"] == "high"
    assert odd(after)["load"] == 90


async def test_a_day_that_does_not_exist_cannot_be_judged(api) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    response = await api.put(f"/stats/points/{missing}", json={"verdict": "excluded"})

    assert response.status_code == 404


async def test_saying_the_machine_changed_splits_its_history(api) -> None:
    for n in range(4):
        await train(api, day_offset=(n - 4) * 7, push=True)
    variant = await bench(api)
    body = (await api.get(f"/stats/variants/{variant}?period=all")).json()
    machine = body["machines"][0]
    third = machine["points"][2]["day"]

    created = await api.post(
        "/stats/marks",
        json={"variant_id": variant, "gym_id": machine["gym_id"], "day": third, "kind": "split"},
    )
    split = (await api.get(f"/stats/variants/{variant}?period=all")).json()["machines"][0]

    assert created.status_code == 201
    assert [segment["start"] for segment in split["segments"]] == ["first", "mark"]
    assert split["segments"][1]["mark_id"] == created.json()["id"]

    assert (await api.delete(f"/stats/marks/{created.json()['id']}")).status_code == 204
    joined = (await api.get(f"/stats/variants/{variant}?period=all")).json()["machines"][0]
    assert len(joined["segments"]) == 1


async def test_with_a_bodyweight_dips_count_for_strength(api) -> None:
    for n in range(2):
        await train(api, day_offset=(n - 2) * 7, push=True)
    catalogue = (await api.get("/catalogue")).json()
    dips = next(
        variant["id"]
        for exercise in catalogue["exercises"]
        for variant in exercise["variants"]
        if variant["name"] == "Fondos lastrados"
    )

    without = (await api.get(f"/stats/variants/{dips}?period=all")).json()
    settings = (await api.put("/bodyweight", json={"kg": 80})).json()
    with_weight = (await api.get(f"/stats/variants/{dips}?period=all")).json()

    assert without["bodyweight"] is None
    assert without["machines"] == []
    assert settings["bodyweight"] == 80
    assert len(with_weight["machines"][0]["points"]) == 2
    assert with_weight["machines"][0]["points"][0]["load"] == 136


async def test_a_muscle_brings_its_strength_and_everything_that_trained_it(api) -> None:
    for week, weight in enumerate(["60", "62", "64", "66", "68", "70"]):
        await train(api, day_offset=(week - 6) * 7, weight=weight, push=True)

    body = (await api.get("/stats/muscles/chest?period=all")).json()

    assert body["name"] == "Pecho"
    assert body["value"] is not None and body["value"] > 100
    assert body["trend"]
    names = {exercise["variant"] for exercise in body["exercises"]}
    assert "Press banca con barra" in names
    assert all(exercise["gyms"] for exercise in body["exercises"])


async def test_the_notes_that_link_a_variant_show_up_in_it(api, setup) -> None:
    import json

    from arga_tenancy import current_user
    from arga_testing import fresh_modules

    for week, (reps, weight) in enumerate([(8, "60"), (8, "60"), (8, "60"), (5, "80")]):
        await train(api, day_offset=(week - 4) * 7, reps=reps, weight=weight)
    variant = (await api.get("/stats?period=all")).json()["movers"][0]["variant_id"]
    async with setup.begin() as connection:
        await fresh_modules(connection, "training", "notebook", fresh=["notebook"])
        for n, (note, title, removed) in enumerate(
            [
                ("n-1", "Técnica", False),
                ("n-1", "Técnica de banca", False),
                ("n-2", "Vieja", False),
                ("n-2", "Vieja", True),
            ]
        ):
            mention = {
                "app": "training",
                "id": variant,
                "note_id": note,
                "note_title": title,
                "note_href": f"/notebook/nota/{note}",
                "line": "Bajar la carga",
                "removed": removed,
            }
            await connection.execute(
                text(
                    "insert into kernel.events (ts, module, source, type, payload, user_id, "
                    "dedup_hash) values (:ts, 'notebook', 'app', 'notebook.mention', "
                    "cast(:payload as jsonb), :person, :dedup)"
                ),
                {
                    "ts": datetime(2026, 9, 28, 10, n, tzinfo=UTC),
                    "payload": json.dumps({"mention": mention}),
                    "person": current_user.get(),
                    "dedup": f"test-mention-{n}",
                },
            )
    try:
        body = (await api.get(f"/stats/variants/{variant}?period=all")).json()
    finally:
        async with setup.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'notebook'"))
            await connection.execute(text("delete from kernel.modules where id = 'notebook'"))

    assert body["notes"] == [
        {"title": "Técnica de banca", "href": "/notebook/nota/n-1", "line": "Bajar la carga"}
    ]


async def test_while_stats_computes_the_rest_of_training_still_answers(api, monkeypatch) -> None:
    await train(api, 0)
    slow = strength.build

    def build(*args, **kwargs):
        time.sleep(1.5)
        return slow(*args, **kwargs)

    monkeypatch.setattr(strength, "build", build)
    stats._KEPT.clear()

    async def nothing() -> None:
        return None

    monkeypatch.setattr(main, "warm_stats", nothing)
    done: dict[str, float] = {}

    async def timed(name: str, path: str) -> None:
        await api.get(path)
        done[name] = time.perf_counter()

    stats_call = asyncio.create_task(timed("stats", "/stats?period=3m"))
    await asyncio.sleep(0.2)
    await timed("today", "/today")
    await stats_call

    assert done["today"] < done["stats"]


async def test_stats_reuses_what_it_computed_while_nothing_changes(api, monkeypatch) -> None:
    await train(api, -10)
    await train(api, -8)
    calls = []
    slow = strength.build
    monkeypatch.setattr(strength, "build", lambda *a, **k: calls.append(1) or slow(*a, **k))
    stats._KEPT.clear()

    first = (await api.get("/stats?period=3m")).json()
    again = (await api.get("/stats?period=3m")).json()
    assert len(calls) == 1
    assert again == first

    await train(api, -4)
    assert len(calls) == 2
    await api.get("/stats?period=3m")
    assert len(calls) == 2


async def test_opening_today_leaves_stats_computed(api, monkeypatch) -> None:
    await train(api, 0)
    await train(api, 2)
    stats._KEPT.clear()
    await api.get("/today")
    calls = []
    slow = strength.build
    monkeypatch.setattr(strength, "build", lambda *a, **k: calls.append(1) or slow(*a, **k))

    response = await api.get("/stats?period=3m")

    assert response.status_code == 200
    assert calls == []
