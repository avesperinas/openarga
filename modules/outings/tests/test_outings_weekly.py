from __future__ import annotations

from datetime import UTC, datetime

from outings import weekly


def test_monday_before_six_is_still_last_week() -> None:
    assert weekly.key(datetime(2026, 10, 12, 3, 30, tzinfo=UTC)) is None
    assert weekly.key(datetime(2026, 10, 12, 4, 0, tzinfo=UTC)) == "agenda:2026-W42"


def test_the_rest_of_the_week_asks_for_the_same_week() -> None:
    thursday = weekly.key(datetime(2026, 10, 15, 18, 0, tzinfo=UTC))
    sunday = weekly.key(datetime(2026, 10, 18, 21, 0, tzinfo=UTC))

    assert thursday == sunday == "agenda:2026-W42"


def test_it_asks_at_most_once_an_hour_per_person() -> None:
    weekly.ASKED.clear()

    assert weekly.due("ana", clock=1000.0) is True
    assert weekly.due("ana", clock=1000.0 + 1800) is False
    assert weekly.due("luis", clock=1000.0 + 1800) is True
    assert weekly.due("ana", clock=1000.0 + 3600) is True


async def test_the_weekly_agenda_is_an_ai_run_through_the_kernel(api, hub_app, area) -> None:
    from outings.main import as_app

    async with as_app() as connection:
        asked = await weekly.ask(connection, datetime(2026, 10, 15, 18, 0, tzinfo=UTC))
        again = await weekly.ask(connection, datetime(2026, 10, 16, 9, 0, tzinfo=UTC))

    assert asked is not None and asked.status == "done" and asked.provider == "fake"
    assert asked.run_id and again is not None and again.run_id == asked.run_id


async def test_monday_before_six_asks_nothing(api) -> None:
    from outings.main import as_app

    async with as_app() as connection:
        assert await weekly.ask(connection, datetime(2026, 10, 12, 3, 30, tzinfo=UTC)) is None


async def test_the_brief_fits_in_one_run(api, area) -> None:
    from arga_contracts.ai import RunRequest
    from outings import by_hand
    from outings.main import as_app

    async with as_app() as connection:
        brief = await by_hand.brief(connection)

    RunRequest(task=brief, key="agenda:2026-W42", web=True)
