from __future__ import annotations

from sqlalchemy import text

import arga_contracts as contracts
from macros import records
from macros.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_macros"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def test_each_day_eaten_goes_to_its_note_with_its_macros(api, world) -> None:
    logged = await api.post(
        "/entries",
        json={
            "eaten_at": "2026-09-28T12:30:00+02:00",
            "items": [
                {
                    "kind": "quick",
                    "name": "Pintxo",
                    "quantity": 400,
                    "unit": "kcal",
                    "quick": {"protein": 20},
                },
                {"kind": "water", "quantity": 500, "unit": "ml"},
            ],
        },
    )
    assert logged.status_code == 201, logged.text
    await api.put("/target", json={"kcal": 2000, "protein": 140, "valid_from": "2026-09-01"})

    found = await built()

    day = found["day:2026-09-28"]
    assert day["day"] == "2026-09-28"
    assert day["href"] == "/macros/day/2026-09-28"
    assert day["properties"] == {"kcal": 400, "protein_g": 20.0}
    lines = day["body"].split("\n")
    assert lines[0] == "400 kcal · 20 g protein"
    assert lines[2].startswith("- 12:30 · Pintxo (400 kcal)")
    assert lines[2].endswith("· 400 kcal")

    target = found["target"]
    assert target["properties"] == {"since": "2026-09-01", "kcal": 2000.0, "protein_g": 140.0}
    assert "- Energy: 2,000 kcal" in target["body"]
