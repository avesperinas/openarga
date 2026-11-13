from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

import arga_contracts as contracts
from arga_contracts import records as write
from vitals import records
from vitals.db import engine

KERNEL_LIKE = "kernel_as_in_production"


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_vitals"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def steps(schema, person, day: str, count: int) -> None:
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "do $$ begin if not exists "
                f"(select 1 from pg_roles where rolname = '{KERNEL_LIKE}') "
                f"then create role {KERNEL_LIKE} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select on kernel.events to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select on kernel.modules to {KERNEL_LIKE}"))
        await connection.execute(text(f"alter view vitals.events owner to {KERNEL_LIKE}"))
        await connection.execute(
            text(
                "insert into kernel.events (ts, ingested_at, module, source, type, payload, "
                "dedup_hash, user_id) values (:ts, :ts, 'hub', 'apple_health', "
                "'health.steps', cast(:payload as jsonb), :dedup, :user)"
            ),
            {
                "ts": datetime.fromisoformat(f"{day}T20:00:00+00:00"),
                "payload": json.dumps({"date": day, "steps": count}),
                "dedup": f"records-steps:{day}:{count}:{person}",
                "user": person,
            },
        )


async def test_a_checkup_is_a_sheet_and_each_day_says_weight_and_steps(api, schema, person) -> None:
    checkup = (
        await api.post("/checkups", json={"day": "2026-03-12", "center": "Occupational health"})
    ).json()
    await api.post(
        f"/checkups/{checkup['id']}/results",
        json={"analyte": "ldl", "value": 162, "unit": "mg/dL", "ref_high": 130},
    )
    await api.post(
        f"/checkups/{checkup['id']}/results",
        json={"analyte": "hdl", "value": 55, "unit": "mg/dL", "ref_low": 40},
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

    sheet = found[f"checkup:{checkup['id']}"]
    assert sheet["title"] == "2026-03-12 Occupational health"
    assert sheet["folder"] == "Check-ups"
    assert sheet["properties"] == {
        "date": "2026-03-12",
        "values": 2,
        "center": "Occupational health",
        "out_of_range": 1,
    }
    assert "| LDL cholesterol | **162** | mg/dL | ≤ 130 |" in sheet["body"]
    assert "1 out of range, in bold." in sheet["body"]

    day = found["day:2026-09-01"]
    assert day["properties"] == {"weight_kg": 80.2, "steps": 9432}
    assert day["body"].startswith("- Weight: 80")
    assert "- Steps: 9" in day["body"]
    assert found["day:2026-03-12"]["body"] == (
        f"- Check-up: [[vitals:checkup:{checkup['id']}|2026-03-12 Occupational health]]"
    )

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_vitals"'))
        queued = await write.publish(connection, "vitals", await records.build(connection))
    assert queued["added"] == len(found)
