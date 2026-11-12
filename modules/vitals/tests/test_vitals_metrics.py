from __future__ import annotations

from sqlalchemy import text
from test_vitals_records import steps

import arga_contracts as contracts
from arga_contracts import metrics as publish
from vitals import metrics
from vitals.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_vitals"'))
        found = await metrics.build(connection)
    for one in found:
        assert one == contracts.metric("vitals", **one)
    return {contracts.metric_identity(one): one for one in found}


async def test_steps_weight_and_ldl_are_figures_of_their_day(api, schema, person) -> None:
    checkup = (await api.post("/checkups", json={"day": "2026-03-12"})).json()
    await api.post(
        f"/checkups/{checkup['id']}/results",
        json={"analyte": "ldl", "value": 4.19, "unit": "mmol/L"},
    )
    await api.post(
        f"/checkups/{checkup['id']}/results",
        json={"analyte": "cholesterol", "value": 231, "unit": "mg/dL"},
    )
    await api.post("/weight", json={"kg": 80.4, "day": "2026-09-01"})
    await api.post("/weight", json={"kg": 80.0, "day": "2026-09-01"})
    try:
        await steps(schema, person, "2026-09-01", 9432)
        found = await built()
    finally:
        async with schema.begin() as connection:
            await connection.execute(
                text("delete from kernel.events where dedup_hash like 'records-steps:%'")
            )

    assert found["vitals.steps@2026-09-01"]["value"] == 9432
    assert found["vitals.steps@2026-09-01"]["kind"] == "amount"
    assert found["vitals.weight@2026-09-01"]["value"] == 80.2
    assert found["vitals.weight@2026-09-01"]["kind"] == "level"
    assert found["vitals.ldl@2026-03-12"]["unit"] == "mg/dL"
    assert round(found["vitals.ldl@2026-03-12"]["value"]) == 162
    assert found["vitals.lab:cholesterol@2026-03-12"]["label"] == "Colesterol total"
    assert found["vitals.lab:cholesterol@2026-03-12"]["value"] == 231


async def test_the_history_goes_once_to_the_outbox(api, schema) -> None:
    await api.post("/weight", json={"kg": 80.0, "day": "2026-09-01"})
    await api.post("/weight", json={"kg": 79.6, "day": "2026-09-02"})
    for expected in (2, 0):
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_vitals"'))
            counts = await publish.publish(connection, "vitals", await metrics.build(connection))
        assert counts["added"] == expected


async def test_two_checkups_on_one_day_publish_what_the_cover_shows(api, schema) -> None:
    analytes = (await api.get("/analytes")).json()[:40]
    plan = [
        ("2026-09-15", "Prevención", 120),
        ("2026-09-15", "Laboratorio", 150),
        ("2026-03-02", "Centro A", 115),
        ("2025-03-04", "Centro A", 110),
        ("2024-03-02", "Centro A", 100),
    ]
    for day, center, base in plan:
        checkup = (await api.post("/checkups", json={"day": day, "center": center})).json()["id"]
        for n, analyte in enumerate(analytes):
            body = {"analyte": analyte["id"], "value": base + n / 10}
            if analyte["unit"]:
                body["unit"] = analyte["unit"]
            await api.post(f"/checkups/{checkup}/results", json=body)

    found = await built()
    cover = (await api.get("/labs/ldl")).json()
    same_day = [one for one in found.values() if one["day"] == "2026-09-15"]

    assert same_day and all(one["value"] >= 150 for one in same_day if "lab" in one["key"])
    assert found["vitals.ldl@2026-09-15"]["value"] == cover["points"][-1]["value"]
