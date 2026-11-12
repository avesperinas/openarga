from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import text

from arga_contracts import sources
from outings import agenda, common
from outings.db import engine

IRATI = {
    "name": "Selva de Irati",
    "display_name": "Selva de Irati, Orbaizeta, Navarra, 31671, Spain",
    "lat": 42.98,
    "lon": -1.17,
    "osm_type": "way",
    "osm_id": 101,
    "kind": "forest",
    "country_code": "ES",
    "region_code": "ES-NA",
}
BARDENAS = {
    "name": "Bardenas Reales",
    "display_name": "Bardenas Reales, Arguedas, Navarra, Spain",
    "lat": 42.2,
    "lon": -1.48,
    "osm_type": "relation",
    "osm_id": 102,
    "kind": "nature_reserve",
    "country_code": "ES",
    "region_code": "ES-NA",
}


async def make_wish(api, name="Selva de Irati", kind="getaway", **extra) -> dict:
    response = await api.post("/wishes", json={"kind": kind, "name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def jpeg(width: int = 2400, height: int = 1800) -> bytes:
    import io

    from PIL import Image

    image = Image.linear_gradient("L").resize((width, height)).convert("RGB")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=95)
    return out.getvalue()


CONNECTION = str(uuid4())
TODAY = common.today()


def leisure(title: str, starts: date, ends: date | None = None, **extra) -> dict:
    payload = {
        "connection": CONNECTION,
        "key": f"k-{title}",
        "title": title,
        "starts_on": starts.isoformat(),
        "ends_on": (ends or starts).isoformat(),
        "time": None,
        "venue": "Synthetic hall",
        "town": "Pamplona",
        "category": "stage",
        "summary": "A test event.",
        "link": f"https://agenda.example/{title}",
        "source_name": "Synthetic agenda",
        "source_page": "https://agenda.example/agenda",
        "recurring": False,
        **extra,
    }
    payload["fingerprint"] = f"{hash(tuple(sorted(map(str, payload.items())))) & 0xFFFFFFFF:08x}"
    sources.check("leisure.event", payload)
    return payload


class Hub:
    def __init__(self, kernel: AsyncClient) -> None:
        self.kernel = kernel

    async def post(self, kind: str, payload: dict, dedup: str) -> None:
        response = await self.kernel.post(
            "/events",
            json={
                "ts": datetime.now(UTC).isoformat(),
                "module": "hub",
                "source": "prueba",
                "type": kind,
                "payload": payload,
                "dedup_hash": dedup,
            },
        )
        assert response.status_code in (200, 201), response.text

    async def bring(self, *events: dict) -> None:
        for event in events:
            await self.post(
                "leisure.event",
                event,
                f"leisure:{CONNECTION}:{event['key']}:{event['fingerprint']}",
            )

    async def removed(self) -> None:
        await self.post(
            "hub.connection",
            {
                "connection": CONNECTION,
                "provider": "prueba",
                "label": "Synthetic agenda",
                "state": "removed",
                "removed": True,
                "paused": False,
                "produces": ["leisure.event"],
            },
            f"connection:{CONNECTION}:removed",
        )


async def derive() -> dict:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_outings"'))
        return await agenda.derive(connection)
