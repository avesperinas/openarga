from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from arga_contracts.ai import RunRequest, RunResponse
from arga_tenancy import as_user, format_spaces, kernel_url
from hub.ai import ledger, settings
from hub.ai.providers import Fake, Provider, ProviderError, ToolResult, Usage
from hub.ai.tools import Toolbox, Web
from hub.connections import Refused
from hub.db import as_module

SYSTEM = (
    "You work inside OpenArga, a person's self-hosted personal system, on behalf of the app "
    "'{app}'. Your only way to read or change anything is the tools you are given: they read "
    "every app of this person and write only to '{app}'. Do what the task asks, call tools when "
    "you need data, never invent data a tool did not return, and finish with a short summary of "
    "what you did."
)
STALE_MINUTES = 60

EXISTING = text("""
    select id, status, summary, provider, model from hub.ai_attempt
    where capability = 'run' and app = :app and run_key = :key
      and status in ('queued', 'running', 'done')
""")

ENQUEUE = text("""
    insert into hub.ai_attempt (app, capability, role, provider, model, run_key, status, task,
                                web, max_steps)
    values (:app, 'run', :role, :provider, :model, :key, :status, :task, :web, :max_steps)
    returning id
""")

QUEUED = text("""
    select id, app, role, task, web, max_steps from hub.ai_attempt
    where status = 'queued' order by started_at limit 5
""")

TAKE = text("""
    update hub.ai_attempt set status = 'running'
    where id = :id and status = 'queued' returning id
""")

FORGOTTEN = text(f"""
    update hub.ai_attempt
    set status = 'failed', detail = 'interrupted: the worker stopped during the run',
        finished_at = now()
    where status = 'running' and started_at < now() - interval '{STALE_MINUTES} minutes'
""")


async def enqueue(module: str, body: dict) -> dict:
    request = RunRequest.model_validate(body)
    async with as_module() as connection:
        found = await settings.effective(connection)
        try:
            model = found.model(request.role)
        except settings.Unavailable as error:
            raise Refused(str(error), 503) from error
        before = (await connection.execute(EXISTING, {"app": module, "key": request.key})).first()
        if before is not None:
            return RunResponse(
                status="repeated",
                run_id=str(before.id),
                summary=before.summary,
                provider=before.provider,
                model=before.model,
            ).model_dump()
        over = await ledger.left(connection, found.monthly_tokens) == 0
        instant = found.provider == "fake" and not over
        try:
            async with connection.begin_nested():
                attempt = await connection.scalar(
                    ENQUEUE,
                    {
                        "app": module,
                        "role": request.role,
                        "provider": found.provider,
                        "model": model,
                        "key": request.key,
                        "status": "over_budget" if over else "done" if instant else "queued",
                        "task": request.task,
                        "web": request.web,
                        "max_steps": request.max_steps,
                    },
                )
        except IntegrityError:
            return RunResponse(status="repeated", provider=found.provider, model=model).model_dump()
    if over:
        raise Refused("this month's AI budget is spent", 429)
    if instant:
        # The fake provider touches nothing, so there is nothing to wait for.
        turn = await Fake().conversation(model, request.role, "", request.task, []).step()
        async with as_module() as connection:
            await ledger.close_attempt(connection, attempt, "done", Usage(), summary=turn.text)
        return RunResponse(
            status="done", run_id=str(attempt), summary=turn.text, provider="fake", model=model
        ).model_dump()
    return RunResponse(
        status="queued", run_id=str(attempt), provider=found.provider, model=model
    ).model_dump()


async def execute(
    attempt,
    provider: Provider,
    toolbox: Toolbox,
    model: str,
    monthly: int | None,
) -> tuple[str, int, Usage, str | None, str | None]:
    async with as_module() as connection:
        budget = await ledger.left(connection, monthly)
    usage = Usage()
    tools = await toolbox.specs()
    conversation = provider.conversation(
        model, attempt.role, SYSTEM.format(app=attempt.app), attempt.task, tools
    )
    summary = ""
    for step in range(1, attempt.max_steps + 1):
        try:
            turn = await conversation.step()
        except ProviderError as error:
            return "failed", step, usage, str(error), summary or None
        usage.add(turn.usage)
        summary = turn.text or summary
        if budget is not None and usage.total >= budget:
            return "over_budget", step, usage, "the month's AI budget ran out mid-run", summary
        if turn.stop == "refused":
            return "failed", step, usage, "the model declined the task", summary or None
        if turn.stop == "truncated":
            return "failed", step, usage, "the model's answer did not fit", summary or None
        if turn.stop == "done":
            return "done", step, usage, None, summary
        results: list[ToolResult] = list(
            await asyncio.gather(*(toolbox.call(call) for call in turn.calls))
        )
        conversation.answer(results)
    return "failed", attempt.max_steps, usage, "the task did not finish within its steps", summary


def say(line: str) -> None:
    print(f"ai · {line}", file=sys.stderr, flush=True)


async def drain(
    kernel: httpx.AsyncClient,
    modules: httpx.AsyncClient,
    web: Web | None = None,
    providers: Callable[[settings.Effective], Provider] | None = None,
) -> int:
    ran = 0
    response = await kernel.get("/internal/users", timeout=10.0)
    response.raise_for_status()
    everyone = [
        (UUID(row["id"]), tuple(UUID(space) for space in row.get("spaces") or ()))
        for row in response.json()
    ]
    for user, spaces in everyone:
        with as_user(user, spaces):
            async with as_module() as connection:
                await connection.execute(FORGOTTEN)
                waiting = (await connection.execute(QUEUED)).all()
            for attempt in waiting:
                async with as_module() as connection:
                    if await connection.scalar(TAKE, {"id": attempt.id}) is None:
                        continue
                    found = await settings.effective(connection)
                ran += 1
                await run_one(attempt, user, spaces, found, kernel, modules, web, providers)
    return ran


async def run_one(attempt, user: UUID, spaces, found, kernel, modules, web, providers) -> None:
    usage, steps, status, detail, summary = Usage(), 0, "failed", None, None
    try:
        model = found.model(attempt.role)
        provider = providers(found) if providers else settings.provider_for(found, modules)
        toolbox = Toolbox(
            attempt.app,
            str(user),
            format_spaces(spaces),
            modules,
            web if attempt.web else None,
            str(kernel.base_url) or kernel_url(),
        )
        status, steps, usage, detail, summary = await execute(
            attempt, provider, toolbox, model, found.monthly_tokens
        )
    except (settings.Unavailable, ProviderError, httpx.HTTPError) as error:
        detail = str(error) or type(error).__name__
    except Exception as error:  # noqa: BLE001 - one broken run must not stop the queue
        detail = f"{type(error).__name__}: {error}"
        say(f"{attempt.id}: {detail}")
    async with as_module() as connection:
        await ledger.close_attempt(
            connection, attempt.id, status, usage, steps=steps, detail=detail, summary=summary
        )
