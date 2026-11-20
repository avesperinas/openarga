from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from hub import catalogue, demo, instruments

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")


async def seed_everyone(schema) -> dict[str, list[str]]:
    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        spaces = current_spaces.set((CAST.space_id,))
        try:
            for _ in range(2):
                async with schema.begin() as connection:
                    await connection.execute(text('set local role "mod_hub"'))
                    await demo.seed(connection, persona, date.today())
            async with schema.begin() as connection:
                await connection.execute(text('set local role "mod_hub"'))
                seen[persona.key] = sorted(
                    (
                        await connection.execute(text("select provider from hub.hub_connection"))
                    ).scalars()
                )
        finally:
            current_spaces.reset(spaces)
            current_user.reset(token)
    return seen


async def test_alex_and_sam_get_their_connections_once_each(schema) -> None:
    seen = await seed_everyone(schema)

    assert seen == {
        "alex": ["apple_podcasts", "football", "holidays", "ical", "prices"],
        "sam": ["formula1", "holidays", "ical", "ical"],
    }


def test_every_demo_connection_is_a_valid_one() -> None:
    for persona in CAST.people:
        for provider, _, config in demo.connections(persona, date.today()):
            known = catalogue.provider(provider)
            if known.clean is not None:
                known.clean(config)
            if provider == "prices":
                assert instruments.stored(config)


async def test_each_person_reads_the_connections_in_their_own_language(schema) -> None:
    found = {}
    await seed_everyone(schema)
    for persona in CAST.people:
        token = current_user.set(persona.id)
        try:
            async with schema.begin() as connection:
                await connection.execute(text('set local role "mod_hub"'))
                found[persona.key] = set(
                    await connection.scalars(text("select label from hub.hub_connection"))
                )
        finally:
            current_user.reset(token)

    assert {"Football"} <= found["alex"]
    assert {demo.say(CAST.people[1], "Formula 1")} <= found["sam"]
    assert not {"Formula 1"} & found["sam"]
