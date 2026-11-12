from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import kernel_url, user_headers
from insights import insights, signals, talk

MODULE = "insights"
CAPABILITY = "claude.run"
MADRID = ZoneInfo("Europe/Madrid")
MORNING_FROM, MORNING_UNTIL = 7, 21
WEEKLY_FROM = 18
WEEKLY_UNTIL_MONDAY = 12
MAX_ATTEMPTS = 3
SEEN_DAYS = 14
TOLD_DAYS = 90

Kind = Literal["morning", "weekly"]


def _week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"weekly:{year}-W{week:02d}"


def due(now: datetime) -> list[tuple[Kind, str]]:
    local = now.astimezone(MADRID)
    out: list[tuple[Kind, str]] = []
    if MORNING_FROM <= local.hour < MORNING_UNTIL:
        out.append(("morning", f"morning:{local.date().isoformat()}"))
    if local.weekday() == 6 and local.hour >= WEEKLY_FROM:
        out.append(("weekly", _week_key(local.date())))
    if local.weekday() == 0 and local.hour < WEEKLY_UNTIL_MONDAY:
        out.append(("weekly", _week_key(local.date() - timedelta(days=1))))
    return out


def attempt_key(key: str, attempt: int) -> str:
    return key if attempt <= 1 else f"{key}#{attempt}"


ASKED_AS = "'insights:' || r.key || case when r.attempt > 1 then '#' || r.attempt else '' end"

RUN = text("select outcome, attempt from insights.insights_run where key = :key")

FINISHED = text("""
    select payload->>'outcome' as outcome, payload->>'detail' as detail,
           payload->>'code' as code, payload->>'ran_with' as ran_with
    from insights.events
    where type = 'hub.run' and payload->>'key' = :key
    order by ts desc limit 1
""")

SEEN = text(f"""
    select r.signal_ids from insights.insights_run r
    where r.kind = 'morning' and r.outcome = 'queued' and r.key <> :key
      and r.asked_at > now() - make_interval(days => :days)
      and exists (
          select 1 from insights.events e
          where e.type = 'hub.run' and e.payload->>'key' = {ASKED_AS}
            and e.payload->>'outcome' = 'ok'
      )
""")

SAVE = text("""
    insert into insights.insights_run (kind, key, outcome, detail, signal_ids, attempt)
    values (:kind, :key, :outcome, :detail, cast(:ids as jsonb), :attempt)
    on conflict (user_id, key) do update
    set outcome = excluded.outcome, detail = excluded.detail, signal_ids = excluded.signal_ids,
        attempt = excluded.attempt, asked_at = now()
""")


async def finished(connection: AsyncConnection, key: str, attempt: int) -> Any:
    asked_as = f"{MODULE}:{attempt_key(key, attempt)}"
    return (await connection.execute(FINISHED, {"key": asked_as})).one_or_none()


async def next_attempt(connection: AsyncConnection, key: str) -> int | None:
    previous = (await connection.execute(RUN, {"key": key})).one_or_none()
    if previous is None:
        return 1
    if previous.outcome != "queued":
        return previous.attempt
    ended = await finished(connection, key, previous.attempt)
    if ended is None or ended.outcome == "ok" or previous.attempt >= MAX_ATTEMPTS:
        return None
    return previous.attempt + 1


async def seen(connection: AsyncConnection, key: str) -> set[str]:
    rows = await connection.execute(SEEN, {"key": key, "days": SEEN_DAYS})
    return {one for row in rows for one in (row.signal_ids or [])}


async def save(
    connection: AsyncConnection,
    kind: Kind,
    key: str,
    outcome: str,
    found: list[signals.Signal],
    detail: str | None = None,
    attempt: int = 1,
) -> None:
    await connection.execute(
        SAVE,
        {
            "kind": kind,
            "key": key,
            "outcome": outcome,
            "detail": detail[:500] if detail else None,
            "ids": json.dumps([one.id for one in found]),
            "attempt": attempt,
        },
    )


RATINGS = {"useful": "le sirvió", "known": "ya lo sabía", "not_applicable": "no le aplica"}


def _told(given: list[insights.Insight]) -> list[str]:
    if not given:
        return ["(Todavía no le has dicho nada.)"]
    return [
        f"- {one.created_at.astimezone(MADRID):%Y-%m-%d} · {one.topic} · «{one.title}» · "
        + (RATINGS[one.rating] if one.rating else "sin valorar")
        for one in given
    ]


def _signals(found: list[signals.Signal]) -> list[str]:
    return [f"- [{one.id}] {one.text}" for one in found] or ["(Ninguna.)"]


LISTON = [
    "El listón (si no lo pasa, no se publica; insights_publish_insight rechaza lo que no lo trae):",
    "1. Cita una cifra suya y su línea base (su media, su banda, su ritmo, su objetivo), no una "
    "regla general. En `figures`, la principal primero.",
    "2. Dice qué afecta: una meta suya, algo de su perfil o una consecuencia con fecha.",
    "3. Propone una acción concreta y comprobable: qué, cuánto y cuándo.",
    "4. No repite un consejo de los últimos 30 días sobre el mismo tema salvo que la cifra haya "
    "cambiado. Lo que valoró como «ya lo sabía», solo con algo que no sepa; lo que «no le aplica», "
    "no vuelvas a ello.",
]

VOICE = [
    "Cómo se escribe: en español, de tú, directo y breve, sin frases de ánimo. El cuerpo en "
    "párrafos cortos separados por una línea en blanco, sin Markdown ni encabezados: lo que ves, "
    "por qué importa y qué harías. Las cifras a la española (1.234,5). No diagnostiques: en salud, "
    "di lo que ves en sus cifras y cuándo conviene preguntar a un médico.",
    "Solo escribes en Insights, con insights_publish_insight. No uses insights_reply: aquí no hay "
    "conversación. Si un dato no está, no lo inventes.",
]


def _head(profile: insights.Profile, today: str) -> list[str]:
    lines = [
        f"Eres {profile.name}, el asesor de una persona dentro de arga, su sistema personal. Hoy "
        f"es {today}. Miras todos sus datos a la vez con las tools de lectura de arga (cifras, "
        "movimientos, entrenos, comida, metas, agenda, notas) y le escribes lo que ve que importa.",
    ]
    if profile.about.strip():
        lines += ["", "Lo que la persona te ha contado de sí misma:", profile.about.strip()]
    else:
        lines += ["", "No te ha contado nada de sí misma: aconseja con lo que digan sus datos."]
    return lines


def morning_brief(
    profile: insights.Profile,
    fresh: list[signals.Signal],
    standing: list[signals.Signal],
    given: list[insights.Insight],
    today: str,
) -> str:
    lines = [
        *_head(profile, today),
        "",
        "Esta es tu mirada de la mañana. Insights ya ha medido, sin modelo, lo que se sale de lo suyo:",
        "",
        "Señales nuevas:",
        *_signals(fresh),
        "",
        "Señales que siguen en pie y ya estaban otras mañanas (solo si cambian algo):",
        *_signals(standing),
        "",
        "Lo que le has dicho los últimos 90 días, con su valoración:",
        *_told(given),
        "",
        "Qué haces:",
        "1. Mira cada señal nueva de cerca con las tools de lectura: de dónde sale, si es un dato "
        "mal apuntado, qué la explica y qué otras cifras se mueven con ella. insights_get_series te da "
        "cualquier cifra en cualquier rango.",
        "2. Cruza: lo que más vale es lo que ninguna app ve sola.",
        "3. Publica con insights_publish_insight, kind «alert», como mucho dos consejos, solo lo que "
        "pase el listón. `topic` estable y corto (la clave de la cifra, `vitals.weight`, o "
        "`money.gasto:restaurantes`): es lo que evita repetirse.",
        "4. Si nada pasa el listón, no publiques nada. Callarse es lo normal.",
        "",
        *LISTON,
        "",
        *VOICE,
    ]
    return "\n".join(lines)


def weekly_brief(
    profile: insights.Profile,
    week: list[signals.Signal],
    given: list[insights.Insight],
    today: str,
    monday: date,
    sunday: date,
    key: str,
) -> str:
    topic = "semana:" + key.split(":", 1)[1].lower()
    lines = [
        *_head(profile, today),
        "",
        f"Toca el resumen de su semana, del lunes {monday:%d/%m} al domingo {sunday:%d/%m}.",
        "",
        "Las señales de la semana, medidas sin modelo:",
        *_signals(week),
        "",
        "Lo que le has dicho los últimos 90 días, con su valoración:",
        *_told(given),
        "",
        "Qué haces:",
        "1. Repasa la semana por ámbitos con las tools de lectura: dinero (Money, Carrera), "
        "cuerpo (Vitals, Macros, Training), tiempo y metas (Planner, KPIs, Notebook) y ocio y viajes "
        "(Library, Travel, Outings). En cada uno, lo que se movió frente a lo suyo, con cifras. "
        "Si un ámbito no tiene nada, se dice en una línea o se omite.",
        "2. Publica exactamente uno con insights_publish_insight: kind «weekly», domain «cross», "
        f"topic «{topic}», título corto que diga lo principal de la semana. En el cuerpo, un "
        "párrafo por ámbito. En `figures`, las tres a seis cifras que más importan, cada una "
        "con su línea base. En `affects`, la meta o lo de su perfil que más pesa esta semana. En "
        "`action`, la propuesta que más importa, en una frase.",
        "3. En `proposals`, de 3 a 7 propuestas para la semana que viene, la más importante "
        "primero. Cada una concreta y comprobable (`what`: qué, cuánto y cuándo), con la cifra "
        "que mueve y su línea base (`figure`), y en `how` cómo se aplica: la app y lo que haría "
        "Claude con sus tools cuando la persona se lo pida (`Planner: bloque de 45 min el martes a "
        "las 19:00`). Tú no aplicas ninguna: solo las propones. Sin propuesta de relleno: si la "
        "semana no da para más, tres.",
        "4. Este se publica siempre, aunque la semana haya sido tranquila: entonces di eso, con "
        "las cifras que lo muestran.",
        "",
        *LISTON[:4],
        "",
        *VOICE,
    ]
    return "\n".join(lines)


def timeout() -> float:
    return float(os.environ.get("HUB_TIMEOUT_SECONDS", "30"))


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def ask(key: str, prompt: str, tools: tuple[str, ...] = ()) -> dict[str, Any]:
    body: dict[str, Any] = {"key": key, "prompt": prompt, "wait_for_room": True}
    if tools:
        body["tools"] = list(tools)
    try:
        async with httpx.AsyncClient(transport=transport()) as client:
            response = await client.post(
                f"{kernel_url()}/internal/capabilities/{CAPABILITY}",
                json=body,
                headers={**user_headers(), "x-arga-module": MODULE},
                timeout=timeout(),
            )
    except httpx.HTTPError as error:
        return {"outcome": "error", "detail": f"Hub no contesta ({type(error).__name__})"}
    if response.status_code != 200:
        return {"outcome": "error", "detail": f"Hub contesta {response.status_code}"}
    return response.json()


def refused_detail(answer: dict[str, Any]) -> str | None:
    if answer.get("outcome") in ("queued", "running") or answer.get("repeated"):
        return None
    if answer.get("code") == "not_granted":
        return (
            "Insights no tiene permiso para usar tu Claude. Dáselo en Hub, en la ficha de tu "
            "cuenta de Claude: «Tu Claude en arga» → Insights."
        )
    return str(answer.get("detail") or "Hub no ha apuntado la pasada.")


def week_of(key: str) -> tuple[date, date]:
    year, week = key.split(":", 1)[1].split("-W")
    monday = date.fromisocalendar(int(year), int(week), 1)
    return monday, monday + timedelta(days=6)


async def run(connection: AsyncConnection, kind: Kind, key: str, now: datetime) -> str | None:
    attempt = await next_attempt(connection, key)
    if attempt is None:
        return None
    local = now.astimezone(MADRID)
    today = local.date()
    profile = await insights.profile(connection)
    given = await insights.recent(connection, limit=60, since=now - timedelta(days=TOLD_DAYS))
    said_today = talk.spanish_day(local)
    if kind == "morning":
        found = await signals.read(connection, today - timedelta(days=1), today)
        before = await seen(connection, key)
        fresh = [one for one in found if one.id not in before]
        if not fresh:
            await save(connection, kind, key, "quiet", found, attempt=attempt)
            return "quiet"
        standing = [one for one in found if one.id in before]
        prompt = morning_brief(profile, fresh, standing, given, said_today)
    else:
        monday, sunday = week_of(key)
        found = await signals.read(connection, monday, min(sunday, today))
        prompt = weekly_brief(profile, found, given, said_today, monday, sunday, key)
    answer = await ask(attempt_key(key, attempt), prompt)
    problem = refused_detail(answer)
    if problem:
        await save(connection, kind, key, "refused", found, problem, attempt=attempt)
        return "refused"
    await save(connection, kind, key, "queued", found, attempt=attempt)
    return "queued"


LAST_RUNS = text("""
    select distinct on (kind) kind, key, outcome, detail, attempt,
           jsonb_array_length(signal_ids) as signals, asked_at
    from insights.insights_run
    order by kind, asked_at desc
""")

RECENT_RUNS = text("""
    select kind, key, outcome, detail, attempt, jsonb_array_length(signal_ids) as signals, asked_at
    from insights.insights_run
    where asked_at > now() - make_interval(days => :days)
    order by asked_at desc
""")

FIXES = {
    "no_room": "Tus cuentas de Claude van sin hueco: se vuelve a pedir sola.",
    "no_account": "Ninguna cuenta de Claude puede ahora: mira tus cuentas en Hub.",
    "not_granted": "Dale permiso a Insights en Hub, en «Tu Claude en arga».",
    "rate_limited": "Tu cuenta se quedó sin uso a mitad: se vuelve a pedir sola.",
}


class LastRun(BaseModel):
    kind: Kind
    key: str
    asked_at: datetime
    signals: int
    state: str
    detail: str | None
    attempt: int = 1
    ran_with: str | None = None
    fix: str | None = None


async def _told_run(connection: AsyncConnection, row: Any) -> LastRun:
    state, detail, ran_with, fix = row.outcome, row.detail, None, None
    if row.outcome == "queued":
        done = await finished(connection, row.key, row.attempt)
        state = done.outcome if done else "waiting"
        detail = done.detail if done else None
        ran_with = done.ran_with if done else None
        if done and done.outcome != "ok":
            fix = FIXES.get(done.code or done.outcome)
            if fix is None:
                fix = (
                    f"Se vuelve a pedir sola (intento {row.attempt} de {MAX_ATTEMPTS})."
                    if row.attempt < MAX_ATTEMPTS
                    else "Ya se intentó tres veces: la siguiente toca mañana."
                )
    elif row.outcome == "refused":
        fix = FIXES["not_granted"] if "permiso" in (row.detail or "") else None
    return LastRun(
        kind=row.kind,
        key=row.key,
        asked_at=row.asked_at,
        signals=row.signals,
        state=state,
        detail=detail,
        attempt=row.attempt,
        ran_with=ran_with,
        fix=fix,
    )


async def last(connection: AsyncConnection) -> list[LastRun]:
    return [await _told_run(connection, row) for row in await connection.execute(LAST_RUNS)]


async def recent(connection: AsyncConnection, days: int = 14) -> list[LastRun]:
    rows = (await connection.execute(RECENT_RUNS, {"days": days})).all()
    return [await _told_run(connection, row) for row in rows]
