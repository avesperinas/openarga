from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import secrets
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlencode
from uuid import UUID

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import as_user, kernel_url, users
from hub import credentials, sync
from hub.db import as_module
from hub.providers import claude

CAPABILITY = "claude.run"
CLIENT = "claude-run"
PROVIDER = "claude"
OPERATION = "run"
GRANT_MINUTES = 15
HEARTBEAT = Path(os.environ.get("CLAUDE_RUN_HEARTBEAT", "/tmp/claude-run.alive"))


def public_url() -> str:
    return os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")


def issuer() -> str:
    return os.environ.get("OAUTH_ISSUER", f"{public_url()}/auth/realms/arga").rstrip("/")


def token_url() -> str:
    return os.environ.get(
        "OAUTH_TOKEN_URL", "http://auth:8080/auth/realms/arga/protocol/openid-connect/token"
    )


def mcp_url() -> str:
    return os.environ.get("ARGA_MCP_URL", "http://gateway:8000/mcp")


def client_secret() -> str:
    return os.environ.get("CLAUDE_RUN_CLIENT_SECRET", "")


def redirect_uri() -> str:
    return f"{public_url()}/api/hub/claude-run/callback"


def grant_key(app: str) -> str:
    return f"run_{app}"


def claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN", "claude")


def run_minutes() -> float:
    return float(os.environ.get("CLAUDE_RUN_MINUTES", "20"))


class Refused(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class App:
    id: str
    name: str


def runners(modules: list[dict[str, Any]]) -> list[App]:
    return [
        App(module["id"], module["name"])
        for module in modules
        if CAPABILITY in (module.get("uses") or [])
    ]


def scopes_for(app: str, modules: list[dict[str, Any]]) -> list[str]:
    reads = sorted(f"{module['id']}:read" for module in modules)
    return ["openid", "offline_access", *reads, f"{app}:write"]


CLAUDE_ACCOUNT = text("""
    select id, label, paused from hub.hub_connection
    where id = :id and provider = 'claude'
""")

REMEMBER = text("""
    insert into hub.hub_claude_grant_request (state, connection_id, app, verifier)
    values (:state, :connection, :app, :verifier)
""")

TAKE = text("""
    delete from hub.hub_claude_grant_request
    where state = :state and created_at > now() - make_interval(mins => :minutes)
    returning connection_id, app, verifier
""")


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def authorize(
    database: AsyncConnection, connection_id: UUID, app: str, modules: list[dict[str, Any]]
) -> str:
    if not client_secret():
        raise Refused("arga todavía no tiene el cliente de Keycloak para esto", 503)
    if app not in {one.id for one in runners(modules)}:
        raise Refused(f"«{app}» no pide usar tu Claude", 404)
    if (await database.execute(CLAUDE_ACCOUNT, {"id": connection_id})).one_or_none() is None:
        raise Refused("esa cuenta de Claude no está en Hub", 404)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    await database.execute(
        REMEMBER, {"state": state, "connection": connection_id, "app": app, "verifier": verifier}
    )
    query = {
        "client_id": CLIENT,
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "scope": " ".join(scopes_for(app, modules)),
        "state": state,
        "code_challenge": challenge(verifier),
        "code_challenge_method": "S256",
    }
    return f"{issuer()}/protocol/openid-connect/auth?{urlencode(query)}"


FORMER = text("""
    select connection_id from hub.hub_credential
    where key = :key and connection_id <> :connection
""")

DROP = text("""
    delete from hub.hub_credential where key = :key and connection_id = :connection
""")


async def finish_grant(
    database: AsyncConnection, auth: httpx.AsyncClient, code: str, state: str
) -> tuple[str, UUID]:
    pending = (
        await database.execute(TAKE, {"state": state, "minutes": GRANT_MINUTES})
    ).one_or_none()
    if pending is None:
        raise Refused("esa autorización no es de aquí o ha caducado: vuelve a empezar", 400)
    response = await auth.post(
        token_url(),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "client_id": CLIENT,
            "client_secret": client_secret(),
            "code_verifier": pending.verifier,
        },
    )
    if response.status_code != 200:
        raise Refused(f"Keycloak no dio el permiso ({response.status_code})", 502)
    granted = response.json()
    scopes = set(str(granted.get("scope", "")).split())
    if "offline_access" not in scopes or f"{pending.app}:write" not in scopes:
        raise Refused("Keycloak dio un permiso sin lo que hace falta para trabajar solo", 502)
    key = grant_key(pending.app)
    for former in (
        await database.execute(FORMER, {"key": key, "connection": pending.connection_id})
    ).scalars():
        await database.execute(DROP, {"key": key, "connection": former})
    await credentials.store(
        database, PROVIDER, pending.connection_id, key, granted["refresh_token"]
    )
    return pending.app, pending.connection_id


class Grant(BaseModel):
    app: str
    connection: UUID
    label: str
    since: datetime


GRANTS = text("""
    select k.key, k.created_at, c.id as connection, c.label
    from hub.hub_credential k
    join hub.hub_connection c on c.id = k.connection_id
    where c.provider = 'claude' and k.key like 'run\\_%'
    order by k.key
""")


async def grants(database: AsyncConnection) -> list[Grant]:
    return [
        Grant(
            app=row.key.removeprefix("run_"),
            connection=row.connection,
            label=row.label,
            since=row.created_at,
        )
        for row in await database.execute(GRANTS)
    ]


async def revoke(database: AsyncConnection, auth: httpx.AsyncClient, app: str) -> bool:
    found = [one for one in await grants(database) if one.app == app]
    if not found:
        return False
    for grant in found:
        token = await credentials.use(database, PROVIDER, grant.connection, grant_key(app))
        if token and client_secret():
            with contextlib.suppress(httpx.HTTPError):
                await auth.post(
                    token_url().replace("/token", "/revoke"),
                    data={
                        "token": token,
                        "token_type_hint": "refresh_token",
                        "client_id": CLIENT,
                        "client_secret": client_secret(),
                    },
                )
        await database.execute(DROP, {"key": grant_key(app), "connection": grant.connection})
    return True


class RunIn(BaseModel):
    key: Annotated[str, Field(min_length=1, max_length=200)]
    prompt: Annotated[str, Field(min_length=1, max_length=40000)]
    tools: list[Literal["WebSearch", "WebFetch"]] = Field(default_factory=list)
    wait_for_room: bool = False


GRANTED = text("""
    select c.id, c.provider, c.label, c.paused
    from hub.hub_credential k
    join hub.hub_connection c on c.id = k.connection_id
    where c.provider = 'claude' and k.key = :key
    limit 1
""")

PREVIOUS = text("""
    select outcome, detail from hub.hub_run
    where connection_id = :connection and idempotency_key = :key
""")

QUEUE = text("""
    insert into hub.hub_claude_job
        (run_id, connection_id, app, prompt, tools, wait_for_room)
    values (:run, :connection, :app, :prompt, :tools, :wait)
""")


async def request(module: str, body: dict[str, Any]) -> dict[str, Any]:
    asked = RunIn.model_validate(body)
    async with as_module() as database:
        account = (await database.execute(GRANTED, {"key": grant_key(module)})).one_or_none()
        if account is None:
            return {
                "outcome": "skipped",
                "code": "not_granted",
                "detail": "Esta app no tiene permiso para usar tu Claude: dáselo en Hub.",
            }
        if account.paused:
            return {"outcome": "skipped", "code": "paused", "detail": "La cuenta está en pausa."}
        key = f"{module}:{asked.key}"
        run_id = await sync.start(database, account.id, "action", OPERATION, key)
        if run_id is None:
            previous = (
                await database.execute(PREVIOUS, {"connection": account.id, "key": key})
            ).one()
            return {"outcome": previous.outcome, "detail": previous.detail, "repeated": True}
        await database.execute(
            QUEUE,
            {
                "run": run_id,
                "connection": account.id,
                "app": module,
                "prompt": asked.prompt,
                "tools": list(asked.tools),
                "wait": asked.wait_for_room,
            },
        )
    return {"outcome": "queued", "run": str(run_id), "repeated": False}


NEXT = text("""
    update hub.hub_claude_job j set status = 'running', started_at = now()
    from hub.hub_run r
    where j.id = (
        select id from hub.hub_claude_job
        where status = 'queued' and (not_before is null or not_before <= now())
        order by created_at limit 1 for update skip locked
    ) and r.id = j.run_id
    returning j.id, j.run_id, j.connection_id, j.app, j.prompt, j.tools, j.wait_for_room,
              j.created_at, r.idempotency_key as key
""")

LATER = text("""
    update hub.hub_claude_job
    set status = 'queued', started_at = null, not_before = now() + make_interval(mins => :minutes)
    where id = :id
""")

ROOM_PERCENT = 100.0
WAIT_MINUTES = 15
GIVE_UP = timedelta(hours=18)


FULL_PERCENT = 100.0


def _open(payload: dict[str, Any], used: str, resets: str, now: datetime) -> float | None:
    value, until = payload.get(used), payload.get(resets)
    if value is None or not until:
        return None
    try:
        closes = datetime.fromisoformat(until)
    except ValueError:
        return None
    return float(value) if closes > now else None


def crowded(
    payload: dict[str, Any] | None, now: datetime, limit: float = ROOM_PERCENT
) -> str | None:
    if not payload:
        return None
    for name, used, resets in (
        ("la ventana de cinco horas", "window_utilization", "window_resets_at"),
        ("la semana", "week_utilization", "week_resets_at"),
    ):
        value = _open(payload, used, resets, now)
        if value is not None and value >= limit:
            return f"{name} va al {value:g} %"
    return None


def used(payload: dict[str, Any] | None, now: datetime) -> float:
    if not payload:
        return 0.0
    values = [
        _open(payload, "window_utilization", "window_resets_at", now),
        _open(payload, "week_utilization", "week_resets_at", now),
    ]
    return max((value for value in values if value is not None), default=0.0)


ACCOUNTS = text("""
    select id, label, paused, coalesce((config->>'relay')::boolean, true) as relay
    from hub.hub_connection
    where provider = 'claude' and status = 'active'
    order by created_at
""")

LAST_ROOM = text("""
    select payload from hub.events
    where type in ('ai.claude.ping', 'ai.claude.usage') and payload->>'account_id' = :account
      and coalesce(payload->>'window_utilization', payload->>'week_utilization') is not null
    order by ts desc
    limit 1
""")

LAST_PING = text("""
    select payload->>'success' as success, payload->>'status_code' as status
    from hub.events
    where type = 'ai.claude.ping' and payload->>'account_id' = :account
    order by ts desc
    limit 1
""")

REJECTED = frozenset({"401", "403"})


@dataclass
class Account:
    id: UUID
    label: str
    titular: bool
    used: float


@dataclass
class Choice:
    usable: list[Account]
    passed: list[str]
    wait: bool


async def choose(database: AsyncConnection, job: Any, now: datetime) -> Choice:
    limit = ROOM_PERCENT if getattr(job, "wait_for_room", False) else FULL_PERCENT
    rows = sorted(
        (await database.execute(ACCOUNTS)).all(), key=lambda row: row.id != job.connection_id
    )
    usable: list[Account] = []
    passed: list[str] = []
    waits = False
    for row in rows:
        titular = row.id == job.connection_id
        if not titular and not row.relay:
            continue
        name = f"«{row.label}»"
        if row.paused:
            passed.append(f"{name} está en pausa")
            continue
        token = (await credentials.status(database, row.id, (claude.TOKEN,)))[0]
        if not token.configured:
            passed.append(f"{name} no tiene token")
            continue
        ping = (await database.execute(LAST_PING, {"account": str(row.id)})).one_or_none()
        if ping and ping.success == "false" and ping.status in REJECTED:
            passed.append(f"{name} tiene el token rechazado ({ping.status})")
            continue
        seen = (await database.execute(LAST_ROOM, {"account": str(row.id)})).one_or_none()
        payload = seen.payload if seen else None
        why = crowded(payload, now, limit)
        if why:
            passed.append(f"{name}: {why}")
            waits = True
            continue
        usable.append(Account(row.id, row.label, titular, used(payload, now)))
    first = [one for one in usable if one.titular]
    rest = sorted((one for one in usable if not one.titular), key=lambda one: one.used)
    return Choice(first + rest, passed, wait=not usable and waits)


CUT = text("""
    update hub.hub_claude_job j set status = 'done', finished_at = now()
    from hub.hub_run r
    where j.status = 'running' and r.id = j.run_id
    returning j.id, j.run_id, j.connection_id, j.app, r.idempotency_key as key
""")

DONE = text("""
    update hub.hub_claude_job set status = 'done', finished_at = now()
    where id = :id
""")

ACCOUNT = text("""
    select id, provider, label, paused from hub.hub_connection where id = :id
""")


@dataclass
class Said:
    ok: bool
    detail: str
    rate_limited: bool = False
    rejected: bool = False


def command(job: Any, config: Path) -> list[str]:
    tools = ",".join(job.tools)
    allowed = ["mcp__arga", *job.tools]
    line = [
        claude_bin(),
        "-p",
        job.prompt,
        "--output-format",
        "json",
        "--restricted",
        "--tools",
        tools,
        "--strict-mcp-config",
        "--mcp-config",
        str(config),
        "--allowedTools",
        ",".join(allowed),
        "--no-session-persistence",
        "--disable-slash-commands",
    ]
    model = os.environ.get("CLAUDE_RUN_MODEL", "").strip()
    if model:
        line += ["--model", model]
    return line


def model_of(result: dict[str, Any]) -> str | None:
    usage = result.get("modelUsage")
    if not isinstance(usage, dict) or not usage:
        return None
    return str(max(usage, key=lambda model: (usage[model] or {}).get("outputTokens") or 0))


def understood(code: int, out: str, err: str) -> Said:
    try:
        result = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except (json.JSONDecodeError, IndexError):
        result = {}
    said = str(result.get("result") or err or out or "sin respuesta").strip()
    first = said.splitlines()[0][:500] if said else ""
    lowered = said.lower()
    limited = "limit" in lowered and ("reset" in lowered or "usage" in lowered)
    rejected = any(
        sign in lowered
        for sign in (
            "invalid api key",
            "oauth token",
            "authentication_error",
            "authentication failed",
            "please run /login",
            "401",
        )
    )
    if code == 0 and not result.get("is_error", False):
        turns = result.get("num_turns")
        model = model_of(result)
        done = f"Hecho en {turns} turnos" if turns else "Hecho"
        if model:
            done += f" con {model}"
        return Said(True, f"{done}. {first}" if turns or model else first)
    return Said(False, first or f"el CLI acabó con {code}", rate_limited=limited, rejected=rejected)


async def access_token(auth: httpx.AsyncClient, refresh: str) -> tuple[str, str | None]:
    response = await auth.post(
        token_url(),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": CLIENT,
            "client_secret": client_secret(),
        },
    )
    if response.status_code != 200:
        raise Refused(f"Keycloak no renovó el permiso ({response.status_code}): vuelve a darlo")
    body = response.json()
    rotated = body.get("refresh_token")
    return body["access_token"], rotated if rotated and rotated != refresh else None


async def launch(job: Any, token: str, access: str) -> Said:
    with tempfile.TemporaryDirectory(prefix="claude-run-") as home:
        config = Path(home) / "mcp.json"
        config.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "arga": {
                            "type": "http",
                            "url": mcp_url(),
                            "headers": {"Authorization": f"Bearer {access}"},
                        }
                    }
                }
            )
        )
        environment = {
            "HOME": home,
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "CLAUDE_CODE_OAUTH_TOKEN": token,
            "DISABLE_AUTOUPDATER": "1",
        }
        process = await asyncio.create_subprocess_exec(
            *command(job, config),
            cwd=home,
            env=environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=run_minutes() * 60)
        except TimeoutError:
            process.kill()
            await process.wait()
            return Said(False, f"Cortada a los {run_minutes():g} minutos.")
    return understood(
        process.returncode or 0,
        out.decode(errors="replace"),
        claude.redact(err.decode(errors="replace"), token),
    )


RAN_ON = text("update hub.hub_claude_job set ran_on = :account where id = :id")


def _hops(passed: list[str]) -> str:
    return "; ".join(passed)


async def work(job: Any, auth: httpx.AsyncClient, kernel: httpx.AsyncClient) -> sync.Outcome:
    result = sync.Outcome(job.run_id, "ok", key=job.key)
    now = datetime.now(UTC)
    async with as_module() as database:
        account = (await database.execute(ACCOUNT, {"id": job.connection_id})).one()
        refresh = await credentials.use(database, PROVIDER, job.connection_id, grant_key(job.app))
        choice = await choose(database, job, now)
    if refresh is None:
        result.outcome, result.code = "skipped", "not_granted"
        result.detail = "Se quitó el permiso de la app antes de la pasada."
    elif not choice.usable:
        result.outcome, result.code = "skipped", "no_account"
        result.detail = f"Ninguna cuenta de Claude puede hacerla: {_hops(choice.passed)}."
    else:
        await _run_with(job, auth, refresh, choice, result)
    async with as_module() as database:
        await database.execute(DONE, {"id": job.id})
        if result.ran_on:
            await database.execute(RAN_ON, {"id": job.id, "account": UUID(result.ran_on)})
    await sync.finish(kernel, account, PROVIDER, "action", OPERATION, result)
    return result


async def _run_with(
    job: Any, auth: httpx.AsyncClient, refresh: str, choice: Choice, result: sync.Outcome
) -> None:
    passed = list(choice.passed)
    for one in choice.usable:
        try:
            access, rotated = await access_token(auth, refresh)
            async with as_module() as database:
                if rotated:
                    await credentials.store(
                        database, PROVIDER, job.connection_id, grant_key(job.app), rotated
                    )
                    refresh = rotated
                token = await credentials.use(database, PROVIDER, one.id, claude.TOKEN)
            said = await launch(job, token or "", access)
        except (Refused, httpx.HTTPError) as error:
            result.outcome, result.detail = "error", str(error)[:500]
            return
        if not one.titular:
            result.ran_on, result.ran_with = str(one.id), one.label
        if said.ok:
            result.outcome = "ok"
            result.detail = _with(one, passed, said.detail)
            return
        result.outcome = "rate_limited" if said.rate_limited else "error"
        result.detail = _with(one, passed, said.detail)
        if not (said.rate_limited or said.rejected):
            return
        passed.append(
            f"«{one.label}» se quedó sin uso"
            if said.rate_limited
            else f"«{one.label}» rechazó el token"
        )


def _with(one: Account, passed: list[str], detail: str) -> str:
    if one.titular and not passed:
        return detail
    head = f"Con «{one.label}»" + (f" ({_hops(passed)})" if passed else "")
    return f"{head}. {detail}"


def say(line: str) -> None:
    print(f"claude-run · {line}", flush=True)


async def postponed(job: Any, kernel: httpx.AsyncClient) -> bool:
    if not getattr(job, "wait_for_room", False):
        return False
    now = datetime.now(UTC)
    async with as_module() as database:
        choice = await choose(database, job, now)
        if not choice.wait:
            return False
        why = _hops(choice.passed)
        if now - job.created_at < GIVE_UP:
            await database.execute(LATER, {"id": job.id, "minutes": WAIT_MINUTES})
            say(f"{job.app} espera: {why}")
            return True
        await database.execute(DONE, {"id": job.id})
        account = (await database.execute(ACCOUNT, {"id": job.connection_id})).one()
    result = sync.Outcome(job.run_id, "skipped", key=job.key)
    result.code = "no_room"
    result.detail = f"Sin hueco en tu uso de Claude: {why}."
    await sync.finish(kernel, account, PROVIDER, "action", OPERATION, result)
    say(f"{job.app}: saltada · {result.detail}")
    return True


async def tick(auth: httpx.AsyncClient, kernel: httpx.AsyncClient) -> int:
    done = 0
    for user in await users(kernel):
        with as_user(user):
            while True:
                HEARTBEAT.touch()  # noqa: ASYNC240 -- un fichero vacío en /tmp
                async with as_module() as database:
                    job = (await database.execute(NEXT)).one_or_none()
                if job is None:
                    break
                if await postponed(job, kernel):
                    continue
                say(f"pasada de {job.app} para {user}")
                outcome = await work(job, auth, kernel)
                say(f"{job.app}: {outcome.outcome} · {outcome.detail}")
                done += 1
    return done


async def recover(kernel: httpx.AsyncClient) -> int:
    cut = 0
    for user in await users(kernel):
        with as_user(user):
            async with as_module() as database:
                rows = (await database.execute(CUT)).all()
                accounts = {
                    row.connection_id: (
                        await database.execute(ACCOUNT, {"id": row.connection_id})
                    ).one()
                    for row in rows
                }
            for row in rows:
                result = sync.Outcome(row.run_id, "error", key=row.key)
                result.detail = "Se cortó a medias: arga se reinició mientras corría."
                await sync.finish(
                    kernel, accounts[row.connection_id], PROVIDER, "action", OPERATION, result
                )
                cut += 1
    return cut


async def serve() -> None:
    async with (
        httpx.AsyncClient(timeout=30.0) as auth,
        httpx.AsyncClient(base_url=kernel_url(), timeout=30.0) as kernel,
    ):
        say(f"listo: {claude_bin()}, MCP en {mcp_url()}")
        try:
            if cut := await recover(kernel):
                say(f"{cut} pasada(s) cortadas por el reinicio, dadas por fallidas")
        except (httpx.HTTPError, OSError) as error:
            say(f"sin recuperar lo cortado: {type(error).__name__}")
        while True:
            HEARTBEAT.touch()  # noqa: ASYNC240 -- un fichero vacío en /tmp
            try:
                await tick(auth, kernel)
            except (httpx.HTTPError, OSError) as error:
                say(f"sin pasada: {type(error).__name__}: {error}")
            await asyncio.sleep(float(os.environ.get("CLAUDE_RUN_POLL_SECONDS", "3")))


def main() -> int:
    try:
        credentials.masters()
    except Exception as error:  # noqa: BLE001 - se dice y se sale con código distinto de cero
        print(f"claude-run: {error}", file=sys.stderr)
        return 1
    if not client_secret():
        print("claude-run: falta CLAUDE_RUN_CLIENT_SECRET", file=sys.stderr)
        return 1
    asyncio.run(serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
