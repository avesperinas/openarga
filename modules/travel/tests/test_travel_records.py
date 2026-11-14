from __future__ import annotations

from datetime import date

from sqlalchemy import text
from travel_kit import BRUGES, GHENT, make_trip, place, stay

import arga_contracts as contracts
from travel import records
from travel.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def test_a_trip_its_countries_and_its_days(api) -> None:
    trip = await make_trip(
        api,
        "Flandes",
        "2025-04-10",
        "2025-04-12",
        travellers=2,
        companions=["Ane"],
        tags=["ciudades"],
    )
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12")
    ghent = await place(api, GHENT)
    bruges = next(one for one in (await api.get("/places")).json() if one["name"] == "Brujas")
    await api.post(
        f"/trips/{trip['id']}/legs",
        json={
            "from_place_id": bruges["id"],
            "to_place_id": ghent["id"],
            "mode": "train",
            "travelled_on": "2025-04-11",
        },
    )
    await api.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "lodging", "concept": "Hotel", "amount_eur": "120.50"},
    )

    found = await built()

    ficha = found[f"trip:{trip['id']}"]
    assert ficha["title"] == "2025-04 Flandes"
    assert ficha["folder"] == "Viajes"
    assert ficha["href"] == f"/travel/viajes/{trip['id']}"
    props = ficha["properties"]
    assert props["inicio"] == "2025-04-10" and props["fin"] == "2025-04-12"
    assert props["dias"] == 3 and props["noches"] == 2 and props["viajeros"] == 2
    assert props["acompanantes"] == ["Ane"] and props["tags"] == ["ciudades"]
    assert props["gasto_persona_eur"] == 120.5
    assert props["paises"] == ["Bélgica"]
    body = ficha["body"]
    first, last = (contracts.records.long_date(date(2025, 4, day)) for day in (10, 12))
    assert body.startswith(f"Del {first} al {last} · 3 días, 2 noches")
    assert "Países: [[travel:country:BE|Bélgica]]" in body
    assert "| 2025-04-11 | Brujas → Gante | tren |" in body
    assert "120,50 € por persona, 241,00 € el grupo" in body

    belgium = found["country:BE"]
    assert belgium["title"] == "Bélgica" and belgium["folder"] == "Países"
    assert f"- [[travel:trip:{trip['id']}|2025-04 Flandes]]" in belgium["body"]

    assert found["day:2025-04-11"]["body"] == (
        f"- De viaje: [[travel:trip:{trip['id']}|Flandes]] (día 2 de 3) · durmiendo en Brujas\n"
        "- Tren: Brujas → Gante"
    )
    assert "day:2025-04-12" in found and "day:2025-04-13" not in found
