from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from hub.declare import Provider, Secret, Sync
from hub.providers import Fetched

PING = "ai.claude.ping"
USAGE = "ai.claude.usage"
LEGACY_SOURCE = "pings"
TOKEN = "token"

IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."
OFFLINE = "Sin conexión con Anthropic"
MISSING = "Falta tu token de Claude Code"

USAGE_EVERY = timedelta(minutes=5)
USAGE_MARGIN = timedelta(minutes=2)
TOO_MANY_REQUESTS = 429


def api_url() -> str:
    return os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com").rstrip("/")


def ping_model() -> str:
    return os.environ.get("PING_MODEL", "claude-haiku-4-5")


def ping_timeout_seconds() -> float:
    return float(os.environ.get("PING_TIMEOUT_SECONDS", "60"))


def output_excerpt_chars() -> int:
    return int(os.environ.get("OUTPUT_EXCERPT_CHARS", "2000"))


def normalise(raw: str) -> str:
    token = raw.strip()
    if not token or any(character.isspace() for character in token):
        raise ValueError("no parece un token: pégalo tal cual, sin espacios")
    return token


@dataclass(frozen=True)
class Result:
    success: bool
    status_code: int | None
    duration_ms: int
    output: str
    window_resets_at: datetime | None = None
    window_utilization: float | None = None
    week_resets_at: datetime | None = None
    week_utilization: float | None = None

    @property
    def rate_limited(self) -> bool:
        return self.status_code == TOO_MANY_REQUESTS

    @property
    def first_line(self) -> str:
        lines = self.output.strip().splitlines()
        return lines[0][:200] if lines else ""


def redact(text: str, token: str) -> str:
    return text.replace(token, "***") if len(token) >= 8 else text


def excerpt(text: str, limit: int | None = None) -> str:
    limit = output_excerpt_chars() if limit is None else limit
    text = text.strip() or "(sin salida)"
    if len(text) > limit:
        text = f"{text[:limit]}\n… (recortado, {len(text)} caracteres en total)"
    return text


def limit_from(headers: Mapping[str, str], claim: str) -> tuple[datetime | None, float | None]:
    resets_at = utilization = None
    try:
        reset = headers.get(f"anthropic-ratelimit-unified-{claim}-reset")
        if reset:
            resets_at = datetime.fromtimestamp(float(reset), UTC)
    except (ValueError, OverflowError, OSError):
        resets_at = None
    try:
        used = headers.get(f"anthropic-ratelimit-unified-{claim}-utilization")
        if used:
            utilization = min(max(round(float(used) * 100, 1), 0.0), 100.0)
    except ValueError:
        utilization = None
    return resets_at, utilization


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if response.is_success:
        text = "".join(
            part.get("text", "") for part in body.get("content", []) if isinstance(part, dict)
        )
        return f"{text} · {body.get('model', '')}".strip(" ·")
    error = body.get("error") if isinstance(body, dict) else None
    return error.get("message", response.text) if isinstance(error, dict) else response.text


async def message(client: httpx.AsyncClient, token: str) -> Result:
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    if not token:
        return Result(False, None, elapsed(), MISSING)
    try:
        response = await client.post(
            f"{api_url()}/v1/messages",
            timeout=ping_timeout_seconds(),
            headers={
                "authorization": f"Bearer {token}",
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "oauth-2025-04-20",
            },
            json={
                "model": ping_model(),
                "max_tokens": 1,
                "system": [{"type": "text", "text": IDENTITY}],
                "messages": [{"role": "user", "content": "ok"}],
            },
        )
    except httpx.TimeoutException:
        return Result(
            False, None, elapsed(), f"Anthropic no contestó en {ping_timeout_seconds():g} s"
        )
    except httpx.HTTPError as error:
        return Result(
            False, None, elapsed(), redact(f"{OFFLINE}\n{type(error).__name__}: {error}", token)
        )

    resets_at, utilization = limit_from(response.headers, "5h")
    week_resets_at, week_utilization = limit_from(response.headers, "7d")
    said = redact(_message(response), token)
    output = (
        excerpt(said)
        if response.is_success
        else excerpt(f"Anthropic contesta {response.status_code}\n{said}")
    )
    return Result(
        response.is_success,
        response.status_code,
        elapsed(),
        output,
        resets_at,
        utilization,
        week_resets_at,
        week_utilization,
    )


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _limits(result: Result) -> dict[str, Any]:
    return {
        "window_resets_at": _iso(result.window_resets_at),
        "window_utilization": result.window_utilization,
        "week_resets_at": _iso(result.week_resets_at),
        "week_utilization": result.week_utilization,
    }


def ping_event(
    key: str,
    trigger: str,
    account: str,
    request_id: str | None,
    started_at: datetime,
    result: Result,
) -> dict[str, Any]:
    return {
        "ts": started_at.isoformat(),
        "type": PING,
        "payload": {
            "key": key,
            "trigger": trigger,
            "account_id": account,
            "request_id": request_id,
            "success": result.success,
            "status_code": result.status_code,
            "duration_ms": result.duration_ms,
            "output": result.output,
            **_limits(result),
        },
        "dedup_hash": f"{LEGACY_SOURCE}:{key}",
    }


def usage_event(account: str, started_at: datetime, result: Result) -> dict[str, Any]:
    key = f"usage:{account}:{started_at:%Y-%m-%dT%H:%M}"
    return {
        "ts": started_at.isoformat(),
        "type": USAGE,
        "payload": {
            "key": key,
            "account_id": account,
            "success": result.success,
            "status_code": result.status_code,
            "detail": "" if result.success else result.first_line,
            **_limits(result),
        },
        "dedup_hash": f"{LEGACY_SOURCE}:{key}",
    }


def usage_due(observed_at: datetime | None, payload: dict[str, Any] | None, now: datetime) -> bool:
    if observed_at is None or not payload or not payload.get("success"):
        return False
    raw = payload.get("window_resets_at")
    if not raw:
        return False
    resets_at = datetime.fromisoformat(raw)
    if resets_at - now <= USAGE_MARGIN:
        return False
    return now - observed_at >= USAGE_EVERY


async def read_usage(
    client: httpx.AsyncClient, secrets: dict[str, str], connection: Any
) -> Fetched:
    started_at = datetime.now(UTC)
    result = await message(client, secrets.get(TOKEN, ""))
    event = usage_event(str(connection.id), started_at, result)
    if result.success:
        return Fetched([event])
    return Fetched([event], problem=result.first_line, rate_limited=result.rate_limited)


SOURCES = (
    Provider(
        id="claude",
        name="Claude",
        category="ai",
        description="Una cuenta de Claude: lanza el ping que abre su ventana de cinco horas, a "
        "las horas que le pongas en Chuping, y lee cuánto llevas gastado. Añade una por cada "
        "cuenta que tengas.",
        capabilities=("action", "sync"),
        serves=("claude.ping", "claude.handoff", "claude.run"),
        secrets=(
            Secret(
                "token",
                "Token de Claude Code",
                "Lo generas con `claude setup-token` en tu ordenador. Solo se usa para abrir tu "
                "ventana y leer cuánto llevas.",
            ),
        ),
        emits=("ai.claude.ping", "ai.claude.usage"),
        available=True,
        schedule="* * * * *",
        unique_label=True,
        by_hand=False,
        sync=Sync("usage", read_usage, policy="open_window"),
        normalise=lambda _key, raw: normalise(raw),
    ),
)
