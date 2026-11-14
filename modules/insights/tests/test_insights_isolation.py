from __future__ import annotations

import json
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_insights"
READ = "mod_insights_read"
KERNEL_LIKE = "kernel_como_en_produccion"


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person, ()):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


INSERT = (
    "insert into insights.insights_insight (kind, domain, topic, title, body, figures, affects, action) "
    "values ('alert', 'body', 'vitals.weight', :title, 'text', "
    '\'[{"label": "weight", "value": 80, "baseline": 78, "baseline_label": "your average"}]\', '
    "'the weight goal', 'Walk 30 more minutes every day this week')"
)
PROFILE = "insert into insights.insights_profile (name, about) values (:name, :about)"


@pytest.fixture
async def two_people(schema):
    await as_role(schema, WRITE, ANA, INSERT, title="El de Ana")
    await as_role(schema, WRITE, LUIS, INSERT, title="El de Luis")
    await as_role(schema, WRITE, ANA, PROFILE, name="Txuri", about="What Ana tells about herself")
    await as_role(schema, WRITE, LUIS, PROFILE, name=None, about="What Luis tells about himself")
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_people, role: str) -> None:
    ana = await as_role(two_people, role, ANA, "select title from insights.insights_insight")
    luis = await as_role(two_people, role, LUIS, "select about from insights.insights_profile")

    assert [row.title for row in ana] == ["El de Ana"]
    assert [row.about for row in luis] == ["What Luis tells about himself"]


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_people, role: str) -> None:
    assert await as_role(two_people, role, None, "select 1 from insights.insights_insight") == []
    assert await as_role(two_people, role, None, "select 1 from insights.insights_profile") == []


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into insights.insights_profile (user_id, about) values (:other, 'x')",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_rating_someone_elses_insight_touches_nothing(two_people) -> None:
    changed = await as_role(
        two_people,
        WRITE,
        ANA,
        "update insights.insights_insight set rating = 'useful' where title = 'El de Luis'",
    )

    assert changed == 0


async def test_the_reader_role_cannot_write(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(two_people, READ, ANA, INSERT, title="Otro")

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('insights', 'app', 'insights.insight', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()


async def test_a_conversation_is_only_seen_by_whoever_had_it(two_people) -> None:
    await as_role(
        two_people, WRITE, ANA, "insert into insights.insights_thread (title) values ('De Ana')"
    )

    ana = await as_role(two_people, READ, ANA, "select title from insights.insights_thread")
    luis = await as_role(two_people, READ, LUIS, "select title from insights.insights_thread")

    assert [row.title for row in ana] == ["De Ana"]
    assert luis == []


async def test_a_pass_is_only_seen_by_whoever_it_was_for(two_people) -> None:
    await as_role(
        two_people,
        WRITE,
        ANA,
        "insert into insights.insights_run (kind, key, outcome) values ('morning', 'morning:2026-10-13', "
        "'quiet')",
    )

    ana = await as_role(two_people, READ, ANA, "select key from insights.insights_run")
    luis = await as_role(two_people, READ, LUIS, "select key from insights.insights_run")

    assert [row.key for row in ana] == ["morning:2026-10-13"]
    assert luis == []


async def test_someone_elses_figures_never_reach_the_signals(two_people) -> None:
    probe = "probe_isolation"
    async with two_people.begin() as connection:
        await connection.execute(
            text(
                "do $$ begin if not exists "
                f"(select 1 from pg_roles where rolname = '{KERNEL_LIKE}') "
                f"then create role {KERNEL_LIKE} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {KERNEL_LIKE}"))
        await connection.execute(
            text(f"grant select on kernel.events, kernel.modules to {KERNEL_LIKE}")
        )
        await connection.execute(text(f"alter view insights.events owner to {KERNEL_LIKE}"))
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:m, '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {
                "m": probe,
                "manifest": json.dumps(
                    {"id": probe, "publishes": [{"type": f"{probe}.metric", "contract": "metric"}]}
                ),
            },
        )
        for person, value in ((ANA, 70), (LUIS, 90)):
            await connection.execute(
                text(
                    "insert into kernel.events (module, source, type, payload, dedup_hash, "
                    "user_id, ts) values (:m, 'app', :type, cast(:payload as jsonb), :dedup, "
                    ":user, now())"
                ),
                {
                    "m": probe,
                    "type": f"{probe}.metric",
                    "payload": json.dumps(
                        {
                            "metric": {
                                "key": f"{probe}.weight",
                                "label": "Peso",
                                "unit": "kg",
                                "kind": "level",
                                "day": "2026-10-13",
                                "value": value,
                            }
                        }
                    ),
                    "dedup": f"iso:{person}",
                    "user": person,
                },
            )
    try:
        seen = await as_role(
            two_people,
            READ,
            ANA,
            "select payload->'metric'->>'value' as value from insights.events where payload ? 'metric'",
        )
    finally:
        async with two_people.begin() as connection:
            await connection.execute(
                text("delete from kernel.events where module = :m"), {"m": probe}
            )
            await connection.execute(text("delete from kernel.modules where id = :m"), {"m": probe})

    assert [row.value for row in seen] == ["70"]


TASTE_ROWS = {
    "insights_trait": (
        "insert into insights.insights_trait (facet, key, label, source, status) "
        "values ('topic', lower(:tag), :tag, 'said', 'confirmed')",
        "select label as tag from insights.insights_trait",
    ),
    "insights_pill": (
        "insert into insights.insights_pill (day, origin, family_key, topic, minutes, headline, lead, "
        "sections, to_tell, sources) values ('2026-11-10', 'daily', 'history', :tag, 15, "
        "'A test headline', 'A test lead that is long enough', "
        '\'[{"title": "a", "text": "b"}, {"title": "c", "text": "d"}]\', '
        '\'A test fact to tell someone\', \'[{"title": "x", "url": "https://x.org"}]\')',
        "select topic as tag from insights.insights_pill",
    ),
    "insights_fact": (
        "insert into insights.insights_fact (day, family_key, text, source) values ('2026-11-10', "
        "'science', :tag || ' is a test fact long enough', '{}'::jsonb)",
        "select split_part(text, ' ', 1) as tag from insights.insights_fact",
    ),
    "insights_pick": (
        "insert into insights.insights_pick (kind, key, title, why, origin, verified) "
        "values ('book', :tag, :tag, 'A test why', 'weekly', 'catalog')",
        "select title as tag from insights.insights_pick",
    ),
    "insights_question": (
        "insert into insights.insights_question (origin, kind, text) values ('pass', 'free', :tag)",
        "select text as tag from insights.insights_question",
    ),
    "insights_family": (
        "insert into insights.insights_family (key, name, hue, glyph, themes) "
        "values (lower(:tag), :tag, 1, 'globe', '')",
        "select name as tag from insights.insights_family",
    ),
}


@pytest.mark.parametrize("table", sorted(TASTE_ROWS))
@pytest.mark.parametrize("role", [WRITE, READ])
async def test_what_insights_knows_of_each_one_is_only_theirs(
    two_people, table: str, role: str
) -> None:
    insert, select = TASTE_ROWS[table]
    await as_role(two_people, WRITE, ANA, insert, tag="Anaa")
    await as_role(two_people, WRITE, LUIS, insert, tag="Luis")

    ana = await as_role(two_people, role, ANA, select)
    nobody = await as_role(two_people, role, None, select)

    assert [row.tag for row in ana] == ["Anaa"]
    assert nobody == []
