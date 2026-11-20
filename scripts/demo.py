from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from arga_module import demo, preferences
from arga_tenancy import as_user, install

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))

import health_feed  # noqa: E402

SUBJECT = "demo-{username}"

USER = text("""
    insert into kernel.users (id, subject, last_seen_at) values (:id, :subject, now())
    on conflict (id) do update set subject = excluded.subject
""")
SPACE = text("""
    insert into kernel.spaces (id, name) values (:id, :name)
    on conflict (id) do update set name = excluded.name
""")
MEMBER = text("""
    insert into kernel.space_members (space_id, user_id, role, status, display_name)
    values (:space, :user, :role, 'accepted', :name)
    on conflict (space_id, user_id) do update set status = 'accepted', display_name = :name
""")
PREFERENCES = text("""
    insert into kernel.person_preferences
        (user_id, locale, timezone, currency, country, region, area)
    values (:id, :locale, :timezone, :currency, :country, :region, :area)
    on conflict (user_id) do update set
        locale = excluded.locale, timezone = excluded.timezone, currency = excluded.currency,
        country = excluded.country, region = excluded.region, area = excluded.area,
        updated_at = now()
""")
TABLES = text("""
    select format('%I.%I', schemaname, tablename) from pg_tables
    where schemaname = :schema
      and obj_description(format('%I.%I', schemaname, tablename)::regclass, 'pg_class')
          in ('arga:person', 'arga:shared')
""")
FORGET = (
    "delete from kernel.events where module = any(:modules)",
    "delete from kernel.users where id = any(:people)",
    "delete from kernel.spaces where id = :space",
)

Seed = Callable[[Any, demo.Persona, date], Awaitable[None]]


@dataclass
class Report:
    seeded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is missing: the demo needs the instance's database")
    return url


async def cast_in_kernel(engine: AsyncEngine, cast: demo.Cast) -> None:
    async with engine.begin() as connection:
        await connection.execute(SPACE, {"id": cast.space_id, "name": cast.space_name})
        for index, person in enumerate(cast.people):
            subject = SUBJECT.format(username=person.username)
            await connection.execute(USER, {"id": person.id, "subject": subject})
            role = "owner" if index == 0 else "member"
            await connection.execute(
                MEMBER,
                {"space": cast.space_id, "user": person.id, "role": role, "name": person.name},
            )
    for person in cast.people:
        with as_user(person.id, (cast.space_id,)):
            async with engine.begin() as connection:
                await connection.execute(
                    PREFERENCES,
                    {
                        "id": person.id,
                        "locale": person.locale,
                        "timezone": person.timezone,
                        "currency": person.currency,
                        "country": person.country,
                        "region": person.region,
                        "area": person.area,
                    },
                )


def _preferences_of(person: demo.Persona) -> preferences.Preferences:
    return preferences.Preferences(
        locale=person.locale,
        timezone=person.timezone,
        currency=person.currency,
        country=person.country,
        region=person.region,
        area=person.area,
    )


async def run_seeds(
    engine: AsyncEngine,
    cast: demo.Cast,
    seeds: dict[str, Seed],
    today: date,
    report: Report,
) -> None:
    for module_id, seed in seeds.items():
        try:
            for person in cast.people:
                token = preferences.use(_preferences_of(person))
                try:
                    with as_user(person.id, (cast.space_id,)):
                        async with engine.begin() as connection:
                            await connection.execute(text(f'set local role "mod_{module_id}"'))
                            await seed(connection, person, today)
                finally:
                    preferences.reset(token)
        except Exception as error:  # noqa: BLE001
            report.failed[module_id] = f"{type(error).__name__}: {error}"
        else:
            report.seeded.append(module_id)


def daily(modules: Path) -> dict[str, Seed]:
    found = demo.seeds(modules)
    for module_id in found:
        live = getattr(sys.modules.get(f"{module_id}.demo"), "live", None)
        if live is not None:
            found[module_id] = live
    return found


async def forget(engine: AsyncEngine, cast: demo.Cast, modules: list[str]) -> None:
    async with engine.begin() as connection:
        for module_id in modules:
            tables = (await connection.execute(TABLES, {"schema": module_id})).scalars().all()
            if tables:
                await connection.execute(text(f"truncate {', '.join(tables)}"))
        values = {
            "modules": modules,
            "people": [person.id for person in cast.people],
            "space": cast.space_id,
        }
        for statement in FORGET:
            await connection.execute(text(statement), values)


async def run(command: str, today: date, url: str, root: Path = ROOT) -> Report:
    cast = demo.load(root / "demo" / "personas.yaml")
    seeds = demo.seeds(root / "modules")
    engine = install(create_async_engine(url))
    report = Report()
    try:
        if command == "reset":
            await forget(engine, cast, list(seeds))
        await cast_in_kernel(engine, cast)
        chosen = daily(root / "modules") if command == "day" else seeds
        await run_seeds(engine, cast, chosen, today, report)
        async with engine.begin() as connection:
            for person in cast.people:
                await health_feed.feed(connection, person, today)
    finally:
        await engine.dispose()
    return report


def demo_instance() -> bool:
    return os.environ.get("OPENARGA_DEMO", "").strip().lower() in ("1", "true", "yes")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill OpenArga with the demo people.")
    parser.add_argument(
        "command",
        nargs="?",
        default="seed",
        choices=("seed", "day", "reset", "list"),
        help="seed: create the cast and run every app's seed (the default); day: one more day "
        "of simulated life; reset: wipe the demo apps and seed again (demo instances only); "
        "list: only say who and which apps",
    )
    parser.add_argument("--today", type=date.fromisoformat, default=None)
    arguments = parser.parse_args()
    cast = demo.load(ROOT / "demo" / "personas.yaml")
    seeds = demo.seeds(ROOT / "modules")
    print(f"people: {', '.join(person.name for person in cast.people)}")
    print(f"apps with demo data: {', '.join(seeds) or 'none yet'}")
    if arguments.command == "list":
        return 0
    if arguments.command == "reset" and not demo_instance():
        print("reset wipes the apps' data: it only runs with OPENARGA_DEMO=true", file=sys.stderr)
        return 1
    today = arguments.today or date.today()
    report = asyncio.run(run(arguments.command, today, database_url()))
    print(f"seeded on {today}: {', '.join(report.seeded) or 'nothing'}")
    for module_id, problem in report.failed.items():
        print(f"failed {module_id}: {problem}", file=sys.stderr)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
