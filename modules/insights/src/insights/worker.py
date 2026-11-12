from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from arga_contracts.records import Every
from arga_tenancy import as_user, kernel_url, users
from insights import craft, insights, passes, picks, pills, tastes, voice
from insights.db import engine

MODULE = "insights"
ROLE = f"mod_{MODULE}"
INTERVAL_SECONDS = float(os.environ.get("WORKER_INTERVAL_SECONDS", "60"))
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker.alive"))
LOOK_EVERY = float(os.environ.get("PASS_EVERY_SECONDS", "3600"))
LOOKED: dict[tuple[object, str], float] = {}
PILL_EVERY = float(os.environ.get("PILL_EVERY_SECONDS", "300"))
NOTIFY = Every(float(os.environ.get("NOTIFY_EVERY_SECONDS", "300")))
FRESH = timedelta(days=2)


def looking(user: object, key: str, clock: float | None = None, every: float | None = None) -> bool:
    clock = monotonic() if clock is None else clock
    every = LOOK_EVERY if every is None else every
    if clock - LOOKED.get((user, key), -every) < every:
        return False
    LOOKED[(user, key)] = clock
    return True


async def notifications(connection: AsyncConnection) -> list[dict[str, Any]]:
    profile = await insights.profile(connection)
    since = datetime.now(UTC) - FRESH
    out = await _pill_notices(connection, profile.name)
    for one in await insights.recent(connection, limit=20, since=since):
        if one.read_at is not None:
            continue
        title = "Tu semana" if one.kind == "weekly" else one.title
        out.append(
            notify.notification(
                "insight",
                f"insight:{one.id}",
                f"{profile.name}: {title}",
                f"/insights/consejo/{one.id}",
                one.created_at,
                one.title if one.kind == "weekly" else one.action,
            )
        )
    return out


async def _pill_notices(connection: AsyncConnection, name: str) -> list[dict[str, Any]]:
    now = datetime.now(craft.MADRID)
    settings = await tastes.settings(connection)
    out = []
    pill = await pills.daily(connection, now.date())
    hours, minutes = (int(part) for part in settings.pill_time.split(":"))
    if pill is not None and pill.read_at is None and now.time() >= time(hours, minutes):
        out.append(
            notify.notification(
                "pill",
                f"pill:{pill.id}",
                f"{name}: {pill.headline}",
                f"/insights/pildora/{pill.id}",
                pill.created_at,
                pill.lead,
            )
        )
    question = await tastes.current_question(connection)
    if question is not None and question.id and question.asked_at:
        out.append(
            notify.notification(
                "question",
                f"question:{question.id}",
                f"{name} te pregunta",
                "/insights/",
                question.asked_at,
                question.text,
            )
        )
    fresh = [
        one
        for one in await picks.listed(connection, states=["new"], limit=10)
        if one.origin == "weekly" and one.created_at > datetime.now(UTC) - timedelta(days=3)
    ]
    if fresh:
        out.append(
            notify.notification(
                "picks",
                f"picks:{fresh[-1].id}",
                f"{name}: para ti esta semana",
                "/insights/biblioteca",
                fresh[-1].created_at,
                " · ".join(one.title for one in fresh[:4]),
            )
        )
    return out


async def _crafts(user: object, now: datetime, counts: dict[str, int]) -> None:
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{ROLE}"'))
        settings = await tastes.settings(connection)
        done = await craft.profiled(connection)
    for kind, key in craft.due(now, settings, done):
        if not looking(user, key, every=PILL_EVERY if kind == "pill" else None):
            continue
        async with engine().begin() as connection:
            await connection.execute(text(f'set local role "{ROLE}"'))
            outcome = await craft.run(connection, kind, key, now)
        if outcome:
            counts[outcome] = counts.get(outcome, 0) + 1
            print(f"worker · {key} · {outcome} ({user})", flush=True)


@contextlib.asynccontextmanager
async def _as_module() -> Any:
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{ROLE}"'))
        yield connection


async def _voices(user: object, counts: dict[str, int]) -> None:
    done = await voice.generate(_as_module)
    if done:
        counts["voiced"] = counts.get("voiced", 0) + done
        print(f"worker · voz · {done} ({user})", flush=True)


async def run_once(client: httpx.AsyncClient, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    counts = {"queued": 0, "quiet": 0, "refused": 0}
    for user in await users(client):
        with as_user(user):
            for kind, key in passes.due(now):
                if not looking(user, key):
                    continue
                async with engine().begin() as connection:
                    await connection.execute(text(f'set local role "{ROLE}"'))
                    outcome = await passes.run(connection, kind, key, now)
                if outcome:
                    counts[outcome] += 1
                    print(f"worker · {key} · {outcome} ({user})", flush=True)
            await _crafts(user, now, counts)
            await _voices(user, counts)
        await notify.refresh(client, engine, MODULE, notifications, NOTIFY, user)
    return counts


async def loop() -> None:
    async with httpx.AsyncClient() as client:
        while True:
            HEARTBEAT.touch()  # noqa: ASYNC240
            try:
                await run_once(client)
            except Exception as error:  # noqa: BLE001 - un fallo de base no tumba el proceso
                print(f"worker · {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            await asyncio.sleep(INTERVAL_SECONDS)


def main() -> int:
    print(f"worker · insights → {kernel_url()} cada {INTERVAL_SECONDS:g} s", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(loop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
