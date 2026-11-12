from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_tenancy import USER_HEADER, as_user
from kernel.db import engine
from kernel.main import app
from kernel.subject import SUBJECT_HEADER

SOURCE = "users-test"
SUB = "5d2c9a10-7e3b-4f61-9c8d-2b1a0e9f7c64"
OTRO_SUB = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"


async def clean() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.users where subject in (:a, :b)"), {"a": SUB, "b": OTRO_SUB}
        )
        await connection.execute(
            text(
                "delete from kernel.resolution_queue where event_id in "
                "(select id from kernel.events where source = :s)"
            ),
            {"s": SOURCE},
        )
        await connection.execute(text("delete from kernel.events where source = :s"), {"s": SOURCE})
        await connection.execute(
            text(
                "with gone as (delete from kernel.entity_aliases "
                "where alias like 'USERS-TEST %' or alias = 'MERCADONA 1234' returning entity_id) "
                "delete from kernel.entities where id in (select entity_id from gone)"
            )
        )
        await connection.execute(
            text("delete from kernel.ui_preferences where subject in (:a, :b)"),
            {"a": SUB, "b": OTRO_SUB},
        )


@pytest.fixture
async def kernel(database_url: str):
    await clean()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await clean()
    await engine().dispose()


async def user_for(kernel: AsyncClient, subject: str) -> UUID:
    response = await kernel.post("/internal/users", json={"subject": subject})
    assert response.status_code == 200
    return UUID(response.json()["id"])


def event(dedup: str, **extra) -> dict:
    return {
        "ts": "2026-09-17T10:00:00+00:00",
        "module": "finance",
        "source": SOURCE,
        "type": "finance.transaction",
        "payload": {"amount": -3},
        "dedup_hash": dedup,
        **extra,
    }


async def test_a_sub_always_resolves_to_the_same_person(kernel) -> None:
    first = await user_for(kernel, SUB)
    again = await user_for(kernel, SUB)
    other = await user_for(kernel, OTRO_SUB)

    assert first == again
    assert other != first
    listed = {UUID(row["id"]) for row in (await kernel.get("/internal/users")).json()}
    assert {first, other} <= listed


async def test_what_a_person_writes_is_theirs_without_saying_so(kernel) -> None:
    me = await user_for(kernel, SUB)

    await kernel.put(
        "/ui/preferences",
        json={"glass_opacity": 0.4},
        headers={SUBJECT_HEADER: SUB, USER_HEADER: str(me)},
    )

    async with engine().connect() as connection:
        owner = await connection.scalar(
            text("select user_id from kernel.ui_preferences where subject = :s"), {"s": SUB}
        )
    assert owner == me


async def test_an_event_and_what_the_kernel_derives_from_it_belong_to_the_same_person(
    kernel,
) -> None:
    me = await user_for(kernel, SUB)

    response = await kernel.post(
        "/events",
        json=event("users:1", entity={"alias": f"USERS-TEST {uuid4()}", "kind": "merchant"}),
        headers={USER_HEADER: str(me)},
    )

    assert response.status_code == 200
    async with engine().connect() as connection:
        row = (
            await connection.execute(
                text(
                    "select e.user_id as event_owner, n.user_id as entity_owner, "
                    "a.user_id as alias_owner "
                    "from kernel.events e "
                    "join kernel.entities n on n.id = e.entity_id "
                    "join kernel.entity_aliases a on a.entity_id = n.id "
                    "where e.dedup_hash = 'users:1'"
                )
            )
        ).one()
    assert (row.event_owner, row.entity_owner, row.alias_owner) == (me, me, me)


async def test_the_person_does_not_stay_on_the_pooled_connection(kernel) -> None:
    me = await user_for(kernel, SUB)
    other = await user_for(kernel, OTRO_SUB)
    await kernel.post("/events", json=event("users:2"), headers={USER_HEADER: str(me)})

    await kernel.post("/events", json=event("users:3"), headers={USER_HEADER: str(other)})
    with as_user(None):
        async with engine().connect() as connection:
            leftover = await connection.scalar(text("select current_setting('arga.user_id', true)"))
            owners = dict(
                (
                    await connection.execute(
                        text("select dedup_hash, user_id from kernel.events where source = :s"),
                        {"s": SOURCE},
                    )
                ).all()
            )
    assert owners == {"users:2": me, "users:3": other}
    assert leftover in (None, "")


async def test_without_a_person_nothing_of_anyone_is_written(kernel) -> None:
    with as_user(None):
        response = await kernel.post("/events", json=event("users:4"))

    assert response.status_code == 422
    assert USER_HEADER in response.json()["detail"]


async def test_two_people_can_send_the_same_event(kernel) -> None:
    me = await user_for(kernel, SUB)
    other = await user_for(kernel, OTRO_SUB)

    mine = await kernel.post("/events", json=event("users:6"), headers={USER_HEADER: str(me)})
    theirs = await kernel.post("/events", json=event("users:6"), headers={USER_HEADER: str(other)})
    again = await kernel.post("/events", json=event("users:6"), headers={USER_HEADER: str(me)})

    assert (mine.json()["created"], theirs.json()["created"], again.json()["created"]) == (
        True,
        True,
        False,
    )


async def test_a_header_that_is_not_a_person_is_refused_before_touching_anything(kernel) -> None:
    response = await kernel.post("/events", json=event("users:5"), headers={USER_HEADER: "yo"})

    assert response.status_code == 400
    async with engine().connect() as connection:
        assert (
            await connection.scalar(
                text("select count(*) from kernel.events where dedup_hash = 'users:5'")
            )
            == 0
        )


async def test_a_background_pass_writes_in_the_name_of_whoever_it_is_attending(
    database_url,
) -> None:
    someone = uuid4()
    with as_user(someone):
        async with engine().begin() as connection:
            seen = await connection.scalar(text("select current_setting('arga.user_id', true)"))
    with as_user(None):
        async with engine().begin() as connection:
            after = await connection.scalar(text("select current_setting('arga.user_id', true)"))
    await engine().dispose()

    assert seen == str(someone)
    assert after in (None, "")
