from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from outings import hub

PLANNER = "probe_planner"
T0 = datetime(2026, 10, 8, 17, 0, tzinfo=UTC)


@pytest.fixture
async def planner(schema):
    async with schema.begin() as connection:
        await connection.execute(
            text("delete from kernel.events where module = :m"), {"m": PLANNER}
        )
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:m, '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {
                "m": PLANNER,
                "manifest": json.dumps(
                    {"publishes": [{"type": f"{PLANNER}.plan", "contract": "trip"}]}
                ),
            },
        )
    yield schema
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": PLANNER})
        await connection.execute(
            text("delete from kernel.events where module = :m"), {"m": PLANNER}
        )


async def planned(engine, at: datetime, **item) -> None:
    body = {
        "id": "trip:1",
        "title": "Budapest",
        "phase": "plan",
        "href": "/probe/viajes/1",
        "starts_on": "2027-11-11",
        "ends_on": "2027-11-14",
        "image": None,
        "detail": "4 days · 2 travellers",
        "removed": False,
        **item,
    }
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash) "
                "values (:ts, :m, 'app', :type, cast(:payload as jsonb), :dedup)"
            ),
            {
                "ts": at,
                "m": PLANNER,
                "type": f"{PLANNER}.plan",
                "payload": json.dumps({"trip": body}),
                "dedup": f"{body['id']}:{at.isoformat()}",
            },
        )


async def test_a_trip_planned_elsewhere_shows_with_its_phase_and_links_there(api, planner) -> None:
    await planned(planner, T0)
    await planned(
        planner,
        T0,
        id="idea:2",
        title="Japan in sakura",
        phase="idea",
        starts_on=None,
        ends_on=None,
        href="/probe/ideas/2",
    )

    found = (await api.get("/planned")).json()

    assert [(one["title"], one["phase"], one["href"]) for one in found] == [
        ("Budapest", "plan", "/probe/viajes/1"),
        ("Japan in sakura", "idea", "/probe/ideas/2"),
    ]
    assert found[0]["app"] == PLANNER


async def test_the_last_version_counts_and_what_is_removed_is_gone(api, planner) -> None:
    await planned(planner, T0)
    await planned(planner, T0 + timedelta(hours=1), phase="upcoming", title="Budapest y Viena")
    assert [(o["title"], o["phase"]) for o in (await api.get("/planned")).json()] == [
        ("Budapest y Viena", "upcoming")
    ]

    await planned(planner, T0 + timedelta(hours=2), removed=True)
    assert (await api.get("/planned")).json() == []


async def test_a_trip_wish_becomes_an_idea_where_trips_are_planned(api, monkeypatch) -> None:
    made = await api.post(
        "/wishes",
        json={
            "kind": "trip",
            "name": "Escocia",
            "body": "Highlands en coche",
            "place": {"name": "Edimburgo", "lat": 55.9533, "lon": -3.1883},
        },
    )
    assert made.status_code == 201, made.text
    asked: list[tuple[str, dict]] = []

    async def kernel(name: str, body: dict) -> dict:
        asked.append((name, body))
        return {"id": "i1", "href": "/travel/ideas/i1", "already": False}

    monkeypatch.setattr(hub, "capability", kernel)
    idea = await api.post(f"/wishes/{made.json()['id']}/idea")

    assert idea.status_code == 200, idea.text
    assert idea.json() == {"href": "/travel/ideas/i1", "already": False}
    assert asked == [
        (
            "trips.idea",
            {
                "title": "Escocia",
                "place": "Edimburgo",
                "lat": 55.9533,
                "lon": -3.1883,
                "notes": "Highlands en coche",
            },
        )
    ]


async def test_only_a_trip_becomes_an_idea(api) -> None:
    made = await api.post("/wishes", json={"kind": "eat", "name": "Asador"})

    refused = await api.post(f"/wishes/{made.json()['id']}/idea")

    assert refused.status_code == 409, refused.text
