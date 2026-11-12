from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest

from arga_contracts import notify
from arga_tenancy import as_user

PERSON = UUID("00000000-0000-4000-8000-0000000a1e70")


def kernel_saying(timezone: str | None) -> httpx.AsyncClient:
    def answer(request: httpx.Request) -> httpx.Response:
        if timezone is None:
            return httpx.Response(503)
        assert request.headers["x-arga-user"] == str(PERSON)
        return httpx.Response(200, json={"timezone": timezone})

    return httpx.AsyncClient(transport=httpx.MockTransport(answer))


def test_without_a_person_the_instance_zone_rules(monkeypatch) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", "Asia/Tokyo")
    assert notify.at(date(2026, 3, 1), time(9)) == datetime(
        2026, 3, 1, 9, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert ZoneInfo("Asia/Tokyo") == notify.MADRID


def test_a_wrong_instance_zone_falls_back_to_utc(monkeypatch) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", "Nowhere/Never")
    assert notify.zone() == ZoneInfo("UTC")


@pytest.mark.parametrize(
    ("said", "expected"), [("America/Chicago", "America/Chicago"), (None, "UTC")]
)
async def test_the_person_zone_comes_from_the_kernel(monkeypatch, said, expected) -> None:
    monkeypatch.delenv("OPENARGA_TIMEZONE", raising=False)
    async with kernel_saying(said) as client:
        with as_user(PERSON):
            found = await notify.zone_of_person(client)
    assert found == ZoneInfo(expected)
