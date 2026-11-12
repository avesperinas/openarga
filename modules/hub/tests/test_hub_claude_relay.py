# ruff: noqa: F811

from __future__ import annotations

import json
import secrets
import stat
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from test_hub_claude import TOKEN, ask, fake, hand_over, kernel, migrated  # noqa: F401
from test_hub_claude_run import grant, keycloak, run_as, runs, secret  # noqa: F401

from hub import claude_run, connections
from hub.db import as_module

OTHER = f"sk-ant-oat01-otra-{secrets.token_hex(8)}"


@pytest.fixture
def cli(tmp_path: Path, monkeypatch) -> Path:
    record = tmp_path / "llamadas.jsonl"
    script = tmp_path / "claude"
    limit = tmp_path / "limite"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "token = os.environ.get('CLAUDE_CODE_OAUTH_TOKEN')\n"
        f"open({str(record)!r}, 'a').write(json.dumps(token) + '\\n')\n"
        f"if token == {TOKEN!r} and os.path.exists({str(limit)!r}):\n"
        "    print(json.dumps({'is_error': True, 'result':"
        " 'Claude usage limit reached. Your limit will reset at 5pm'}))\n"
        "    sys.exit(1)\n"
        "print(json.dumps({'is_error': False, 'num_turns': 3, 'result': 'Listo.'}))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLAUDE_BIN", str(script))
    return record


def tokens(record: Path) -> list[str]:
    return [json.loads(line) for line in record.read_text().splitlines()] if record.exists() else []


async def crowd(api, fake, account, used: str = "1") -> None:
    fake.week_used = used
    ping = {"connection": str(account), "key": f"manual:{uuid4()}", "trigger": "manual"}
    await ask(api, "claude.ping", ping)


async def next_job():
    async with as_module() as database:
        return (await database.execute(claude_run.NEXT)).one()


async def work(job, kernel):
    transport, _ = keycloak()
    async with httpx.AsyncClient(transport=transport) as auth:
        return await claude_run.work(job, auth, kernel)


async def test_a_titular_without_room_hands_the_run_to_the_other_account(
    api, kernel, schema, fake, cli
) -> None:
    titular, other = uuid4(), uuid4()
    await hand_over(api, titular, label="Principal")
    await hand_over(api, other, token=OTHER, label="Otra")
    await grant(titular, "insights")
    await crowd(api, fake, titular)
    await run_as("insights", key="morning:2026-10-20", wait_for_room=True)(api)

    job = await next_job()
    assert await claude_run.postponed(job, kernel) is False
    result = await work(job, kernel)

    assert tokens(cli) == [OTHER]
    assert result.outcome == "ok"
    assert (
        result.detail
        == "Con «Otra» («Principal»: la semana va al 100 %). Hecho en 3 turnos. Listo."
    )
    async with schema.connect() as connection:
        ran_on = await connection.scalar(text("select ran_on from hub.hub_claude_job"))
        payload = (
            await connection.execute(
                text(
                    "select payload from kernel.events where type = 'hub.run' "
                    "and payload->>'operation' = 'run'"
                )
            )
        ).scalar_one()
    assert ran_on == other
    assert (payload["ran_on"], payload["ran_with"]) == (str(other), "Otra")
    assert payload["connection"] == str(titular)


async def test_a_titular_without_a_token_hands_it_over_too(api, kernel, schema, fake, cli) -> None:
    titular, other = uuid4(), uuid4()
    await hand_over(api, titular, token=None, label="Principal")
    await hand_over(api, other, token=OTHER, label="Otra")
    await grant(titular, "outings")
    await run_as("outings")(api)

    result = await work(await next_job(), kernel)

    assert tokens(cli) == [OTHER]
    assert result.detail.startswith("Con «Otra» («Principal» no tiene token).")


async def test_when_no_account_can_it_is_skipped_and_says_why_each(
    api, kernel, schema, fake, cli
) -> None:
    titular = uuid4()
    await hand_over(api, titular, token=None, label="Principal")
    await grant(titular, "outings")
    await run_as("outings")(api)

    result = await work(await next_job(), kernel)

    assert tokens(cli) == []
    assert (result.outcome, result.code) == ("skipped", "no_account")
    assert result.detail == "Ninguna cuenta de Claude puede hacerla: «Principal» no tiene token."
    async with schema.connect() as connection:
        code = await connection.scalar(text("select code from hub.hub_run where operation = 'run'"))
    assert code == "no_account"


async def test_a_run_cut_by_the_usage_limit_goes_on_with_the_next_account(
    api, kernel, schema, fake, cli
) -> None:
    titular, other = uuid4(), uuid4()
    await hand_over(api, titular, label="Principal")
    await hand_over(api, other, token=OTHER, label="Otra")
    await grant(titular, "outings")
    (cli.parent / "limite").write_text("")
    await run_as("outings")(api)

    result = await work(await next_job(), kernel)

    assert tokens(cli) == [TOKEN, OTHER]
    assert result.outcome == "ok"
    assert result.detail.startswith("Con «Otra» («Principal» se quedó sin uso).")


async def test_an_account_with_the_relay_off_covers_no_one_and_the_run_waits(
    api, kernel, schema, fake, cli
) -> None:
    titular, other = uuid4(), uuid4()
    await hand_over(api, titular, label="Principal")
    await hand_over(api, other, token=OTHER, label="Otra")
    async with as_module() as database:
        assert await connections.set_relay(database, other, False) is True
        assert (await connections.detail(database, other))["relay"] is False
    await grant(titular, "insights")
    await crowd(api, fake, titular)
    await run_as("insights", key="morning:2026-10-21", wait_for_room=True)(api)

    assert await claude_run.postponed(await next_job(), kernel) is True
    assert tokens(cli) == []


async def test_the_one_with_more_room_goes_first(api, kernel, schema, fake) -> None:
    titular, fuller, emptier = uuid4(), uuid4(), uuid4()
    await hand_over(api, titular, token=None, label="Principal")
    await hand_over(api, fuller, label="Llena")
    await hand_over(api, emptier, label="Vacía")
    await crowd(api, fake, fuller, "0.7")
    await crowd(api, fake, emptier, "0.2")
    await grant(titular, "outings")
    await run_as("outings")(api)
    job = await next_job()

    async with as_module() as database:
        choice = await claude_run.choose(database, job, job.created_at)

    assert [one.label for one in choice.usable] == ["Vacía", "Llena"]
    assert choice.passed == ["«Principal» no tiene token"]
