from __future__ import annotations

import os
from datetime import datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import kernel_url, user_headers
from insights import insights

MODULE = "insights"
CAPABILITY = "claude.run"
HISTORY = 30


class NotFound(Exception):
    pass


class Message(BaseModel):
    id: str
    author: Literal["person", "insights"]
    body: str
    created_at: datetime


class Thread(BaseModel):
    id: str
    title: str
    insight_id: str | None
    waiting_since: datetime | None
    problem: str | None
    created_at: datetime
    updated_at: datetime


class ThreadOut(Thread):
    messages: list[Message]


class Say(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class Start(Say):
    insight_id: str | None = None


THREAD = (
    "id::text as id, title, insight_id::text as insight_id, waiting_since, problem, "
    "created_at, updated_at"
)


async def threads(connection: AsyncConnection, limit: int = 50) -> list[Thread]:
    rows = await connection.execute(
        text(
            f"select {THREAD} from insights.insights_thread order by updated_at desc limit :limit"
        ),
        {"limit": limit},
    )
    return [Thread.model_validate(dict(row._mapping)) for row in rows]


async def thread(connection: AsyncConnection, thread_id: str) -> ThreadOut:
    row = (
        await connection.execute(
            text(f"select {THREAD} from insights.insights_thread where id = cast(:id as uuid)"),
            {"id": thread_id},
        )
    ).one_or_none()
    if row is None:
        raise NotFound(thread_id)
    messages = await connection.execute(
        text("""
            select id::text as id, author, body, created_at from insights.insights_message
            where thread_id = cast(:id as uuid) order by created_at
        """),
        {"id": thread_id},
    )
    return ThreadOut(
        **dict(row._mapping),
        messages=[Message.model_validate(dict(one._mapping)) for one in messages],
    )


def title_of(text_: str) -> str:
    line = " ".join(text_.split())
    return line if len(line) <= 80 else line[:79].rstrip() + "…"


async def start(connection: AsyncConnection, wanted: Start) -> str:
    title = title_of(wanted.text)
    if wanted.insight_id:
        title = (await insights.one(connection, wanted.insight_id)).title
    thread_id = await connection.scalar(
        text("""
            insert into insights.insights_thread (title, insight_id)
            values (:title, cast(:insight as uuid)) returning id::text
        """),
        {"title": title, "insight": wanted.insight_id},
    )
    await add(connection, thread_id, "person", wanted.text)
    return thread_id


async def add(connection: AsyncConnection, thread_id: str, author: str, body: str) -> str:
    exists = await connection.scalar(
        text("select 1 from insights.insights_thread where id = cast(:thread as uuid)"),
        {"thread": thread_id},
    )
    if not exists:
        raise NotFound(thread_id)
    message_id = await connection.scalar(
        text("""
            insert into insights.insights_message (thread_id, author, body)
            values (cast(:thread as uuid), :author, :body) returning id::text
        """),
        {"thread": thread_id, "author": author, "body": body},
    )
    await connection.execute(
        text("""
            update insights.insights_thread
            set updated_at = now(), problem = null,
                waiting_since = case when :author = 'person' then now() else null end
            where id = cast(:thread as uuid)
        """),
        {"thread": thread_id, "author": author},
    )
    return message_id


async def remove(connection: AsyncConnection, thread_id: str) -> None:
    gone = await connection.execute(
        text("delete from insights.insights_thread where id = cast(:id as uuid)"), {"id": thread_id}
    )
    if not gone.rowcount:
        raise NotFound(thread_id)


LAST_RUN = text("""
    select payload->>'outcome' as outcome, payload->>'code' as code,
           payload->>'detail' as detail
    from insights.events
    where type = 'hub.run' and payload->>'key' like :key
      and ts >= :since
    order by ts desc limit 1
""")


def problem_of(outcome: str, code: str | None, detail: str | None, answered: bool) -> str | None:
    if outcome == "ok":
        return None if answered else "Terminó sin contestar. Vuelve a preguntar."
    if outcome == "rate_limited":
        return (
            "Has llegado al límite de uso de tu Claude. Vuelve a preguntar cuando se abra la "
            "ventana siguiente."
        )
    if code == "not_granted":
        return (
            "Insights no tiene permiso para usar tu Claude. Dáselo en Hub, en la ficha de tu "
            "cuenta de Claude: «Tu Claude en arga» → Insights."
        )
    reason = (detail or "").strip()
    return f"No ha podido contestar: {reason}" if reason else "No ha podido contestar."


async def settle(connection: AsyncConnection, thread_id: str) -> None:
    conversation = await thread(connection, thread_id)
    if conversation.waiting_since is None or not conversation.messages:
        return
    asked = [one for one in conversation.messages if one.author == "person"]
    if not asked:
        return
    last = asked[-1]
    run = (
        await connection.execute(
            LAST_RUN,
            {"key": f"{MODULE}:thread:{last.id}%", "since": conversation.waiting_since},
        )
    ).one_or_none()
    if run is None:
        return
    answered = any(
        one.author == "insights" and one.created_at >= last.created_at
        for one in conversation.messages
    )
    problem = problem_of(run.outcome, run.code, run.detail, answered)
    if problem:
        await failed(connection, thread_id, problem)


async def add_waiting(connection: AsyncConnection, thread_id: str) -> None:
    await connection.execute(
        text("""
            update insights.insights_thread set waiting_since = now(), problem = null
            where id = cast(:thread as uuid)
        """),
        {"thread": thread_id},
    )


async def failed(connection: AsyncConnection, thread_id: str, problem: str) -> None:
    await connection.execute(
        text("""
            update insights.insights_thread set waiting_since = null, problem = :problem
            where id = cast(:thread as uuid)
        """),
        {"thread": thread_id, "problem": problem[:500]},
    )


def brief(
    profile: insights.Profile,
    conversation: ThreadOut,
    about: insights.Insight | None,
    today: str,
    tastes: list[str] | None = None,
) -> str:
    lines = [
        f"Eres {profile.name}, el asesor de una persona dentro de arga, su sistema personal. Hoy "
        f"es {today}. Te escribe en la app de {profile.name} y le contestas por la tool "
        f"insights_reply, con thread_id «{conversation.id}». Llámala una sola vez, al final, con tu "
        "respuesta entera. Lo que no pase por insights_reply no lo verá.",
        "",
        "Cómo contestas:",
        "- Con sus datos, no con generalidades. Antes de contestar, mira lo que haga falta con las "
        "tools de lectura de arga (cifras, movimientos, entrenos, comida, metas, notas de Notebook) y "
        "cita las cifras: lo suyo frente a su propia línea base (su media, su objetivo, su ritmo).",
        "- Directo y breve, en español, de tú. Sin relleno ni frases de ánimo. En Markdown: "
        "párrafos cortos, **negrita** para la cifra que importa, listas si enumeras y una tabla "
        "pequeña solo si compara varias cifras. Sin encabezados.",
        "- Si propones algo, que sea concreto y comprobable: qué, cuánto y cuándo.",
        "- Si un dato no está, dilo y di cómo conseguirlo; no lo inventes.",
        "- No diagnostiques: en salud, di lo que ves en sus cifras y cuándo conviene preguntar a "
        "un médico.",
        "- Solo puedes escribir en Insights. Si te pide apuntar algo en otra app, dile cómo hacerlo.",
        "- Si te dice algo de sus gustos («me encantó», «nada de fútbol»), apúntalo con "
        "insights_note_taste. Si te pide recomendaciones, publícalas con insights_publish_picks (`origin` "
        "«chat»), que las comprueba en catálogo, y cuéntale en tu respuesta las que salieron: "
        "estarán en su Biblioteca.",
    ]
    if profile.about.strip():
        lines += ["", "Lo que la persona te ha contado de sí misma:", profile.about.strip()]
    if tastes:
        lines += ["", "Lo que sabes de sus gustos:", *tastes]
    if about is not None:
        figures = "; ".join(
            f"{one.label}: {one.value:g}{' ' + one.unit if one.unit else ''} frente a "
            f"{one.baseline:g} ({one.baseline_label})"
            for one in about.figures
        )
        lines += [
            "",
            f"Esta conversación contesta a un consejo que le diste el {about.created_at:%Y-%m-%d}:",
            f"«{about.title}». {about.body}",
            f"Cifras: {figures}. Qué afecta: {about.affects}. Qué propusiste: {about.action}",
        ]
    lines += ["", "La conversación hasta ahora (lo último es lo que tienes que contestar):"]
    for message in conversation.messages[-HISTORY:]:
        who = "Persona" if message.author == "person" else profile.name
        lines.append(f"[{who}] {message.body}")
    return "\n".join(lines)


DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def spanish_day(moment: datetime) -> str:
    return f"{DAYS[moment.weekday()]} {moment.day} de {MONTHS[moment.month - 1]} de {moment.year}"


def timeout() -> float:
    return float(os.environ.get("HUB_TIMEOUT_SECONDS", "30"))


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def ask(key: str, prompt: str) -> str | None:
    try:
        async with httpx.AsyncClient(transport=transport()) as client:
            response = await client.post(
                f"{kernel_url()}/internal/capabilities/{CAPABILITY}",
                json={"key": key, "prompt": prompt},
                headers={**user_headers(), "x-arga-module": MODULE},
                timeout=timeout(),
            )
    except httpx.HTTPError as error:
        return f"Hub no contesta ({type(error).__name__}). Vuelve a intentarlo."
    if response.status_code != 200:
        return f"Hub no ha podido apuntar la pregunta ({response.status_code})."
    answer = response.json()
    if answer.get("outcome") in ("queued", "running") or answer.get("repeated"):
        return None
    if answer.get("code") == "not_granted":
        return (
            "Insights no tiene permiso para usar tu Claude. Dáselo en Hub, en la ficha de tu "
            "cuenta de Claude: «Tu Claude en arga» → Insights."
        )
    return answer.get("detail") or "Hub no ha apuntado la pregunta."
