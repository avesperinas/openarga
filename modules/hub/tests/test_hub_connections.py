from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from arga_widgets import validate
from hub import catalogue, connections, widgets
from hub.tools import NoArguments, get_connections

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("status", "paused", "expires", "recent", "expected"),
    [
        ("pending", False, None, [], "pending"),
        ("active", True, None, ["error", "error"], "paused"),
        ("active", False, NOW - timedelta(days=1), ["ok"], "expired"),
        ("active", False, NOW + timedelta(days=3), ["ok"], "expiring"),
        ("active", False, NOW + timedelta(days=90), ["ok"], "active"),
        ("active", False, None, ["error", "error", "ok"], "failing"),
        ("active", False, None, ["error", "ok"], "active"),
        ("active", False, None, ["running", "error", "skipped", "error"], "failing"),
        ("active", False, None, ["rate_limited", "rate_limited"], "active"),
        ("active", False, None, [], "active"),
    ],
)
def test_the_state_comes_from_facts(status, paused, expires, recent, expected) -> None:
    assert connections.state_of(status, paused, expires, recent, NOW) == expected


def test_the_reason_names_the_connection_and_the_date() -> None:
    assert connections.reason_of("BBVA", "expired", NOW - timedelta(days=2), None, NOW) == (
        "Access to BBVA expired on 2026-09-20; it needs reconnecting."
    )
    assert connections.reason_of("BBVA", "expiring", NOW + timedelta(days=1), None, NOW) == (
        "Access to BBVA expires in 1 day."
    )
    assert connections.reason_of("Bitvavo", "failing", None, "403 key revoked", NOW) == (
        "Bitvavo is failing: 403 key revoked"
    )
    assert connections.reason_of("Bitvavo", "active", None, None, NOW) is None


async def connect(
    schema, label: str, provider: str = "bitvavo", with_credentials: bool = True, **extra
) -> str:
    columns = ", ".join(["provider", "label", *extra])
    values = ", ".join([":provider", ":label", *(f":{key}" for key in extra)])
    async with schema.begin() as connection:
        created = await connection.scalar(
            text(f"insert into hub.hub_connection ({columns}) values ({values}) returning id"),
            {"provider": provider, "label": label, **extra},
        )
        known = catalogue.BY_ID.get(provider)
        for secret in known.secrets if known and with_credentials else ():
            await connection.execute(
                text(
                    "insert into hub.hub_credential "
                    "(connection_id, key, ciphertext, hint) values (:c, :key, :blob, '…abcd')"
                ),
                {"c": created, "key": secret.key, "blob": b"sintetico"},
            )
        return created


async def ran(schema, connection_id, outcome: str, ago: timedelta, emitted=0, detail=None) -> None:
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into hub.hub_run (connection_id, capability, operation, "
                "started_at, finished_at, outcome, emitted, detail) "
                "values (:c, 'sync', 'balances', :at, :at, :outcome, :emitted, :detail)"
            ),
            {
                "c": connection_id,
                "at": NOW - ago,
                "outcome": outcome,
                "emitted": emitted,
                "detail": detail,
            },
        )


async def test_the_listing_reads_the_runs(schema) -> None:
    good = await connect(schema, "Bitvavo")
    await ran(schema, good, "ok", timedelta(days=9), emitted=100)
    await ran(schema, good, "ok", timedelta(hours=3), emitted=4)
    broken = await connect(schema, "Claude", provider="claude")
    await ran(schema, broken, "error", timedelta(hours=2), detail="401 token expired")
    await ran(schema, broken, "error", timedelta(hours=1), detail="401 token expired")

    async with schema.connect() as connection:
        found = {item.label: item for item in await connections.listed(connection, NOW)}

    assert found["Bitvavo"].state == "active"
    assert found["Bitvavo"].last_ok_at == NOW - timedelta(hours=3)
    assert found["Bitvavo"].emitted_week == 4
    assert found["Bitvavo"].category == "finance"
    assert found["Claude"].state == "failing"
    assert found["Claude"].reason == "Claude is failing: 401 token expired"
    assert found["Claude"].last_ok_at is None


async def test_the_widget_puts_what_needs_you_first(schema) -> None:
    await connect(schema, "Bitvavo")
    await connect(schema, "Santander", provider="enable_banking", status="pending")

    async with schema.connect() as connection:
        body = await widgets.status(connection, NOW)

    validate("list", body["body"], body["state"])
    assert body["state"] == "ready"
    assert body["body"]["rows"] == [
        {"label": "Santander", "value": "Unfinished", "tone": "warning"},
        {"label": "Bitvavo", "value": "Up to date", "tone": "positive"},
    ]
    assert body["body"]["detail"] == "Santander is waiting for you to finish authorising it."


async def test_an_expired_connection_shows_in_red_without_hiding_the_rest(schema) -> None:
    await connect(schema, "Bitvavo")
    await connect(
        schema,
        "BBVA",
        provider="enable_banking",
        consent_expires_at=NOW - timedelta(days=2),
    )

    async with schema.connect() as connection:
        body = await widgets.status(connection, NOW)

    validate("list", body["body"], body["state"])
    assert body["state"] == "ready"
    assert body["body"]["rows"][0] == {"label": "BBVA", "value": "Expired", "tone": "negative"}
    assert [row["label"] for row in body["body"]["rows"]] == ["BBVA", "Bitvavo"]
    assert body["body"]["detail"] == "Access to BBVA expired on 2026-09-20; it needs reconnecting."


async def test_all_well_says_so(schema) -> None:
    good = await connect(schema, "Bitvavo")
    await ran(schema, good, "ok", timedelta(hours=1))

    async with schema.connect() as connection:
        body = await widgets.status(connection, NOW)

    assert body["body"]["detail"] == "all up to date"


async def test_the_tool_tells_what_is_connected_and_what_still_lives_in_its_app(schema) -> None:
    await connect(schema, "Bitvavo")

    async with schema.connect() as connection:
        content = await get_connections(connection, NoArguments())

    assert [(c["name"], c["provider"], c["category"]) for c in content["connections"]] == [
        ("Bitvavo", "Bitvavo", "Finanzas")
    ]
    assert content["configured_elsewhere"] == []


async def test_the_tool_runs_as_the_read_role_and_refuses_without_a_scope(schema, api) -> None:
    await connect(schema, "Bitvavo")

    read = await api.post("/tools/get_connections", json={}, headers={"x-arga-scopes": "hub:read"})
    refused = await api.post("/tools/get_connections", json={}, headers={"x-arga-scopes": ""})
    unknown = await api.post(
        "/tools/get_connections", json={"x": 1}, headers={"x-arga-scopes": "hub:read"}
    )

    assert read.status_code == 200, read.text
    assert [c["name"] for c in read.json()["content"]["connections"]] == ["Bitvavo"]
    assert refused.status_code == 403
    assert unknown.status_code == 422


async def test_a_connection_without_its_credential_is_half_done_and_says_what(schema) -> None:
    await connect(schema, "Claude del trabajo", provider="claude", with_credentials=False)

    async with schema.connect() as connection:
        [found] = await connections.listed(connection, NOW)

    assert found.state == "pending"
    assert found.reason == "Claude del trabajo is missing its credential: paste it in its page."
