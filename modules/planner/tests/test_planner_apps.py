from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_tenancy import USER_HEADER
from planner import apps

GYM = "probe_gym"


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema, person, monkeypatch):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": GYM})
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:m, '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {
                "m": GYM,
                "manifest": json.dumps(
                    {
                        "id": GYM,
                        "name": "Gimnasio",
                        "version": "0.1.0",
                        "database": {"schema": GYM, "role": f"mod_{GYM}", "reads": []},
                        "api": {"prefix": f"/api/{GYM}"},
                        "ui": {"widgets": [], "view": f"/{GYM}"},
                        "publishes": [{"type": f"{GYM}.session", "contract": "agenda"}],
                    }
                ),
            },
        )
    monkeypatch.setattr(apps, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        c.headers[USER_HEADER] = str(person)
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": GYM})
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": GYM})
    await kernel_db.engine().dispose()


START = datetime(2026, 10, 6, 16, 0, tzinfo=UTC)


def session(key: str, **changes) -> dict:
    return {
        "uid": f"{GYM}:session:{key}",
        "title": "Torso",
        "start": "2026-10-06T18:00:00+02:00",
        "end": "2026-10-06T19:00:00+02:00",
        "all_day": False,
        "tz": "Europe/Madrid",
        "status": "confirmed",
        "href": f"/{GYM}/sesion/{key}",
        **changes,
    }


async def publish(
    kernel, item: dict, event_type: str = f"{GYM}.session", at=None, **beside
) -> None:
    payload = {"agenda": item, **beside}
    response = await kernel.post(
        "/events",
        json={
            "ts": (at or datetime.now(UTC)).isoformat(),
            "module": GYM,
            "source": "app",
            "type": event_type,
            "payload": payload,
            "dedup_hash": hashlib.sha256(
                f"{event_type}:{json.dumps(payload, sort_keys=True)}".encode()
            ).hexdigest(),
        },
    )
    assert response.status_code in (200, 201), response.text


async def week(api) -> list[dict]:
    await api.get("/calendars")
    response = await api.get(
        "/occurrences",
        params={
            "from": (START - timedelta(days=1)).isoformat(),
            "to": (START + timedelta(days=2)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_what_an_app_publishes_shows_up_in_its_own_layer(api, kernel) -> None:
    await publish(kernel, session("1"))

    [found] = await week(api)
    layers = (await api.get("/calendars")).json()
    [layer] = [one for one in layers if one["origin"] == "app"]
    assert layer["name"] == "Gimnasio"
    assert layer["app"] == GYM
    assert found["calendar_id"] == layer["id"]
    assert found["title"] == "Torso"
    assert found["href"] == f"/{GYM}/sesion/1"


async def test_the_layer_is_born_once(api, kernel) -> None:
    await publish(kernel, session("1"))
    await publish(kernel, session("2", title="Pierna"))

    await week(api)
    await week(api)

    layers = [one for one in (await api.get("/calendars")).json() if one["origin"] == "app"]
    assert len(layers) == 1


async def test_the_names_are_asked_before_anything_is_written(api, kernel, monkeypatch) -> None:
    await publish(kernel, session("1"))
    written: list[int] = []
    asked = apps.app_names

    async def names() -> dict[str, str]:
        from planner.db import engine

        async with engine().connect() as other:
            written.append(
                int(
                    await other.scalar(
                        text(
                            "select count(*) from pg_locks l join pg_class c on c.oid = l.relation "
                            "where c.relname = 'planner_app_event' and l.mode = 'RowExclusiveLock'"
                        )
                    )
                )
            )
        return await asked()

    monkeypatch.setattr(apps, "app_names", names)

    await week(api)

    assert written == [0]


async def test_the_latest_version_wins(api, kernel) -> None:
    await publish(kernel, session("1"), at=START)
    await week(api)
    await publish(
        kernel,
        session("1", end="2026-10-06T19:30:00+02:00"),
        at=START + timedelta(hours=1),
    )

    [found] = await week(api)
    assert found["end"] == "2026-10-06T19:30:00+02:00"


async def test_what_is_cancelled_leaves_the_calendar(api, kernel) -> None:
    await publish(kernel, session("1"), at=START)
    assert len(await week(api)) == 1

    await publish(kernel, session("1", status="cancelled"), at=START + timedelta(hours=1))

    assert await week(api) == []


async def test_nothing_from_an_app_can_be_edited_here(api, kernel) -> None:
    await publish(kernel, session("1"))
    [found] = await week(api)

    response = await api.post(f"/events/{found['event_id']}/cancel", json={"scope": "all"})

    assert response.status_code in (404, 409, 422)
    assert len(await week(api)) == 1


async def test_nobody_creates_an_event_in_an_app_layer(api, kernel) -> None:
    await publish(kernel, session("1"))
    await week(api)
    [layer] = [one for one in (await api.get("/calendars")).json() if one["origin"] == "app"]

    response = await api.post(
        "/events",
        json={
            "calendar_id": layer["id"],
            "title": "Colado",
            "all_day": False,
            "start": "2026-10-07T10:00:00",
            "end": "2026-10-07T11:00:00",
            "tz": "Europe/Madrid",
        },
    )

    assert response.status_code in (409, 422)


async def test_what_does_not_fit_is_dropped_and_the_rest_arrives(api, kernel) -> None:
    await publish(kernel, session("bad", start="mañana"))
    await publish(kernel, session("2"))

    assert [one["title"] for one in await week(api)] == ["Torso"]


async def test_what_the_app_does_not_declare_never_arrives(api, kernel) -> None:
    await publish(kernel, session("1"), event_type=f"{GYM}.secret")

    assert await week(api) == []


async def test_search_finds_what_comes_from_an_app(api, kernel) -> None:
    await publish(kernel, session("1"))
    await week(api)

    found = (await api.get("/search", params={"q": "torso"})).json()

    assert [one["href"] for one in found] == [f"/{GYM}/sesion/1"]


async def test_an_app_layer_can_be_seen_as_background(api, kernel) -> None:
    await publish(kernel, session("1"))
    await week(api)
    [layer] = [one for one in (await api.get("/calendars")).json() if one["origin"] == "app"]

    changed = await api.patch(f"/calendars/{layer['id']}", json={"display": "background"})

    assert changed.status_code == 200, changed.text
    assert changed.json()["display"] == "background"
    assert changed.json()["origin"] == "app"


async def test_the_last_one_published_wins_even_with_an_earlier_instant(api, kernel) -> None:
    await publish(kernel, session("1"), at=START + timedelta(hours=3))
    await week(api)
    await publish(
        kernel,
        session("1", start="2026-10-06T17:00:00+02:00", end="2026-10-06T18:00:00+02:00"),
        at=START,
    )

    [found] = await week(api)
    assert found["start"] == "2026-10-06T17:00:00+02:00"


async def test_an_app_that_does_not_serve_moving_stays_still(api, kernel) -> None:
    await publish(kernel, session("1"))
    await week(api)

    [layer] = [one for one in (await api.get("/calendars")).json() if one["origin"] == "app"]

    assert layer["movable"] is False


async def test_what_asks_for_its_own_layer_goes_to_a_separate_layer_of_the_app(api, kernel) -> None:
    await publish(kernel, session("1"))
    await publish(kernel, session("2", title="Vuelo"), layer="Trayectos")

    found = {one["title"]: one["calendar_id"] for one in await week(api)}
    layers = {
        one["name"]: one for one in (await api.get("/calendars")).json() if one["origin"] == "app"
    }

    assert set(layers) == {"Gimnasio", "Gimnasio · Trayectos"}
    assert layers["Gimnasio · Trayectos"]["app"] == f"{GYM}:Trayectos"
    assert found == {
        "Torso": layers["Gimnasio"]["id"],
        "Vuelo": layers["Gimnasio · Trayectos"]["id"],
    }
    assert layers["Gimnasio · Trayectos"]["movable"] is False

    await api.patch(f"/calendars/{layers['Gimnasio']['id']}", json={"display": "background"})
    shown = {
        one["name"]: one["display"]
        for one in (await api.get("/calendars")).json()
        if one["origin"] == "app"
    }
    assert shown == {"Gimnasio": "background", "Gimnasio · Trayectos": "events"}


async def test_what_was_kept_without_a_layer_moves_when_it_asks_for_one(
    api, kernel, schema
) -> None:
    await publish(kernel, session("1", title="Vuelo"), layer="Trayectos")
    await week(api)
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_planner"'))
        await connection.execute(text("update planner.planner_app_event set layer = null"))

    [found] = await week(api)
    [aside] = [
        one for one in (await api.get("/calendars")).json() if one["app"] == f"{GYM}:Trayectos"
    ]
    assert found["calendar_id"] == aside["id"]


async def test_a_layer_that_does_not_fit_is_ignored(api, kernel) -> None:
    await publish(kernel, session("1"), layer="x" * 80)

    await week(api)
    assert [
        one["app"] for one in (await api.get("/calendars")).json() if one["origin"] == "app"
    ] == [GYM]


async def test_a_layer_of_your_own_frees_the_days_an_app_puts_all_day(api, kernel) -> None:
    await publish(
        kernel,
        session("v1", title="Vacaciones", start="2026-10-07", end="2026-10-09", all_day=True),
    )
    await week(api)
    [app_layer] = [one for one in (await api.get("/calendars")).json() if one["origin"] == "app"]
    created = await api.post(
        "/calendars",
        json={
            "name": "Trabajo",
            "tone": 3,
            "display": "background",
            "days_off_from": [app_layer["id"]],
        },
    )
    assert created.status_code == 201, created.text
    work = created.json()
    series = await api.post(
        "/events",
        json={
            "calendar_id": work["id"],
            "title": "Jornada",
            "start": "2026-10-05T08:30:00+02:00",
            "end": "2026-10-05T18:00:00+02:00",
            "tz": "Europe/Madrid",
            "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
        },
    )
    assert series.status_code == 201, series.text

    response = await api.get(
        "/occurrences",
        params={"from": "2026-10-05T00:00:00+02:00", "to": "2026-10-10T00:00:00+02:00"},
    )

    days = sorted(one["start"][:10] for one in response.json() if one["calendar_id"] == work["id"])
    assert days == ["2026-10-05", "2026-10-06", "2026-10-09"]


async def test_a_layer_named_after_its_id_takes_the_manifest_name_later(
    api, kernel, monkeypatch
) -> None:
    await publish(kernel, session("1"))

    async def down() -> dict[str, str]:
        return {}

    asked = apps.app_names
    monkeypatch.setattr(apps, "app_names", down)
    await week(api)
    [layer] = [one for one in (await api.get("/calendars")).json() if one["origin"] == "app"]
    assert layer["name"] == GYM.capitalize()

    monkeypatch.setattr(apps, "app_names", asked)
    await week(api)
    [layer] = [one for one in (await api.get("/calendars")).json() if one["origin"] == "app"]
    assert layer["name"] == "Gimnasio"
