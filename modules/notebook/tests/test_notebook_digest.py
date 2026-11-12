from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from itertools import count

import pytest
from sqlalchemy import text

import arga_contracts as contracts
from arga_tenancy import current_user
from notebook import digest, mirror
from notebook import markdown as md

APP = "medidor"
NAMES = {APP: "Medidor"}
READ = {"x-arga-scopes": "notebook:read"}
MONDAY = datetime(2026, 10, 12, 5, 0, tzinfo=UTC)
_clock = count()


async def names() -> dict[str, str]:
    return NAMES


@pytest.fixture
async def meter(schema):
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": APP})
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, manifest) values (:id, '0.1.0', "
                "cast(:manifest as jsonb)) on conflict (id) do update set manifest = "
                "excluded.manifest"
            ),
            {
                "id": APP,
                "manifest": json.dumps(
                    {
                        "id": APP,
                        "name": NAMES[APP],
                        "publishes": [
                            {"type": f"{APP}.metric", "contract": "metric"},
                            {"type": f"{APP}.record", "contract": "record"},
                        ],
                    }
                ),
            },
        )
    yield schema
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": APP})
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": APP})


async def emit(schema, kind: str, payload: dict, at: datetime) -> None:
    at = at + timedelta(seconds=next(_clock))
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, ingested_at, module, source, type, payload, "
                "user_id, dedup_hash) values (:ts, :ts, :app, 'app', :type, "
                "cast(:payload as jsonb), :person, :dedup)"
            ),
            {
                "ts": at,
                "app": APP,
                "type": f"{APP}.{kind}",
                "payload": json.dumps(payload),
                "person": current_user.get(),
                "dedup": f"{kind}:{at.isoformat()}:{json.dumps(payload)}",
            },
        )


async def steps(schema, day: date, value: float) -> None:
    point = {
        "key": f"{APP}.steps",
        "label": "Pasos",
        "unit": "steps",
        "kind": "amount",
        "day": day.isoformat(),
        "value": value,
    }
    await emit(schema, "metric", {"metric": point}, datetime(2026, 10, 12, tzinfo=UTC))


async def record(schema, item: dict, at: datetime) -> None:
    await emit(schema, "record", {"record": contracts.record(**item)}, at)


async def two_weeks(schema) -> None:
    for i in range(14):
        day = date(2026, 9, 28) + timedelta(days=i)
        await steps(schema, day, 8000 if day < date(2026, 10, 5) else 9000)
    await record(
        schema,
        {
            "id": "book:1",
            "title": "Un libro inventado",
            "kind": "Libro",
            "href": "/medidor/libro/1",
            "folder": "Libros",
            "properties": {},
            "body": "Terminado.",
        },
        datetime(2026, 10, 8, 18, tzinfo=UTC),
    )
    await record(
        schema,
        {
            "id": "goal:1",
            "title": "Andar más",
            "kind": "Meta",
            "href": "/medidor/meta/1",
            "folder": "Metas",
            "properties": {
                "estado": "activa",
                "ritmo": "por detrás",
                "actual": 9000,
                "objetivo": 10000,
                "unidad": "pasos",
            },
            "body": "",
        },
        datetime(2026, 10, 9, 18, tzinfo=UTC),
    )
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        await mirror.derive(connection, True, names)


async def refresh(schema, now: datetime = MONDAY) -> dict[str, int]:
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        return await digest.refresh(connection, now, names)


async def note(api, path: str) -> dict:
    found = (await api.get("/notes/resolve", params={"target": path})).json()["note"]
    assert found is not None, f"no está «{path}»"
    return (await api.get(f"/notes/{found['id']}")).json()


def test_periods_and_their_names() -> None:
    assert digest.of("week", date(2026, 10, 8)).title == "2026-W41"
    assert digest.of("month", date(2026, 2, 10)).end == date(2026, 2, 28)
    quarter = digest.of("quarter", date(2026, 11, 3))
    assert (quarter.title, quarter.start, quarter.end) == (
        "2026-T4",
        date(2026, 10, 1),
        date(2026, 12, 31),
    )
    assert digest.parse("2026-w41") == digest.of("week", date(2026, 10, 5))
    assert digest.parse("2026-09").path == "Diario/Meses/2026-09"
    with pytest.raises(ValueError):
        digest.parse("2026-T5")


def test_monday_before_six_still_belongs_to_the_week_before() -> None:
    early = [p.title for p in digest.due(datetime(2026, 10, 12, 3, 0, tzinfo=UTC))]
    later = [p.title for p in digest.due(MONDAY)]

    assert "2026-W41" not in early
    assert later[:2] == ["2026-W40", "2026-W41"]
    assert "2026-09" in later and "2026-T4" in later


async def test_the_week_is_written_with_its_figures_what_happened_and_the_goals(meter, api) -> None:
    await two_weeks(meter)

    await refresh(meter)
    week = await note(api, "Diario/Semanas/2026-W41")
    inner = md.block(week["content"]).inner

    assert "### Medidor" in inner
    assert "| Pasos | 63.000 pasos | 56.000 pasos | +7.000 pasos (+12%) |" in inner
    assert "[[medidor:book:1|Un libro inventado]]" in inner
    assert "- **En riesgo**: [[medidor:goal:1|Andar más]]" in inner
    assert "[[2026-10-05]] · [[2026-10-06]]" in inner


async def test_a_late_figure_rewrites_the_block_and_your_text_stays(meter, api) -> None:
    await two_weeks(meter)
    await refresh(meter)
    week = await note(api, "Diario/Semanas/2026-W41")
    mine = week["content"] + "\nLo que escribo yo de esta semana.\n"
    await api.put(f"/notes/{week['id']}", json={"content": mine, "version": week["version"]})

    await steps(meter, date(2026, 10, 11), 16000)
    again = await refresh(meter, MONDAY + timedelta(hours=1))
    rewritten = await note(api, "Diario/Semanas/2026-W41")

    assert again.get("written", 0) >= 1
    assert "| Pasos | 70.000 pasos |" in md.block(rewritten["content"]).inner
    assert "Lo que escribo yo de esta semana." in rewritten["content"]


def told(week: str, body: str) -> dict:
    return {
        "id": f"semana-{week}",
        "title": f"Semana {week}",
        "kind": "Resumen de la semana",
        "href": "/medidor/semana/1",
        "folder": "Semanas",
        "properties": {"semana": week},
        "body": body,
    }


async def test_the_week_starts_with_what_an_app_tells_of_it(meter, api) -> None:
    await two_weeks(meter)
    body = "**Una semana tranquila**\n\nDormiste más.\n\n## Propuestas\n\n1. Andar."
    await record(meter, told("2026-W41", body), datetime(2026, 10, 12, 6, tzinfo=UTC))
    await record(meter, told("2026-W40", "Otra."), datetime(2026, 10, 4, 18, tzinfo=UTC))
    async with meter.begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        await mirror.derive(connection, True, names)

    await refresh(meter, MONDAY + timedelta(hours=8))
    inner = md.block((await note(api, "Diario/Semanas/2026-W41"))["content"]).inner

    assert inner.startswith("## La semana contada\n\n**Una semana tranquila**\n\nDormiste más.")
    assert "\n### Propuestas\n" in inner
    assert "Lo cuenta [[medidor:semana-2026-W41|Medidor]]." in inner
    assert "Otra." not in inner
    assert "[[medidor:semana-2026-W41|Semana 2026-W41]]" not in inner
    assert inner.index("La semana contada") < inner.index("Cómo fue")
    assert (await note(api, "Medidor/Semanas/Semana 2026-W41"))["properties"]["semana"] == (
        "2026-W41"
    )


async def test_nothing_changed_writes_nothing(meter, api) -> None:
    await two_weeks(meter)
    await refresh(meter)

    again = await refresh(meter, MONDAY + timedelta(minutes=15))

    assert again.get("written", 0) == 0


async def test_the_month_links_its_weeks_and_the_quarter_asks_its_questions(meter, api) -> None:
    await two_weeks(meter)
    await refresh(meter, datetime(2026, 10, 1, 5, 0, tzinfo=UTC))

    month = await note(api, "Diario/Meses/2026-09")
    quarter = await note(api, "Diario/Trimestres/2026-T4")

    assert "[[2026-W40]]" in md.block(month["content"]).inner
    assert "[[2026-W36]]" in md.block(month["content"]).inner
    assert (
        "[[medidor:goal:1|Andar más]]: ahora 9.000 pasos de 10.000 pasos"
        in md.block(quarter["content"]).inner
    )
    outside = md.outside_block(quarter["content"])
    assert "## Andar más" in outside
    assert "- ¿Sigue importando?" in outside and "- ¿Qué cambias?" in outside


async def test_the_quarter_is_written_once(meter, api) -> None:
    await two_weeks(meter)
    first_day = datetime(2026, 10, 1, 5, 0, tzinfo=UTC)
    await refresh(meter, first_day)
    before = await note(api, "Diario/Trimestres/2026-T4")

    await refresh(meter, first_day + timedelta(days=5))

    assert (await note(api, "Diario/Trimestres/2026-T4"))["version"] == before["version"]


async def test_the_tool_says_the_same_as_the_note(meter, api) -> None:
    await two_weeks(meter)
    await refresh(meter)
    week = await note(api, "Diario/Semanas/2026-W41")

    found = (await api.post("/tools/get_digest", json={"period": "2026-W41"}, headers=READ)).json()[
        "content"
    ]

    assert found["note"] == "Diario/Semanas/2026-W41"
    assert found["content"] == md.block(week["content"]).inner


async def test_monday_says_your_week_is_ready(meter, api) -> None:
    await two_weeks(meter)
    await refresh(meter)
    week = await note(api, "Diario/Semanas/2026-W41")

    async with meter.begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        now = await digest.notifications(connection, MONDAY)
        thursday = await digest.notifications(connection, MONDAY + timedelta(days=3))

    [one] = now
    assert (one["kind"], one["key"], one["title"]) == ("week", "week:2026-W41", "Tu semana")
    assert one["href"] == f"/notebook/nota/{week['id']}"
    assert thursday == []
