from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-000000000b0b")

CONNECTION = text("""
    insert into hub.hub_connection (id, provider, label, config, paused, consent_expires_at)
    values (:id, :provider, :label, cast(:config as jsonb), :paused, :expires)
    on conflict (id) do nothing
""")

RUN = text("""
    insert into hub.hub_run
        (id, connection_id, capability, operation, started_at, finished_at, outcome, emitted,
         detail)
    values (:id, :connection, 'sync', :operation, :started, :finished, :outcome, :emitted,
            :detail)
    on conflict (id) do nothing
""")

HEALTHY, FAILING, PAUSED, EXPIRING = "healthy", "failing", "paused", "expiring"
STATES = {
    "Work calendar": FAILING,
    "Birthdays calendar": PAUSED,
    "Pilates timetable": EXPIRING,
}
FAILURE = "The calendar address did not answer in time. It will try again on its own."


def connections(persona: Persona, today: date) -> list[tuple[str, str, dict[str, Any]]]:
    found: list[tuple[str, str, dict[str, Any]]] = []
    if persona.country:
        found.append(
            ("holidays", "Holidays", {"country": persona.country, "region": persona.region})
        )
    if persona.key == "alex":
        found.append(
            ("football", "Football", {"team": "11", "league": "esp.1", "team_name": "Example FC"})
        )
        found.append(("ical", "Work calendar", {"url": "https://calendar.example.org/work.ics"}))
        found.append(("apple_podcasts", "Podcasts", {}))
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
        found.append(
            ("ical", "Birthdays calendar", {"url": "https://calendar.example.org/birthdays.ics"})
        )
        found.append(
            ("ical", "Pilates timetable", {"url": "https://studio.example.org/timetable.ics"})
        )
    return found


def _runs(state: str, today: date, zone_now: datetime) -> list[tuple[int, str, int, str | None]]:
    if state == FAILING:
        return [
            (hours, "error" if hours < 40 else "ok", 0 if hours < 40 else 9,
             FAILURE if hours < 40 else None)
            for hours in (2, 14, 26, 50, 74, 98)
        ]  # fmt: skip
    if state == PAUSED:
        return [(24 * 12 + n * 24, "ok", 2, None) for n in range(0, 8)]
    return [(n * 12 + 1, "ok", (n * 3) % 17 + 2, None) for n in range(0, 14)]


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    now = datetime.combine(today, time(8, 0), UTC)
    for provider, label, config in connections(persona, today):
        identity = uuid5(NAMESPACE, f"{persona.key}:{provider}")
        if provider == "ical":
            identity = uuid5(NAMESPACE, f"{persona.key}:{provider}:{label}")
        state = STATES.get(label, HEALTHY)
        await connection.execute(
            CONNECTION,
            {
                "id": identity,
                "provider": provider,
                "label": label,
                "config": json.dumps(config),
                "paused": state == PAUSED,
                "expires": now + timedelta(days=9) if state == EXPIRING else None,
            },
        )
        for number, (hours, outcome, emitted, detail) in enumerate(_runs(state, today, now)):
            started = now - timedelta(hours=hours)
            await connection.execute(
                RUN,
                {
                    "id": uuid5(NAMESPACE, f"{identity}:run-{number}"),
                    "connection": identity,
                    "operation": "sync",
                    "started": started,
                    "finished": started + timedelta(seconds=4),
                    "outcome": outcome,
                    "emitted": emitted,
                    "detail": detail,
                },
            )
