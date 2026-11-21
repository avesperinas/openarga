from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import string
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
OWNED = text("""
    select format('%I.%I', n.nspname, c.relname) as name,
           exists (select 1 from pg_attribute a
                   where a.attrelid = c.oid and a.attname = 'space_id' and not a.attisdropped)
               as shared
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'p') and not c.relispartition
      and obj_description(c.oid, 'pg_class') in ('arga:person', 'arga:shared')
      and exists (select 1 from pg_attribute a
                  where a.attrelid = c.oid and a.attname = 'user_id' and not a.attisdropped)
""")

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


async def fill(
    engine: AsyncEngine, cast: demo.Cast, seeds: dict[str, Seed], today: date, report: Report
) -> None:
    await cast_in_kernel(engine, cast)
    await run_seeds(engine, cast, seeds, today, report)
    async with engine.begin() as connection:
        for person in cast.people:
            await health_feed.feed(connection, person, today)


async def run(command: str, today: date, url: str, root: Path = ROOT) -> Report:
    cast = demo.load(root / "demo" / "personas.yaml")
    seeds = demo.seeds(root / "modules")
    engine = install(create_async_engine(url))
    report = Report()
    try:
        if command == "reset":
            await forget(engine, cast, list(seeds))
        chosen = daily(root / "modules") if command == "day" else seeds
        await fill(engine, cast, chosen, today, report)
    finally:
        await engine.dispose()
    return report


async def make_copy(
    engine: AsyncEngine, tag: str, locale: str | None, today: date, root: Path = ROOT
) -> tuple[demo.Cast, Report]:
    cast = demo.copy_of(demo.load(root / "demo" / "personas.yaml"), tag, locale)
    report = Report()
    await fill(engine, cast, demo.seeds(root / "modules"), today, report)
    return cast, report


async def drop_copy(engine: AsyncEngine, cast: demo.Cast) -> None:
    if cast.copy is None:
        raise ValueError("only a copy of the cast is dropped, never the cast itself")
    values = {"people": [person.id for person in cast.people], "space": cast.space_id}
    async with engine.begin() as connection:
        owned = {row.name: row.shared for row in await connection.execute(OWNED)}
        # Every row of the copy goes, so no key is left dangling. Row triggers stay quiet while it
        # happens, as they do for the reset's truncate: some apps refuse to delete history row by
        # row (a published plan version), and a vanishing copy should not publish its deletions.
        await connection.execute(text("set local session_replication_role = replica"))
        for name in sorted(owned):
            mine = "user_id = any(:people)" + (" or space_id = :space" if owned[name] else "")
            await connection.execute(text(f"delete from {name} where {mine}"), values)
        await connection.execute(text("set local session_replication_role = origin"))
        await connection.execute(text("delete from kernel.users where id = any(:people)"), values)
        await connection.execute(text("delete from kernel.spaces where id = :space"), values)


@dataclass
class Keeping:
    dropped: list[str] = field(default_factory=list)
    made: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    in_use: int = 0
    ready: dict[str, int] = field(default_factory=dict)


LOCALES = ("en", "es")
GONE = text("""
    select c.tag from kernel.demo_copies c
    where (c.status = 'claimed' and (
              c.claimed_at < now() - cast(:lifetime as interval)
              or coalesce((select max(u.last_seen_at) from kernel.users u
                           where u.subject like 'demo-' || c.tag || '-%'), c.claimed_at)
                 < now() - cast(:idle as interval)))
       or (c.status = 'ready' and c.created_at < now() - cast(:shelf as interval))
""")
ORPHANS = text("""
    select distinct substring(u.subject from '^demo-([a-z0-9]{6,16})-[a-z]+$') as tag
    from kernel.users u
    where u.subject ~ '^demo-[a-z0-9]{6,16}-[a-z]+$'
      and not exists (select 1 from kernel.demo_copies c
                      where c.tag = substring(u.subject from '^demo-([a-z0-9]{6,16})-[a-z]+$'))
""")
COUNTS = text("""
    select locale, status, count(*) as n from kernel.demo_copies group by locale, status
""")
READY = text("insert into kernel.demo_copies (tag, locale) values (:tag, :locale)")
FORGOTTEN = text("delete from kernel.demo_copies where tag = :tag")


def _setting(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else default


def new_tag() -> str:
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))


async def keep(engine: AsyncEngine, today: date, root: Path = ROOT) -> Keeping:
    base = demo.load(root / "demo" / "personas.yaml")
    pool = _setting("OPENARGA_DEMO_POOL", 2)
    cap = _setting("OPENARGA_DEMO_COPIES_MAX", 20)
    windows = {
        "lifetime": timedelta(minutes=_setting("OPENARGA_DEMO_COPY_MINUTES", 120)),
        "idle": timedelta(minutes=_setting("OPENARGA_DEMO_IDLE_MINUTES", 30)),
        "shelf": timedelta(minutes=_setting("OPENARGA_DEMO_SHELF_MINUTES", 360)),
    }
    kept = Keeping()
    async with engine.connect() as connection:
        gone = [row.tag for row in await connection.execute(GONE, windows)]
        gone += [row.tag for row in await connection.execute(ORPHANS)]
    for tag in gone:
        await drop_copy(engine, demo.copy_of(base, tag))
        async with engine.begin() as connection:
            await connection.execute(FORGOTTEN, {"tag": tag})
        kept.dropped.append(tag)
    async with engine.connect() as connection:
        rows = (await connection.execute(COUNTS)).all()
    kept.ready = {locale: 0 for locale in LOCALES}
    for row in rows:
        if row.status == "ready":
            kept.ready[row.locale] = row.n
        else:
            kept.in_use += row.n
    total = kept.in_use + sum(kept.ready.values())
    while total < cap:
        short = [locale for locale in LOCALES if kept.ready[locale] < pool]
        if not short:
            break
        locale = min(short, key=lambda one: kept.ready[one])
        tag = new_tag()
        cast, report = await make_copy(engine, tag, locale, today, root)
        if report.failed:
            await drop_copy(engine, cast)
            kept.failed.update({f"{tag}/{module}": why for module, why in report.failed.items()})
            break
        async with engine.begin() as connection:
            await connection.execute(READY, {"tag": tag, "locale": locale})
        kept.made.append(f"{tag}/{locale}")
        kept.ready[locale] += 1
        total += 1
    return kept


def copies_on() -> bool:
    return demo_instance() and os.environ.get("OPENARGA_DEMO_COPIES", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def cast_today(cast: demo.Cast, now: datetime | None = None) -> date:
    zone = ZoneInfo(cast.people[0].timezone)
    return (now or datetime.now(zone)).astimezone(zone).date()


def demo_instance() -> bool:
    return os.environ.get("OPENARGA_DEMO", "").strip().lower() in ("1", "true", "yes")


def keep_main(today: date) -> int:
    async def once() -> Keeping:
        engine = install(create_async_engine(database_url()))
        try:
            return await keep(engine, today)
        finally:
            await engine.dispose()

    kept = asyncio.run(once())
    if kept.dropped or kept.made or kept.failed:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        ready = ", ".join(f"{locale} {n}" for locale, n in kept.ready.items())
        print(
            f"{stamp} keep: dropped {len(kept.dropped)}, made {len(kept.made)}, "
            f"in use {kept.in_use}, ready {ready}"
        )
    for what, problem in kept.failed.items():
        print(f"failed {what}: {problem}", file=sys.stderr)
    return 1 if kept.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill OpenArga with the demo people.")
    parser.add_argument(
        "command",
        nargs="?",
        default="seed",
        choices=("seed", "day", "reset", "keep", "list"),
        help="seed: create the cast and run every app's seed (the default); day: one more day "
        "of simulated life; reset: wipe the demo apps and seed again (demo instances only); "
        "keep: drop the demo copies nobody uses and make ready ones (with "
        "OPENARGA_DEMO_COPIES=true); list: only say who and which apps",
    )
    parser.add_argument("--today", type=date.fromisoformat, default=None)
    arguments = parser.parse_args()
    cast = demo.load(ROOT / "demo" / "personas.yaml")
    today = arguments.today or cast_today(cast)
    if arguments.command == "keep":
        if not copies_on():
            print(
                "keep looks after demo copies: it runs with OPENARGA_DEMO=true and "
                "OPENARGA_DEMO_COPIES=true",
                file=sys.stderr,
            )
            return 1
        return keep_main(today)
    seeds = demo.seeds(ROOT / "modules")
    print(f"people: {', '.join(person.name for person in cast.people)}")
    print(f"apps with demo data: {', '.join(seeds) or 'none yet'}")
    if arguments.command == "list":
        return 0
    if arguments.command == "reset" and not demo_instance():
        print("reset wipes the apps' data: it only runs with OPENARGA_DEMO=true", file=sys.stderr)
        return 1
    if arguments.command == "reset" and copies_on():
        print(
            "reset would wipe every visitor's copy: with OPENARGA_DEMO_COPIES=true, "
            "keep looks after them instead",
            file=sys.stderr,
        )
        return 1
    report = asyncio.run(run(arguments.command, today, database_url()))
    print(f"seeded on {today}: {', '.join(report.seeded) or 'nothing'}")
    for module_id, problem in report.failed.items():
        print(f"failed {module_id}: {problem}", file=sys.stderr)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
