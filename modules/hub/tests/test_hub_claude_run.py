# ruff: noqa: F811

from __future__ import annotations

import json
import secrets
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from test_hub_claude import (  # noqa: F401
    MODULE_TOKEN,
    TOKEN,
    ask,
    fake,
    hand_over,
    kernel,
    migrated,
)

from hub import claude_run, credentials
from hub.db import as_module

REFRESH = f"refresh-de-prueba-{secrets.token_hex(8)}"
ACCESS = f"access-de-prueba-{secrets.token_hex(8)}"
MODULES = [
    {"id": "outings", "name": "Outings", "enabled": True, "uses": ["claude.run"]},
    {"id": "insights", "name": "Insights", "enabled": True, "uses": ["claude.run"]},
    {"id": "vitals", "name": "Vitals", "enabled": True, "uses": []},
]


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("CLAUDE_RUN_CLIENT_SECRET", "secreto-de-prueba")


def run_as(module: str, key: str = "agenda:2026-W41", **extra):
    def call(api):
        return api.post(
            "/capabilities/claude.run",
            json={"key": key, "prompt": "Rellena la agenda", **extra},
            headers={
                "x-module-token": MODULE_TOKEN,
                "x-arga-module": module,
            },
        )

    return call


async def grant(account, app: str = "outings") -> None:
    async with as_module() as database:
        await credentials.store(database, "claude", account, claude_run.grant_key(app), REFRESH)


async def runs(schema) -> list:
    async with schema.connect() as connection:
        return (
            await connection.execute(
                text(
                    "select outcome, detail, idempotency_key from hub.hub_run "
                    "where operation = 'run' order by started_at"
                )
            )
        ).all()


async def test_without_the_apps_permission_nothing_is_queued(api, kernel, schema) -> None:
    await hand_over(api, uuid4())

    answer = (await run_as("outings")(api)).json()

    assert answer["outcome"] == "skipped"
    assert answer["code"] == "not_granted"
    assert await runs(schema) == []


async def test_with_permission_a_week_is_queued_once(api, kernel, schema) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account)

    first = (await run_as("outings", tools=["WebSearch"])(api)).json()
    again = (await run_as("outings", tools=["WebSearch"])(api)).json()

    assert first["outcome"] == "queued"
    assert again["repeated"] is True
    assert [(r.outcome, r.idempotency_key) for r in await runs(schema)] == [
        ("running", "outings:agenda:2026-W41")
    ]


async def test_another_apps_permission_is_not_this_ones(api, kernel, schema) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account, "insights")

    assert (await run_as("outings")(api)).json()["code"] == "not_granted"


async def test_tools_beyond_the_web_are_refused(api, kernel) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account)

    assert (await run_as("outings", tools=["Bash"])(api)).status_code == 422


async def test_the_permission_asks_for_every_read_and_only_its_own_write(api, kernel) -> None:
    account = uuid4()
    await hand_over(api, account)

    async with as_module() as database:
        url = await claude_run.authorize(database, account, "outings", MODULES)

    query = parse_qs(urlparse(url).query)
    scopes = query["scope"][0].split()
    assert url.startswith("http://localhost:8000/auth/realms/arga/protocol/openid-connect/auth")
    assert query["client_id"] == ["claude-run"]
    assert query["code_challenge_method"] == ["S256"]
    assert {
        "offline_access",
        "outings:read",
        "insights:read",
        "vitals:read",
        "outings:write",
    } <= set(scopes)
    assert [scope for scope in scopes if scope.endswith(":write")] == ["outings:write"]


async def test_an_app_that_does_not_ask_for_claude_gets_no_permission(api, kernel) -> None:
    account = uuid4()
    await hand_over(api, account)

    with pytest.raises(claude_run.Refused) as refused:
        async with as_module() as database:
            await claude_run.authorize(database, account, "vitals", MODULES)

    assert refused.value.status == 404


def keycloak(scope: str = "openid offline_access outings:read outings:write"):
    seen: list[dict] = []

    def answer(request: httpx.Request) -> httpx.Response:
        form = dict(parse_qs(request.content.decode()))
        seen.append({key: value[0] for key, value in form.items()})
        if request.url.path.endswith("/revoke"):
            return httpx.Response(200)
        if form["grant_type"] == ["authorization_code"]:
            return httpx.Response(
                200, json={"access_token": ACCESS, "refresh_token": REFRESH, "scope": scope}
            )
        return httpx.Response(200, json={"access_token": ACCESS, "refresh_token": REFRESH})

    return httpx.MockTransport(answer), seen


async def test_the_way_back_keeps_the_permission_on_the_chosen_account_only(api, kernel) -> None:
    first, second = uuid4(), uuid4()
    await hand_over(api, first, label="Personal")
    await hand_over(api, second, label="Trabajo")
    transport, seen = keycloak()

    for account in (first, second):
        async with as_module() as database:
            url = await claude_run.authorize(database, account, "outings", MODULES)
        state = parse_qs(urlparse(url).query)["state"][0]
        async with httpx.AsyncClient(transport=transport) as auth, as_module() as database:
            assert await claude_run.finish_grant(database, auth, "codigo", state) == (
                "outings",
                account,
            )

    async with as_module() as database:
        granted = await claude_run.grants(database)
    assert [(one.app, one.label) for one in granted] == [("outings", "Trabajo")]
    assert seen[0]["client_secret"] == "secreto-de-prueba"
    assert len(seen[0]["code_verifier"]) >= 43


async def test_a_way_back_that_is_not_ours_is_refused(api, kernel) -> None:
    transport, _ = keycloak()
    with pytest.raises(claude_run.Refused):
        async with httpx.AsyncClient(transport=transport) as auth, as_module() as database:
            await claude_run.finish_grant(database, auth, "codigo", "x" * 40)


async def test_a_permission_without_offline_access_is_not_kept(api, kernel) -> None:
    account = uuid4()
    await hand_over(api, account)
    transport, _ = keycloak(scope="openid outings:read outings:write")
    async with as_module() as database:
        url = await claude_run.authorize(database, account, "outings", MODULES)
    state = parse_qs(urlparse(url).query)["state"][0]

    with pytest.raises(claude_run.Refused):
        async with httpx.AsyncClient(transport=transport) as auth, as_module() as database:
            await claude_run.finish_grant(database, auth, "codigo", state)


@pytest.fixture
def fake_cli(tmp_path: Path, monkeypatch) -> Path:
    record = tmp_path / "llamada.json"
    script = tmp_path / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "config = json.load(open(args[args.index('--mcp-config') + 1]))\n"
        f"json.dump({{'args': args, 'token': os.environ.get('CLAUDE_CODE_OAUTH_TOKEN'),"
        f" 'mcp': config}}, open({str(record)!r}, 'w'))\n"
        "print(json.dumps({'type': 'result', 'is_error': False, 'num_turns': 7,"
        " 'result': 'Apuntados 12 eventos.', 'modelUsage': {"
        "'claude-haiku-5-5': {'outputTokens': 40}, 'claude-opus-5-5': {'outputTokens': 900}}}))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLAUDE_BIN", str(script))
    return record


async def test_the_runner_launches_claude_with_nothing_but_arga(
    api, kernel, schema, fake_cli
) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account)
    await run_as("outings", tools=["WebSearch", "WebFetch"])(api)
    transport, seen = keycloak()

    async with as_module() as database:
        job = (await database.execute(claude_run.NEXT)).one()
    async with httpx.AsyncClient(transport=transport) as auth:
        result = await claude_run.work(job, auth, kernel)

    call = json.loads(fake_cli.read_text())
    args = call["args"]
    assert result.outcome == "ok"
    assert result.detail == "Hecho en 7 turnos con claude-opus-5-5. Apuntados 12 eventos."
    assert call["token"] == TOKEN
    assert args[args.index("--tools") + 1] == "WebSearch,WebFetch"
    assert "--restricted" in args and "--strict-mcp-config" in args
    assert args[args.index("--allowedTools") + 1] == "mcp__arga,WebSearch,WebFetch"
    assert call["mcp"]["mcpServers"]["arga"]["headers"] == {"Authorization": f"Bearer {ACCESS}"}
    assert seen[-1]["grant_type"] == "refresh_token"
    assert [(r.outcome, r.detail) for r in await runs(schema)] == [
        ("ok", "Hecho en 7 turnos con claude-opus-5-5. Apuntados 12 eventos.")
    ]


async def test_a_permission_removed_before_the_run_skips_it(api, kernel, schema, fake_cli) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account)
    await run_as("outings")(api)
    transport, _ = keycloak()
    async with httpx.AsyncClient(transport=transport) as auth, as_module() as database:
        assert await claude_run.revoke(database, auth, "outings") is True

    async with as_module() as database:
        job = (await database.execute(claude_run.NEXT)).one()
    async with httpx.AsyncClient(transport=transport) as auth:
        result = await claude_run.work(job, auth, kernel)

    assert (result.outcome, result.code) == ("skipped", "not_granted")
    assert not fake_cli.exists()


def test_what_the_cli_says_is_understood() -> None:
    ok = claude_run.understood(0, '{"is_error": false, "num_turns": 3, "result": "Listo"}', "")
    failed = claude_run.understood(1, "", "Error: algo se rompió")
    limited = claude_run.understood(
        1,
        '{"is_error": true, "result": "Claude usage limit reached. Your limit will reset at 5pm"}',
        "",
    )

    assert (ok.ok, ok.detail) == (True, "Hecho en 3 turnos. Listo")
    assert (
        claude_run.understood(
            0, '{"num_turns": 2, "result": "Listo", "modelUsage": {"claude-opus-5-5": {}}}', ""
        ).detail
        == "Hecho en 2 turnos con claude-opus-5-5. Listo"
    )
    assert (failed.ok, failed.rate_limited, failed.detail) == (
        False,
        False,
        "Error: algo se rompió",
    )
    assert (limited.ok, limited.rate_limited) == (False, True)


async def test_the_runs_end_carries_the_key_the_app_asked_with(
    api, kernel, schema, fake_cli
) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account)
    await run_as("outings", key="thread:abc")(api)
    transport, _ = keycloak()

    async with as_module() as database:
        job = (await database.execute(claude_run.NEXT)).one()
    async with httpx.AsyncClient(transport=transport) as auth:
        await claude_run.work(job, auth, kernel)

    async with schema.connect() as connection:
        payload = (
            await connection.execute(
                text(
                    "select payload from kernel.events where type = 'hub.run' "
                    "and payload->>'operation' = 'run'"
                )
            )
        ).scalar_one()
    assert payload["key"] == "outings:thread:abc"
    assert payload["outcome"] == "ok"


async def test_what_was_cut_by_a_restart_is_given_up_and_told(api, kernel, schema) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account)
    await run_as("outings", key="thread:cortada")(api)
    async with as_module() as database:
        await database.execute(claude_run.NEXT)

    async def people(_kernel) -> list:
        from arga_tenancy import current_user

        return [current_user.get()]

    import hub.claude_run as module

    original = module.users
    module.users = people
    try:
        assert await claude_run.recover(kernel) == 1
    finally:
        module.users = original

    assert [(r.outcome, r.detail) for r in await runs(schema)] == [
        ("error", "Se cortó a medias: arga se reinició mientras corría.")
    ]
    async with as_module() as database:
        assert (await database.execute(claude_run.NEXT)).one_or_none() is None


def test_room_is_read_from_the_last_observation_of_the_account() -> None:
    now = datetime.now(UTC)
    open_until = (now + timedelta(hours=2)).isoformat()
    closed = (now - timedelta(minutes=1)).isoformat()

    assert claude_run.crowded(None, now) is None
    calm = {"window_utilization": 40, "window_resets_at": open_until}
    assert claude_run.crowded(calm, now) is None
    assert (
        claude_run.crowded({"window_utilization": 100, "window_resets_at": open_until}, now)
        == "la ventana de cinco horas va al 100 %"
    )
    assert claude_run.crowded({"week_utilization": 100, "week_resets_at": open_until}, now) == (
        "la semana va al 100 %"
    )
    assert claude_run.crowded({"week_utilization": 95, "week_resets_at": open_until}, now) is None
    assert claude_run.crowded({"window_utilization": 99, "window_resets_at": closed}, now) is None


async def test_a_background_run_waits_for_room_and_a_person_does_not(
    api, kernel, schema, fake
) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account, "insights")
    fake.week_used = "1"
    ping = {"connection": str(account), "key": "manual:1", "trigger": "manual"}
    await ask(api, "claude.ping", ping)

    await run_as("insights", key="morning:2026-10-13", wait_for_room=True)(api)
    async with as_module() as database:
        waiting = (await database.execute(claude_run.NEXT)).one()
    assert await claude_run.postponed(waiting, kernel) is True
    async with as_module() as database:
        assert (await database.execute(claude_run.NEXT)).one_or_none() is None

    await run_as("insights", key="thread:abc")(api)
    async with as_module() as database:
        asked = (await database.execute(claude_run.NEXT)).one()
    assert await claude_run.postponed(asked, kernel) is False


async def test_a_background_run_that_waited_too_long_is_skipped_and_told(
    api, kernel, schema, fake
) -> None:
    account = uuid4()
    await hand_over(api, account)
    await grant(account, "insights")
    fake.week_used = "1"
    ping = {"connection": str(account), "key": "manual:2", "trigger": "manual"}
    await ask(api, "claude.ping", ping)
    await run_as("insights", key="morning:2026-10-12", wait_for_room=True)(api)
    async with schema.begin() as connection:
        await connection.execute(
            text("update hub.hub_claude_job set created_at = now() - interval '19 hours'")
        )

    async with as_module() as database:
        job = (await database.execute(claude_run.NEXT)).one()
    assert await claude_run.postponed(job, kernel) is True

    assert [(r.outcome, r.detail) for r in await runs(schema)] == [
        ("skipped", "Sin hueco en tu uso de Claude: «Principal»: la semana va al 100 %.")
    ]
