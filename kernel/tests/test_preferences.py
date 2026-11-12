import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_tenancy import USER_HEADER, current_user
from kernel.db import engine
from kernel.main import app

SUBJECTS = ("3f8e2a61-5c4b-4d7e-9a10-2b3c4d5e6f70", "7c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f")


async def clean() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.users where subject = any(:s)"), {"s": list(SUBJECTS)}
        )


@pytest.fixture
async def kernel(database_url: str, monkeypatch):
    for name in ("COUNTRY", "REGION", "AREA"):
        monkeypatch.delenv(f"OPENARGA_{name}", raising=False)
    monkeypatch.setenv("OPENARGA_LOCALE", "en")
    monkeypatch.setenv("OPENARGA_TIMEZONE", "UTC")
    monkeypatch.setenv("OPENARGA_CURRENCY", "EUR")
    await clean()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await clean()
    await engine().dispose()


@pytest.fixture
async def people(kernel) -> list[dict[str, str]]:
    found = []
    for subject in SUBJECTS:
        person = (await kernel.post("/internal/users", json={"subject": subject})).json()
        found.append({USER_HEADER: person["id"]})
    return found


async def test_preferences_start_from_the_instance_defaults(monkeypatch) -> None:
    from kernel.main import app

    monkeypatch.setenv("OPENARGA_LOCALE", "es")
    monkeypatch.setenv("OPENARGA_TIMEZONE", "Europe/Madrid")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        found = (await client.get("/me/preferences")).json()

    assert found["locale"] == "es"
    assert found["timezone"] == "Europe/Madrid"
    assert set(found) == {"locale", "timezone", "currency", "country", "region", "area"}


async def test_a_person_keeps_their_own_preferences(kernel, people) -> None:
    alex, sam = people
    changed = await kernel.patch(
        "/me/preferences",
        json={"locale": "es", "timezone": "Europe/Berlin", "country": "DE", "region": "DE-BY"},
        headers=alex,
    )
    assert changed.status_code == 200, changed.text

    mine = (await kernel.get("/me/preferences", headers=alex)).json()
    theirs = (await kernel.get("/me/preferences", headers=sam)).json()
    assert mine == {
        "locale": "es",
        "timezone": "Europe/Berlin",
        "currency": "EUR",
        "country": "DE",
        "region": "DE-BY",
        "area": None,
    }
    assert theirs["locale"] == "en"
    assert theirs["timezone"] == "UTC"


async def test_only_the_fields_sent_change_and_null_returns_to_the_default(kernel, people) -> None:
    alex, _ = people
    await kernel.patch(
        "/me/preferences", json={"currency": "USD", "timezone": "America/Chicago"}, headers=alex
    )
    await kernel.patch("/me/preferences", json={"currency": None}, headers=alex)

    mine = (await kernel.get("/me/preferences", headers=alex)).json()
    assert mine["currency"] == "EUR"
    assert mine["timezone"] == "America/Chicago"


async def test_a_new_country_drops_a_region_from_the_old_one(kernel, people) -> None:
    alex, _ = people
    await kernel.patch("/me/preferences", json={"country": "ES", "region": "ES-NA"}, headers=alex)
    mine = (await kernel.patch("/me/preferences", json={"country": "DE"}, headers=alex)).json()
    assert (mine["country"], mine["region"]) == ("DE", None)


@pytest.mark.parametrize(
    "wrong",
    [
        {"timezone": "Mars/Olympus"},
        {"locale": "fr"},
        {"currency": "eur"},
        {"country": "ESP"},
        {"region": "Navarra"},
        {"country": "ES", "region": "DE-BY"},
        {"area": "Not A Slug"},
    ],
)
async def test_wrong_values_are_refused(kernel, people, wrong) -> None:
    alex, _ = people
    response = await kernel.patch("/me/preferences", json=wrong, headers=alex)
    assert response.status_code == 422


async def test_writing_needs_a_person(kernel) -> None:
    token = current_user.set(None)
    try:
        response = await kernel.patch("/me/preferences", json={"locale": "es"})
    finally:
        current_user.reset(token)
    assert response.status_code == 422


async def test_resolving_a_person_hands_the_gateway_their_preferences(kernel, people) -> None:
    alex, _ = people
    await kernel.patch("/me/preferences", json={"area": "munich"}, headers=alex)
    resolved = (await kernel.post("/internal/users", json={"subject": SUBJECTS[0]})).json()
    assert resolved["id"] == alex[USER_HEADER]
    assert resolved["preferences"]["area"] == "munich"
    assert resolved["preferences"]["timezone"] == "UTC"


async def test_rows_are_separated_by_postgres(kernel, people) -> None:
    from uuid import UUID

    from arga_tenancy import as_user

    alex, sam = people
    await kernel.patch("/me/preferences", json={"locale": "es"}, headers=alex)
    like = "kernel_preferences_like_production"
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "do $$ begin if not exists (select 1 from pg_roles where rolname = "
                f"'{like}') then create role {like} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {like}"))
        await connection.execute(text(f"grant select on kernel.person_preferences to {like}"))
    with as_user(UUID(sam[USER_HEADER])):
        async with engine().begin() as connection:
            await connection.execute(text(f"set local role {like}"))
            seen = await connection.scalar(text("select count(*) from kernel.person_preferences"))
    assert seen == 0
