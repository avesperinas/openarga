from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-000000000b0b")

CONNECTION = text("""
    insert into hub.hub_connection (id, provider, label, config)
    values (:id, :provider, :label, cast(:config as jsonb))
    on conflict (id) do nothing
""")


def connections(persona: Persona, today: date) -> list[tuple[str, str, dict[str, Any]]]:
    found: list[tuple[str, str, dict[str, Any]]] = []
    if persona.country:
        found.append(
            ("holidays", "Holidays", {"country": persona.country, "region": persona.region})
        )
    if persona.key == "alex":
        found.append(
            ("football", "Example FC", {"team": "11", "league": "esp.1", "team_name": "Example FC"})
        )
        found.append(
            (
                "prices",
                "Prices",
                {
                    "instruments": [
                        {
                            "isin": "",
                            "kind": "listed",
                            "name": "Example world ETF",
                            "currency": "EUR",
                            "since": (today - timedelta(days=60)).isoformat(),
                            "yahoo": "VWCE.DE",
                        }
                    ]
                },
            )
        )
    else:
        found.append(("formula1", "Formula 1", {"sessions": ["race", "qualifying"]}))
    return found


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    for provider, label, config in connections(persona, today):
        await connection.execute(
            CONNECTION,
            {
                "id": uuid5(NAMESPACE, f"{persona.key}:{provider}"),
                "provider": provider,
                "label": label,
                "config": json.dumps(config),
            },
        )
