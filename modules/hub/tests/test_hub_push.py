from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from test_hub_statements import kernel, migrated  # noqa: F401 -- fixtures

from arga_tenancy import current_user
from hub import push
from hub.main import app

PATH = "/push/apple-health"


@pytest.fixture
async def connected(api, kernel):  # noqa: F811
    created = await api.post("/connections", json={"provider": "apple_health"})
    assert created.status_code == 201
    return created.json()


class Outside:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client

    async def post(self, path: str, **kwargs):
        token = current_user.set(None)
        try:
            return await self.client.post(path, **kwargs)
        finally:
            current_user.reset(token)


@pytest.fixture
async def outside(schema):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://hub") as c:
        yield Outside(c)


def bearer(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


async def steps(schema) -> list[tuple[str, int]]:
    async with schema.connect() as connection:
        rows = await connection.execute(
            text(
                "select payload from kernel.events where type = 'health.steps' "
                "order by payload->>'date', (payload->>'steps')::int"
            )
        )
        return [(row.payload["date"], row.payload["steps"]) for row in rows]


async def test_connecting_shows_the_token_once(api, connected) -> None:
    token = connected["ingest_token"]

    assert token.split(".")[0] == UUID("00000000-0000-4000-8000-00000000a7e5").hex
    detail = (await api.get(f"/connections/{connected['id']}")).json()
    assert token not in str(detail)
    assert "ingest_token" not in detail


async def test_two_days_leave_two_events_and_repeating_duplicates_nothing(
    connected, outside, schema
) -> None:
    body = [{"date": "2026-09-23", "steps": 8412}, {"date": "2026-09-24", "steps": 10310}]

    first = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))
    again = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert first.status_code == 200
    assert first.json() == {"received": 2, "new": 2}
    assert again.json() == {"received": 2, "new": 0}
    assert await steps(schema) == [("2026-09-23", 8412), ("2026-09-24", 10310)]


@pytest.mark.parametrize(
    "body",
    [
        {"days": [{"date": "2026-09-24", "steps": 10310}]},
        {"date": "2026-09-24", "steps": 10310},
        {"days": [{"date": "2026-09-24", "steps": "10310"}]},
    ],
)
async def test_a_shortcut_can_send_a_dictionary(connected, outside, schema, body) -> None:
    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 200
    assert await steps(schema) == [("2026-09-24", 10310)]


async def test_a_day_that_grows_is_a_new_event(connected, outside, schema) -> None:
    for count in (3000, 7400):
        await outside.post(
            PATH,
            json=[{"date": "2026-09-24", "steps": count}],
            headers=bearer(connected["ingest_token"]),
        )

    assert await steps(schema) == [("2026-09-24", 3000), ("2026-09-24", 7400)]


async def test_each_push_is_a_run_on_the_card(api, connected, outside) -> None:
    await outside.post(
        PATH, json=[{"date": "2026-09-24", "steps": 1}], headers=bearer(connected["ingest_token"])
    )

    detail = (await api.get(f"/connections/{connected['id']}")).json()
    assert detail["state"] == "active"
    assert detail["runs"][0]["outcome"] == "ok"


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer ",
        "Basic abc",
        "Bearer no-es-un-token",
        "Bearer a.b.c",
    ],
)
async def test_without_a_valid_token_it_is_a_401(connected, outside, schema, authorization) -> None:
    headers = {"authorization": authorization} if authorization else {}

    response = await outside.post(PATH, json=[{"date": "2026-09-24", "steps": 5}], headers=headers)

    assert response.status_code == 401
    assert await steps(schema) == []


async def test_a_forged_secret_for_a_real_connection_is_a_401(connected, outside, schema) -> None:
    user, connection, _secret = connected["ingest_token"].split(".")

    response = await outside.post(
        PATH, json=[{"date": "2026-09-24", "steps": 5}], headers=bearer(f"{user}.{connection}.otro")
    )

    assert response.status_code == 401
    assert await steps(schema) == []


async def test_a_token_claiming_someone_else_is_a_401(connected, outside, schema) -> None:
    _user, connection, secret = connected["ingest_token"].split(".")
    other = UUID("00000000-0000-4000-8000-00000000b0b0").hex

    response = await outside.post(
        PATH,
        json=[{"date": "2026-09-24", "steps": 5}],
        headers=bearer(f"{other}.{connection}.{secret}"),
    )

    assert response.status_code == 401


async def test_a_new_token_retires_the_old_one(api, connected, outside) -> None:
    response = await api.post(f"/connections/{connected['id']}/token")
    renewed = response.json()["ingest_token"]
    body = [{"date": "2026-09-24", "steps": 5}]

    old = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))
    new = await outside.post(PATH, json=body, headers=bearer(renewed))

    assert old.status_code == 401
    assert new.status_code == 200


async def test_a_paused_connection_receives_nothing(api, connected, outside) -> None:
    await api.post(f"/connections/{connected['id']}/pause")

    response = await outside.post(
        PATH, json=[{"date": "2026-09-24", "steps": 5}], headers=bearer(connected["ingest_token"])
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"days": []},
        {"days": [{"date": "2026-09-24", "steps": 5}], "other": 1},
        [{"date": "ayer", "steps": 5}],
        [{"date": "2026-09-24", "steps": -1}],
        [{"date": (date.today() + timedelta(days=5)).isoformat(), "steps": 5}],
        [{"date": "2026-09-24", "steps": 1}] * (push.MAX_ITEMS + 1),
    ],
)
async def test_what_is_not_days_of_steps_is_a_422(connected, outside, schema, body) -> None:
    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 422
    assert await steps(schema) == []


async def test_a_source_it_does_not_know_is_a_404(outside) -> None:
    response = await outside.post("/push/fitbit", json=[], headers=bearer("x.y.z"))

    assert response.status_code == 404


async def test_apple_health_is_listed_under_health() -> None:
    from hub import catalogue

    health = next(one for one in catalogue.listed() if one["id"] == "health")
    assert [p["id"] for p in health["providers"]] == ["apple_health", "google_health"]
    assert health["providers"][0]["capabilities"] == ["push"]


async def events_of(schema, kind: str) -> list[dict]:
    async with schema.connect() as connection:
        rows = await connection.execute(
            text("select payload from kernel.events where type = :kind order by payload::text"),
            {"kind": kind},
        )
        return [row.payload for row in rows]


async def test_a_day_brings_the_rest_of_its_figures_in_one_event(connected, outside, schema):
    body = {
        "date": "2026-09-24",
        "steps": "10310",
        "resting_heart_rate": 58,
        "hrv_ms": "41,5",
        "active_kcal": 512.349,
    }

    first = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))
    again = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert first.json() == {"received": 2, "new": 2}
    assert again.json() == {"received": 2, "new": 0}
    assert await steps(schema) == [("2026-09-24", 10310)]
    assert await events_of(schema, "health.daily") == [
        {
            "date": "2026-09-24",
            "metrics": {"resting_heart_rate": 58.0, "hrv_ms": 41.5, "active_kcal": 512.35},
        }
    ]


async def test_a_day_without_steps_is_only_its_figures(connected, outside, schema) -> None:
    response = await outside.post(
        PATH,
        json=[{"date": "2023-01-02", "vo2max": 44.1}],
        headers=bearer(connected["ingest_token"]),
    )

    assert response.json() == {"received": 1, "new": 1}
    assert await steps(schema) == []


async def test_the_profile_travels_on_its_own(connected, outside, schema) -> None:
    body = {"profile": {"blood_type": "A+", "sex": "male", "birth_date": "1990-01-01"}}

    first = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))
    again = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert first.json() == {"received": 1, "new": 1}
    assert again.json() == {"received": 1, "new": 0}
    assert await events_of(schema, "health.profile") == [
        {"blood_type": "A+", "sex": "male", "birth_date": "1990-01-01"}
    ]


@pytest.mark.parametrize(
    "body",
    [
        [{"date": "2026-09-24", "sexual_activity": 1}],
        [{"date": "2026-09-24", "resting_heart_rate": 900}],
        [{"date": "2026-09-24", "hrv_ms": "mucho"}],
        [{"date": "2026-09-24"}],
        [{"steps": 5}],
        {"profile": {"blood_type": "Z"}},
        {"profile": {}},
        {"profile": {"blood_type": "A+", "religion": "x"}},
    ],
)
async def test_what_it_does_not_know_is_a_422(connected, outside, schema, body) -> None:
    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 422
    assert await events_of(schema, "health.daily") == []
    assert await events_of(schema, "health.profile") == []


@pytest.mark.parametrize(
    "body",
    [
        {"date": ["2026-09-23", "2026-09-24", "2026-09-25"], "steps": [6898, 2991, 7919]},
        {"date": "2026-09-23\n2026-09-24\n2026-09-25", "steps": "6898\n2.991\n7919"},
    ],
)
async def test_a_week_of_steps_is_one_event_per_day(connected, outside, schema, body) -> None:
    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 200
    assert await steps(schema) == [
        ("2026-09-23", 6898),
        ("2026-09-24", 2991),
        ("2026-09-25", 7919),
    ]


async def test_a_single_figure_in_a_week_belongs_to_the_latest_day(
    connected, outside, schema
) -> None:
    body = {
        "date": "2026-09-25\n2026-09-24",
        "steps": "7919\n2991",
        "resting_heart_rate": "58",
    }

    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 200
    assert await events_of(schema, "health.daily") == [
        {"date": "2026-09-25", "metrics": {"resting_heart_rate": 58.0}}
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"date": "2026-09-24\n2026-09-25", "steps": "1\n2\n3"},
        {"date": ["2026-09-24", "2026-09-25"], "steps": ["1", "dos"]},
    ],
)
async def test_dates_and_steps_that_do_not_match_are_a_422(connected, outside, schema, body):
    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 422
    assert await steps(schema) == []


@pytest.mark.parametrize("raw", ["7.919", "7,919", "7919,4", "7919.0", 7919.0])
async def test_steps_as_the_shortcut_writes_them(connected, outside, schema, raw) -> None:
    body = {"date": "2026-09-25", "steps": raw}

    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 200
    assert await steps(schema) == [("2026-09-25", 7919)]


def lines(*values: object) -> str:
    return "\n".join(str(one) for one in values)


def sample(start: str, end: str, steps: float, source: str) -> push.Sample:
    return push.Sample(
        datetime.fromisoformat(f"2026-09-28T{start}+02:00"),
        datetime.fromisoformat(f"2026-09-28T{end}+02:00"),
        steps,
        push.rank_of(source),
    )


def test_a_walk_seen_by_the_watch_and_the_phone_counts_once() -> None:
    counts = push.as_health_counts(
        [
            sample("10:00:00", "10:10:00", 1000, "Apple Watch de Alguien"),
            sample("10:00:00", "10:10:00", 950, "iPhone de Alguien"),
        ]
    )

    assert counts == {date(2026, 9, 28): 1000}


def test_the_phone_fills_in_while_the_watch_is_charging() -> None:
    counts = push.as_health_counts(
        [
            sample("10:00:00", "10:10:00", 1000, "Apple Watch de Alguien"),
            sample("18:00:00", "18:30:00", 3000, "iPhone de Alguien"),
        ]
    )

    assert counts == {date(2026, 9, 28): 4000}


def test_half_covered_the_phone_keeps_the_half_the_watch_did_not_see() -> None:
    counts = push.as_health_counts(
        [
            sample("10:00:00", "10:10:00", 1000, "Apple Watch de Alguien"),
            sample("10:05:00", "10:15:00", 800, "iPhone de Alguien"),
        ]
    )

    assert counts == {date(2026, 9, 28): 1400}


def test_another_app_only_counts_where_neither_device_did() -> None:
    counts = push.as_health_counts(
        [
            sample("10:00:00", "10:10:00", 1000, "iPhone de Alguien"),
            sample("10:00:00", "10:20:00", 2000, "Una app"),
        ]
    )

    assert counts == {date(2026, 9, 28): 2000}


def test_a_sample_across_midnight_is_shared_by_both_days() -> None:
    counts = push.as_health_counts(
        [
            push.Sample(
                datetime.fromisoformat("2026-09-28T23:50:00+02:00"),
                datetime.fromisoformat("2026-09-29T00:10:00+02:00"),
                400,
                0,
            )
        ]
    )

    assert counts == {date(2026, 9, 28): 200, date(2026, 9, 29): 200}


async def test_the_shortcut_sends_samples_and_each_day_arrives_as_health_counts_it(
    connected, outside, schema
) -> None:
    body = {
        "start": lines(
            "2026-09-27T21:00:00+02:00",
            "2026-09-28T10:00:00+02:00",
            "2026-09-28T10:00:00+02:00",
            "2026-09-28T18:00:00+02:00",
            "2026-09-29T09:00:00+02:00",
        ),
        "end": lines(
            "2026-09-27T21:10:00+02:00",
            "2026-09-28T10:10:00+02:00",
            "2026-09-28T10:10:00+02:00",
            "2026-09-28T18:30:00+02:00",
            "2026-09-29T09:10:00+02:00",
        ),
        "steps": lines(500, "1.000", 950, 3000, "120,5"),
        "source": lines(
            "Apple Watch de Alguien",
            "Apple Watch de Alguien",
            "iPhone de Alguien",
            "iPhone de Alguien",
            "iPhone de Alguien",
        ),
        "resting_heart_rate": "58",
    }

    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 200
    assert await steps(schema) == [("2026-09-28", 4000), ("2026-09-29", 120)]
    assert await events_of(schema, "health.daily") == [
        {"date": "2026-09-29", "metrics": {"resting_heart_rate": 58.0}}
    ]


@pytest.mark.parametrize(
    "body",
    [
        {
            "start": lines("2026-09-28T10:00:00+02:00", "2026-09-28T11:00:00+02:00"),
            "end": "2026-09-28T10:10:00+02:00",
            "steps": "100",
            "source": "iPhone",
        },
        {
            "start": "2026-09-28T10:00:00",
            "end": "2026-09-28T10:10:00",
            "steps": "100",
            "source": "iPhone",
        },
        {
            "start": "2026-09-28T10:10:00+02:00",
            "end": "2026-09-28T10:00:00+02:00",
            "steps": "100",
            "source": "iPhone",
        },
        {
            "start": "2026-09-28T10:00:00+02:00",
            "end": "2026-09-28T10:10:00+02:00",
            "steps": "muchos",
            "source": "iPhone",
        },
    ],
)
async def test_samples_that_make_no_sense_are_a_422(connected, outside, schema, body) -> None:
    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 422
    assert await steps(schema) == []


def test_each_hour_is_the_source_that_counted_most() -> None:
    item = {
        "watch_start": lines("2026-09-28T10:00:00+02:00", "2026-09-28T11:00:00+02:00"),
        "watch_steps": lines(3000, 50),
        "phone_start": lines("2026-09-28T10:00:00+02:00", "2026-09-28T11:00:00+02:00"),
        "phone_steps": lines(2800, 1200),
    }

    assert push.by_hours(item) == {date(2026, 9, 28): 4200}


def test_an_hour_given_by_its_first_sample_still_meets_the_other_source() -> None:
    item = {
        "watch_start": "2026-09-28T10:07:00+02:00",
        "watch_steps": "3000",
        "phone_start": "2026-09-28T10:02:30+02:00",
        "phone_steps": "2800",
    }

    assert push.by_hours(item) == {date(2026, 9, 28): 3000}


def test_without_a_watch_the_phone_counts_alone() -> None:
    item = {
        "watch_start": "",
        "watch_steps": "",
        "phone_start": "2026-09-28T10:00:00+02:00",
        "phone_steps": "1.250",
    }

    assert push.by_hours(item) == {date(2026, 9, 28): 1250}


async def test_the_shortcut_sends_hours_and_each_day_arrives_once(
    connected, outside, schema
) -> None:
    body = {
        "watch_start": lines(
            "2026-09-27T22:00:00+02:00", "2026-09-28T10:00:00+02:00", "2026-09-29T09:00:00+02:00"
        ),
        "watch_steps": lines(500, 3000, 700),
        "phone_start": lines("2026-09-28T10:00:00+02:00", "2026-09-28T18:00:00+02:00"),
        "phone_steps": lines(2800, 4000),
        "resting_heart_rate": "58",
    }

    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 200
    assert await steps(schema) == [("2026-09-28", 7000), ("2026-09-29", 700)]
    assert await events_of(schema, "health.daily") == [
        {"date": "2026-09-29", "metrics": {"resting_heart_rate": 58.0}}
    ]


@pytest.mark.parametrize(
    "body",
    [
        {
            "watch_start": lines("2026-09-28T10:00:00+02:00", "2026-09-28T11:00:00+02:00"),
            "watch_steps": "100",
        },
        {"watch_start": "2026-09-28T10:00:00", "watch_steps": "100"},
        {"phone_start": "2026-09-28T10:00:00+02:00", "phone_steps": "100 pasos"},
        {"watch_start": "", "watch_steps": ""},
    ],
)
async def test_hours_that_make_no_sense_are_a_422(connected, outside, schema, body) -> None:
    response = await outside.post(PATH, json=body, headers=bearer(connected["ingest_token"]))

    assert response.status_code == 422
    assert await steps(schema) == []
