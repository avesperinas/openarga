import asyncio
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.db import engine
from kernel.main import app

TAGS = ("kcopyen1", "kcopyen2", "kcopyes1")


async def clean() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.demo_copies where tag = any(:tags)"), {"tags": list(TAGS)}
        )
        await connection.execute(text("delete from kernel.users where subject like 'demo-kcopy%'"))


@pytest.fixture
async def kernel(database_url: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENARGA_DEMO", "true")
    monkeypatch.setenv("OPENARGA_DEMO_COPIES", "true")
    await clean()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await clean()
    await engine().dispose()


async def ready(tag: str, locale: str, minutes_ago: int = 0) -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.demo_copies (tag, locale, created_at) "
                "values (:tag, :locale, now() - make_interval(mins => :ago))"
            ),
            {"tag": tag, "locale": locale, "ago": minutes_ago},
        )
        for key in ("alex", "sam"):
            await connection.execute(
                text(
                    "insert into kernel.users (subject, last_seen_at) "
                    "values (:subject, now() - interval '3 hours')"
                ),
                {"subject": f"demo-{tag}-{key}"},
            )


async def test_a_claim_hands_out_that_language_first_and_then_any_ready_copy(kernel) -> None:
    await ready("kcopyen1", "en", minutes_ago=10)
    await ready("kcopyen2", "en", minutes_ago=5)
    await ready("kcopyes1", "es", minutes_ago=20)

    first = await kernel.post("/internal/demo/claim", json={"locale": "en"})
    second = await kernel.post("/internal/demo/claim", json={"locale": "en"})
    third = await kernel.post("/internal/demo/claim", json={"locale": "en"})

    assert first.status_code == 200 and first.json()["tag"] == "kcopyen1"
    assert second.status_code == 200 and second.json()["tag"] == "kcopyen2"
    assert third.status_code == 200 and third.json()["locale"] == "es"
    async with engine().connect() as connection:
        rows = dict(
            (
                await connection.execute(
                    text("select tag, status from kernel.demo_copies where tag = any(:t)"),
                    {"t": list(TAGS)},
                )
            ).all()
        )
        woken = await connection.scalar(
            text(
                "select bool_and(last_seen_at > now() - interval '1 minute') from kernel.users "
                "where subject like 'demo-kcopyen1-%'"
            )
        )
    assert rows == {"kcopyen1": "claimed", "kcopyen2": "claimed", "kcopyes1": "claimed"}
    assert (await kernel.post("/internal/demo/claim", json={"locale": "en"})).status_code == 409
    assert woken


async def test_two_visitors_at_once_never_get_the_same_copy(kernel) -> None:
    await ready("kcopyen1", "en")

    answers = await asyncio.gather(
        *(kernel.post("/internal/demo/claim", json={"locale": "en"}) for _ in range(5))
    )

    assert sorted(answer.status_code for answer in answers) == [200, 409, 409, 409, 409]


async def test_a_claim_lasts_the_copy_s_lifetime(kernel, monkeypatch) -> None:
    from datetime import datetime, timedelta

    monkeypatch.setenv("OPENARGA_DEMO_COPY_MINUTES", "90")
    await ready("kcopyes1", "es")

    answer = (await kernel.post("/internal/demo/claim", json={"locale": "es"})).json()
    until = datetime.fromisoformat(answer["until"])

    assert timedelta(minutes=89) < until - datetime.now(until.tzinfo) <= timedelta(minutes=90)


async def test_without_copies_there_is_nothing_to_claim(kernel, monkeypatch) -> None:
    monkeypatch.setenv("OPENARGA_DEMO_COPIES", "false")
    await ready("kcopyen1", "en")

    answer = await kernel.post("/internal/demo/claim", json={"locale": "en"})

    assert answer.status_code == 404


async def test_a_copy_s_person_is_found_but_never_made(kernel) -> None:
    await ready("kcopyen1", "en")

    found = await kernel.post("/internal/users", json={"subject": "demo-kcopyen1-alex"})
    gone = await kernel.post("/internal/users", json={"subject": "demo-kcopyen2-alex"})

    assert found.status_code == 200 and UUID(found.json()["id"])
    assert gone.status_code == 404
    async with engine().connect() as connection:
        made = await connection.scalar(
            text("select count(*) from kernel.users where subject = 'demo-kcopyen2-alex'")
        )
    assert made == 0


async def test_without_copies_any_subject_is_made_as_before(kernel, monkeypatch) -> None:
    monkeypatch.setenv("OPENARGA_DEMO_COPIES", "false")

    made = await kernel.post("/internal/users", json={"subject": "demo-kcopyen2-alex"})

    assert made.status_code == 200


async def test_with_copies_the_workers_only_see_people_in_use(kernel, monkeypatch) -> None:
    await ready("kcopyen1", "en")
    await ready("kcopyen2", "en")
    await kernel.post("/internal/demo/claim", json={"locale": "en"})

    listed = {row["id"] for row in (await kernel.get("/internal/users")).json()}
    monkeypatch.setenv("OPENARGA_DEMO_COPIES", "false")
    everyone = {row["id"] for row in (await kernel.get("/internal/users")).json()}

    async with engine().connect() as connection:
        ids = {
            row.subject: str(row.id)
            for row in await connection.execute(
                text("select id, subject from kernel.users where subject like 'demo-kcopy%'")
            )
        }
    assert {ids["demo-kcopyen1-alex"], ids["demo-kcopyen1-sam"]} <= listed
    assert ids["demo-kcopyen2-alex"] not in listed
    assert set(ids.values()) <= everyone
