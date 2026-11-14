from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from hub import catalogue, sync
from hub.providers import SourceError, ine


def month(year: int, number: int, value: float, **extra) -> dict:
    return {
        "Fecha": 0,
        "FK_TipoDato": 1,
        "FK_Periodo": number,
        "Anyo": year,
        "Valor": value,
        **extra,
    }


ANSWER = {
    "COD": "IPC251852",
    "Nombre": "Nacional. Índice general. Índice. ",
    "Data": [month(2025, 11, 119.532), month(2025, 10, 119.301), month(2025, 12, 119.942)],
}


def test_each_month_is_one_point_in_order() -> None:
    assert ine.points(ANSWER) == [
        ("2025-10", 119.301),
        ("2025-11", 119.532),
        ("2025-12", 119.942),
    ]


def test_a_month_without_value_or_secret_is_left_out() -> None:
    body = {
        "Data": [month(2025, 1, None), month(2025, 2, 110.0, Secreto=True), month(2025, 13, 1.0)]
    }

    assert ine.points(body) == []


def test_the_identity_is_the_month_and_its_value() -> None:
    [event] = ine.events([("2025-12", 119.942)])

    assert event["type"] == "economy.cpi"
    assert event["ts"].startswith("2025-12-01T00:00:00")
    assert event["payload"] == {
        "month": "2025-12",
        "index": 119.942,
        "series": "IPC251852",
        "base_year": 2021,
        "area": "ES",
    }
    assert event["dedup_hash"] == "ine:IPC251852:2025-12:119.942"


async def test_ten_years_are_asked_for() -> None:
    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url)
        return httpx.Response(200, json=ANSWER)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        found = await ine.fetch(client)

    assert len(found) == 3
    assert asked[0].path.endswith("/DATOS_SERIE/IPC251852")
    assert asked[0].params["nult"] == "120"


@pytest.mark.parametrize(
    ("status", "transient", "limited"),
    [(503, True, False), (429, False, True), (404, False, False)],
)
async def test_what_the_source_says_is_kept(status: int, transient: bool, limited: bool) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status))
    ) as client:
        with pytest.raises(SourceError) as error:
            await ine.fetch(client)

    assert error.value.transient is transient
    assert error.value.rate_limited is limited


async def test_an_empty_series_is_a_failure_and_not_a_quiet_pass() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"Data": []}))
    ) as client:
        with pytest.raises(SourceError):
            await ine.fetch(client)


def test_the_economy_category_and_the_ine_are_in_the_catalogue() -> None:
    [category] = [c for c in catalogue.listed() if c["id"] == "economy"]
    [provider] = category["providers"]

    assert category["name"] == "Economy"
    assert provider["id"] == "ine"
    assert provider["available"] is True
    assert catalogue.provider("ine").secrets == ()
    assert catalogue.provider("ine").emits == ("economy.cpi",)


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
    await kernel_db.engine().dispose()


async def test_the_connection_is_made_without_a_key_and_a_pass_fills_the_log(
    api, schema, kernel
) -> None:
    created = await api.post("/connections", json={"provider": "ine", "label": "IPC"})
    assert created.status_code == 201, created.text
    row = SimpleNamespace(id=UUID(created.json()["id"]), provider="ine", label="IPC", config={})

    async def no_wait(_: float) -> None:
        return None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=ANSWER))
    ) as source:
        first = await sync.run(row, source=source, kernel=kernel, sleep=no_wait, attempts=1)
        again = await sync.run(row, source=source, kernel=kernel, sleep=no_wait, attempts=1)

    async with schema.connect() as connection:
        months = (
            (
                await connection.execute(
                    text(
                        "select payload->>'month' from kernel.events "
                        "where module = 'hub' and type = 'economy.cpi' order by ts"
                    )
                )
            )
            .scalars()
            .all()
        )

    assert first.outcome == "ok", first.detail
    assert first.emitted == 3
    assert again.emitted == 0
    assert months == ["2025-10", "2025-11", "2025-12"]
