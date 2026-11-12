from __future__ import annotations

from sqlalchemy import text
from travel_kit import make_trip

import arga_contracts as contracts
from travel import plans
from travel.db import engine


async def published(connection) -> list[dict]:
    rows = await connection.execute(
        text("select payload from travel.travel_outbox where type = 'travel.plan' order by id")
    )
    return [row.payload[contracts.TRIP] for row in rows]


async def refresh() -> tuple[int, list[dict]]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        queued = await plans.refresh(connection)
        return queued, await published(connection)


async def test_ideas_and_plans_go_out_once_and_what_is_done_is_withdrawn(api) -> None:
    trip = await make_trip(api, "Budapest", "2027-11-11", "2027-11-14", status="plan")
    idea = await api.post("/ideas", json={"title": "Japón en sakura", "months": [3, 4]})
    assert idea.status_code == 201, idea.text
    await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")

    first, out = await refresh()
    again, _ = await refresh()

    assert first == 2 and again == 0
    by_id = {one["id"]: one for one in out}
    assert by_id[f"trip:{trip['id']}"]["phase"] == "plan"
    assert by_id[f"trip:{trip['id']}"]["href"] == f"/travel/viajes/{trip['id']}"
    assert by_id[f"idea:{idea.json()['id']}"]["detail"] == "mar o abr"

    await api.put(f"/trips/{trip['id']}/archived", json={"archived": True})
    withdrawn, out = await refresh()

    assert withdrawn == 1
    assert out[-1] == {**by_id[f"trip:{trip['id']}"], "removed": True}


async def test_another_app_turns_a_wish_into_an_idea_through_the_kernel_only(
    api, monkeypatch
) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "el-token")
    body = {"title": "Escocia", "place": "Edimburgo", "lat": 55.9533, "lon": -3.1883}
    token = {"x-module-token": "el-token", "x-arga-module": "outings"}

    refused = await api.post("/capabilities/trips.idea", json=body)
    unknown = await api.post("/capabilities/trips.erase", json=body, headers=token)
    made = await api.post("/capabilities/trips.idea", json=body, headers=token)
    again = await api.post("/capabilities/trips.idea", json=body, headers=token)
    idea = (await api.get(f"/ideas/{made.json()['id']}")).json()

    assert refused.status_code == 401
    assert unknown.status_code == 404
    assert made.status_code == 200, made.text
    assert made.json()["already"] is False
    assert made.json()["href"] == f"/travel/ideas/{made.json()['id']}"
    assert again.json() == {**made.json(), "already": True}
    assert [one["place"]["name"] for one in idea["places"]] == ["Edimburgo"]
