from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from insights import insights, passes, picks, pills, talk, tastes

MADRID = ZoneInfo("Europe/Madrid")
Kind = Literal["pill", "more", "picks", "profile"]

AHEAD = timedelta(minutes=25)
PILL_UNTIL = time(22, 30)
PICKS_FROM = time(17, 0)
PROFILE_FROM = time(10, 0)
AWAKE = (time(8, 0), time(22, 30))
LANGUAGE_DAY = 5
MORE_PER_DAY = 3
MAX_ATTEMPTS = passes.MAX_ATTEMPTS
WEB = ("WebFetch", "WebSearch")

LANGUAGE_NAMES = {
    "es": "español de España",
    "en": "inglés",
    "de": "alemán",
    "fr": "francés",
    "it": "italiano",
    "eu": "euskera",
}


def _week(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def due(now: datetime, settings: tastes.Settings, profiled: bool) -> list[tuple[Kind, str]]:
    local = now.astimezone(MADRID)
    clock = local.time()
    out: list[tuple[Kind, str]] = []
    if settings.pill_on:
        hours, minutes = (int(part) for part in settings.pill_time.split(":"))
        start = (datetime.combine(local.date(), time(hours, minutes)) - AHEAD).time()
        if start <= clock <= PILL_UNTIL or (start > PILL_UNTIL and clock >= start):
            out.append(("pill", f"pill:{local.date().isoformat()}"))
    weekday = local.weekday()
    if (weekday == 4 and clock >= PICKS_FROM) or weekday in (5, 6):
        out.append(("picks", f"picks:{_week(local.date())}"))
    awake = AWAKE[0] <= clock <= AWAKE[1]
    if not profiled and awake:
        out.append(("profile", "profile:first"))
    elif weekday == 5 and clock >= PROFILE_FROM and awake:
        out.append(("profile", f"profile:{_week(local.date())}"))
    return out


RUN = text("select outcome, attempt from insights.insights_craft_run where key = :key")

SAVE = text("""
    insert into insights.insights_craft_run
        (kind, key, outcome, detail, attempt, origin, parent_id, branch, family_key)
    values (:kind, :key, :outcome, :detail, :attempt, :origin, cast(:parent as uuid), :branch,
            :family)
    on conflict (user_id, key) do update
    set outcome = excluded.outcome, detail = excluded.detail, attempt = excluded.attempt,
        family_key = coalesce(excluded.family_key, insights.insights_craft_run.family_key),
        asked_at = now()
    returning id::text as id
""")


async def next_attempt(connection: AsyncConnection, key: str) -> int | None:
    previous = (await connection.execute(RUN, {"key": key})).one_or_none()
    if previous is None:
        return 1
    if previous.outcome != "queued":
        return previous.attempt
    ended = (
        await connection.execute(pills.FINISHED, {"key": pills.asked_as(key, previous.attempt)})
    ).first()
    if ended is None or ended.outcome == "ok" or previous.attempt >= MAX_ATTEMPTS:
        return None
    return previous.attempt + 1


async def profiled(connection: AsyncConnection) -> bool:
    return bool(
        await connection.scalar(
            text("select count(*) from insights.insights_craft_run where kind = 'profile'")
        )
    )


def _head(profile: insights.Profile, today: str) -> list[str]:
    lines = [
        f"Eres {profile.name}, dentro de arga, el sistema personal de una persona. Hoy es "
        f"{today}. Lees sus datos con las tools de lectura de arga (mcp__arga__*) y escribes solo "
        "en Insights, con sus tools.",
    ]
    if profile.about.strip():
        lines += ["", "Lo que la persona te ha contado de sí misma:", profile.about.strip()]
    return lines


def _families(found: list[tastes.Family]) -> list[str]:
    return [
        f"- {one.key}: {one.name}, peso {one.weight} de 3"
        + (" (fuera de su zona)" if one.outside else "")
        + f". {one.themes}"
        for one in found
    ]


def _sources(found: list[tastes.Source], family: str) -> list[str]:
    mine = [one for one in found if one.family_key == family and not one.hidden]
    return [f"- {one.name} ({one.kind}, {one.language}): {one.url}" for one in mine] or [
        "(Ninguna: usa fuentes serias.)"
    ]


def _answers(found: list[tastes.Question]) -> list[str]:
    return [
        f"- «{one.text}» → {tastes.said_answer(one)}" + (f" ({one.why})" if one.why else "")
        for one in found
    ]


VOICE = [
    "Cómo se escribe: en castellano de España, de tú cuando hables a la persona, con ritmo y sin "
    "frases hechas ni de relleno. Cifras a la española (1.234,5). Sin Markdown en los textos.",
]

CHICHA = [
    "Con chicha, siempre:",
    "- Habla del mundo, nunca de la persona ni de sus cifras: ni pasos, ni calorías, ni gastos, "
    "ni entrenos, ni «hoy has hecho». Sus datos sirven para elegir el tema; nunca son el tema.",
    "- Nada de autoayuda, consejos de vida, generalidades ni temas manidos. Un tema concreto, con "
    "nombres, fechas, lugares, mecanismos, cifras del mundo y, si lo hay, debate.",
    "- Rigor: no inventes cifras, citas ni fechas. Lo que cuentes, que esté en lo que has leído "
    "con WebFetch o WebSearch, o que sea conocimiento bien establecido. Si algo se discute, dilo.",
]


async def _pill_context(connection: AsyncConnection) -> dict[str, Any]:
    recent = await pills.recent(connection, limit=pills.SEEN_PILLS)
    since = datetime.now(MADRID).date() - timedelta(days=45)
    return {
        "traits": await tastes.traits(connection),
        "families": await tastes.families(connection),
        "sources": await tastes.sources(connection),
        "settings": await tastes.settings(connection),
        "recent": recent,
        "facts": await pills.facts(connection, since),
        "answers": await tastes.fresh_answers(connection),
        "picks": await picks.listed(connection, limit=80),
    }


def pill_brief(
    profile: insights.Profile,
    today: str,
    day: date,
    key: str,
    family: tastes.Family,
    context: dict[str, Any],
    *,
    origin: str = "daily",
    parent: pills.Pill | None = None,
    branch: str | None = None,
) -> str:
    settings: tastes.Settings = context["settings"]
    minutes = settings.pill_minutes
    least, most = minutes * pills.WORDS_PER_MINUTE[0], minutes * pills.WORDS_PER_MINUTE[1]
    target = (minutes * 75, minutes * 90)
    language = "es"
    if (
        origin == "daily"
        and settings.pill_language
        and day.weekday() == LANGUAGE_DAY
        and settings.pill_language != "es"
    ):
        language = settings.pill_language
    recent: list[pills.PillLine] = context["recent"]
    liked = [one.topic for one in recent if one.reaction == "interested"][:20]
    other = [one.topic for one in recent if one.reaction == "other"][:20]
    avoid = [
        one.label for one in context["traits"] if one.facet == "avoid" and one.status != "rejected"
    ]
    lines = [
        *_head(profile, today),
        "",
        "Hoy no aconsejas: escribes una píldora, unos minutos de lectura para aprender algo que le "
        "interese de verdad, como un buen artículo de una revista de divulgación seria.",
        "",
        f"Tema: {family.name} (`{family.key}`). Qué entra: {family.themes}.",
    ]
    if family.outside:
        lines.append(
            "Este tema es para sacarle de su zona: tiene que estar fuera de sus intereses "
            "habituales y de lo que ya le ha gustado. Elige algo concreto y sorprendente y cuenta "
            "por qué le puede enganchar igualmente (personas, conflictos, cómo funcionan las "
            "cosas)."
        )
    if origin == "branch" and parent is not None and branch:
        lines += [
            "",
            f"Es una rama de la píldora «{parent.headline}» ({parent.topic}): «{branch}». Ve más a "
            "fondo justo en ese punto. No repitas lo básico de la anterior.",
        ]
    elif origin == "surprise":
        lines += ["", "La ha pedido ahora con «Sorpréndeme»: que sorprenda de verdad."]
    elif origin == "daily":
        lines += [
            "",
            "Antes de elegir, mira si algo de su vida pide un tema (solo si es fuerte): un viaje "
            "en los próximos 7 a 21 días (travel_get_trips), una asignatura que esté cursando "
            "(study_get_courses), un libro que esté leyendo o acabe de terminar "
            "(library_get_currently_reading, library_find_books), de qué ha escrito estos días "
            "(notebook_get_digest). Si lo hay, úsalo dentro de este tema o de otro suyo con peso 2 o "
            "3 (y entonces pon ese `family_key`), y dilo en `hook` en una frase, sin cifras suyas. "
            "Si no, sin `hook`.",
        ]
    lines += [
        "",
        "Lo que sabes de sus gustos:",
        *tastes.described(context["traits"]),
        "",
        "Sus temas y cuánto le interesan:",
        *_families(context["families"]),
    ]
    if avoid:
        lines += ["", f"De esto no quiere que le hables: {'; '.join(avoid)}."]
    lines += [
        "",
        "Lo que ya ha leído (no repitas ni elijas algo casi igual):",
        *([f"- {one.topic}" for one in recent[:120]] or ["(Nada todavía.)"]),
    ]
    if liked:
        lines += ["", f"Lo que más le interesó: {'; '.join(liked)}."]
    if other:
        lines += ["", f"Lo que pidió cambiar por otro tema: {'; '.join(other)}."]
    if context["answers"]:
        lines += ["", "Lo que te ha contestado hace poco:", *_answers(context["answers"])]
    lines += [
        "",
        "Sus fuentes de confianza para este tema (úsalas si encajan; si no, otras serias):",
        *_sources(context["sources"], family.key),
        "",
        *CHICHA,
        "",
        "Cómo la haces:",
        "1. Elige un subtema concreto, sorprendente y con sustancia que dé para "
        f"{minutes} minutos.",
        "2. Léelo de verdad: abre con WebFetch el artículo de Wikipedia que mejor lo cubre (en "
        "español y, si es más completo, en inglés) y al menos otra fuente seria. Si hace falta, "
        "busca con WebSearch.",
        f"3. Escribe la lectura (entradilla y de 3 a 5 secciones con su ladillo) con unas "
        f"{target[0]} a {target[1]} palabras; se rechaza por debajo de {least} o por encima de "
        f"{most}. Empieza con un gancho, explica con ejemplos concretos, y cierra con por qué "
        "importa hoy. En temas políticos, las ideas con honestidad y sus críticas principales.",
        "4. «Para contar» (`to_tell`): un dato cierto y sorprendente que pueda contar a alguien. "
        "«Para pensar» (`to_think`): una pregunta abierta. Tres ramas (`branches`): subtemas "
        "concretos que den ganas de seguir, cada uno con por qué engancha.",
        f"5. Publícala con insights_publish_pill: `run_key` «{key}», `family_key` el del tema, "
        "`topic` el subtema, y en `sources` lo que has leído de verdad, con su dirección.",
        "6. Después, insights_publish_picks con el `pill_id` que te devuelva y `origin` «pill»: de 2 a "
        "5 cosas para seguir con este tema, en formatos que le gusten (libros que existan, mejor "
        "con edición en español; un podcast o un episodio; un documental o una película si lo "
        "hay). Cada una con por qué a esta persona, con lo suyo. Insights las comprueba en catálogo: "
        "lo que no exista no sale.",
    ]
    if language != "es":
        level = settings.pill_level or "B1"
        lines += [
            "",
            f"Hoy toca en {LANGUAGE_NAMES.get(language, language)}, para practicar, a nivel "
            f"{level}: frases claras, el vocabulario de ese nivel y lo difícil explicado. En "
            f"`language` «{language}», y en `glossary` de 8 a 15 palabras difíciles con su "
            "significado en español. Los datos del día, en español.",
        ]
    if origin == "daily":
        recent_facts = [one.text for one in context["facts"]][:60]
        lines += [
            "",
            f"7. Los datos del día con insights_publish_facts, `day` «{day.isoformat()}»: 5 datos, "
            "repartidos entre sus temas con más peso (y alguno de otro), ciertos y sorprendentes, "
            "cada uno con un nombre, una fecha o una cifra concreta, un poco más en `detail`, y la "
            "fuente que has leído para comprobarlo. Nada de los que todo el mundo ha oído ya. No "
            "repitas los de estos días:",
            *([f"- {one}" for one in recent_facts] or ["(Ninguno todavía.)"]),
            "",
            "8. Si algo de sus gustos no se puede deducir y te ayudaría a acertar, puedes dejarle "
            "una pregunta con insights_ask_question (como mucho una, de un toque y con su porqué). Lo "
            "que te haya contestado arriba, guárdalo como gusto con insights_note_taste.",
        ]
    lines += ["", *VOICE]
    return "\n".join(lines)


def picks_brief(profile: insights.Profile, today: str, context: dict[str, Any]) -> str:
    lines = [
        *_head(profile, today),
        "",
        "Toca «Para ti esta semana»: de 3 a 5 recomendaciones para el fin de semana y los días "
        "que vienen, ligadas a esta persona y no a un tema.",
        "",
        "Lo que sabes de sus gustos:",
        *tastes.described(context["traits"]),
        "",
        "Lo que ya le has recomendado, con lo que hizo:",
        *picks.described(context["picks"]),
        "",
        "Qué haces:",
        "1. Mira sus lecturas con las tools de Library (lo que lee, lo terminado, sus notas por "
        "libro, lo abandonado), lo que estudia (Study), adónde va (Travel), qué le interesa "
        "(Outings) y de qué escribe (Notebook). Si ha terminado un libro estos días, lo siguiente "
        "que le encajaría es la mejor recomendación posible.",
        "2. Elige de 3 a 5, de formatos distintos según sus gustos (libro, podcast o episodio, "
        "película, serie o documental), al menos una un poco fuera de lo suyo. Cosas que existan, "
        "con el título exacto (el de su edición en español si la tiene) y su autoría.",
        "3. Publica con insights_publish_picks, `origin` «weekly». En `why`, por qué a esta persona, "
        "con lo suyo («Le diste un 5 a…», «Vas a…»). En `because`, los rasgos en los que te "
        "apoyas. Insights las comprueba en catálogo y te dice lo que no ha publicado: si falla una, "
        "prueba con otra.",
        "4. Si ha terminado un libro, puedes preguntarle qué le pareció con insights_ask_question "
        "(una, con su porqué).",
        "",
        "Sin cifras suyas en lo que escribas: aquí no aconsejas.",
        "",
        *VOICE,
    ]
    return "\n".join(lines)


def profile_brief(profile: insights.Profile, today: str, context: dict[str, Any]) -> str:
    first = not context["traits"]
    lines = [
        *_head(profile, today),
        "",
        "Toca conocerle mejor: qué le gusta, cómo y qué vive ahora. Lo que propongas lo verá en la "
        "pantalla «Tú» de Insights, con su evidencia, y lo confirmará o descartará.",
        "",
        "Lo que ya sabes (no lo repitas; lo descartado no lo vuelvas a proponer):",
        *tastes.described(context["traits"]),
    ]
    rejected = [one.label for one in context["traits"] if one.status == "rejected"]
    if rejected:
        lines += [f"Descartado por la persona: {'; '.join(rejected)}."]
    if context["answers"]:
        lines += [
            "",
            "Lo que te ha contestado y aún no has guardado:",
            *_answers(context["answers"]),
        ]
    lines += [
        "",
        "Qué haces:",
        "1. Recorre sus apps con las tools de lectura: Library (géneros, autores, notas, lo "
        "abandonado), Study (lo que estudia y los idiomas), Travel (viajes hechos y que vienen, "
        "ideas), Outings (lo que le interesa y lo que silencia, sus ganas), Notebook (de qué "
        "escribe, sus carpetas), Training y Vitals (qué deporte hace), Carrera (a qué se dedica), "
        "Planner (lo que hace cada semana).",
        f"2. Propón {'hasta 15' if first else 'hasta 6'} rasgos con insights_propose_trait, cada uno "
        "concreto y con su evidencia en una línea («Library: 6 novelas de ciencia ficción, media "
        "4,2»). Facetas: `topic` (un tema), `genre`, `format`, `creator` (un autor, un podcast), "
        "`work` (una obra que le marcó), `style` (cómo le gusta que se lo cuenten), `avoid`, "
        "`context` (lo que vive ahora: un máster, un viaje, un idioma), `language`. Mejor pocos y "
        "ciertos que muchos y vagos.",
        "3. Lo que te contestó, guárdalo con insights_note_taste: eso ya lo dijo, no hace falta "
        "confirmarlo.",
        "4. Si hay algo importante que no se puede deducir, déjale una pregunta con "
        "insights_ask_question (como mucho una, de un toque, con su porqué). Si propusiste un rasgo "
        "con poca evidencia, puede ser `confirm` con su `trait_id`.",
        "",
        "Nada más: ni consejos ni píldoras en esta pasada.",
        "",
        *VOICE,
    ]
    return "\n".join(lines)


async def save(
    connection: AsyncConnection,
    kind: Kind,
    key: str,
    outcome: str,
    *,
    detail: str | None = None,
    attempt: int = 1,
    origin: str | None = None,
    parent_id: str | None = None,
    branch: str | None = None,
    family: str | None = None,
) -> str:
    return await connection.scalar(
        SAVE,
        {
            "kind": kind,
            "key": key,
            "outcome": outcome,
            "detail": detail[:500] if detail else None,
            "attempt": attempt,
            "origin": origin,
            "parent": parent_id,
            "branch": branch,
            "family": family,
        },
    )


async def _send(
    connection: AsyncConnection,
    kind: Kind,
    key: str,
    attempt: int,
    prompt: str,
    tools: tuple[str, ...],
    **extra: Any,
) -> str:
    answer = await passes.ask(passes.attempt_key(key, attempt), prompt, tools)
    problem = passes.refused_detail(answer)
    if problem:
        await save(connection, kind, key, "refused", detail=problem, attempt=attempt, **extra)
        return "refused"
    await save(connection, kind, key, "queued", attempt=attempt, **extra)
    return "queued"


async def run(
    connection: AsyncConnection,
    kind: Kind,
    key: str,
    now: datetime,
    rng: random.Random | None = None,
) -> str | None:
    attempt = await next_attempt(connection, key)
    if attempt is None:
        return None
    local = now.astimezone(MADRID)
    today = talk.spanish_day(local)
    profile = await insights.profile(connection)
    await tastes.ensure_defaults(connection)
    context = await _pill_context(connection)
    if kind == "pill":
        if await pills.daily(connection, local.date()) is not None:
            await save(connection, kind, key, "quiet", attempt=attempt, origin="daily")
            return "quiet"
        family = pills.choose(
            context["families"], await pills.history(connection), now, rng or random.Random()
        )
        prompt = pill_brief(profile, today, local.date(), key, family, context)
        outcome = await _send(
            connection, kind, key, attempt, prompt, WEB, origin="daily", family=family.key
        )
    elif kind == "picks":
        prompt = picks_brief(profile, today, context)
        outcome = await _send(connection, kind, key, attempt, prompt, ())
    else:
        prompt = profile_brief(profile, today, context)
        outcome = await _send(connection, kind, key, attempt, prompt, ())
    if outcome == "queued" and context["answers"]:
        await tastes.mark_seen(connection, [one.id for one in context["answers"] if one.id])
    return outcome


class TooMany(Exception):
    pass


async def more(
    connection: AsyncConnection,
    now: datetime,
    *,
    origin: Literal["surprise", "branch"],
    parent_id: str | None = None,
    branch: str | None = None,
    rng: random.Random | None = None,
) -> pills.Ask:
    local = now.astimezone(MADRID)
    asked_today = await connection.scalar(
        text("""
            select count(*) from insights.insights_craft_run
            where kind = 'more' and outcome = 'queued'
              and (asked_at at time zone 'Europe/Madrid')::date = :day
        """),
        {"day": local.date()},
    )
    if asked_today >= MORE_PER_DAY:
        raise TooMany(f"Ya has pedido {MORE_PER_DAY} hoy: mañana hay más.")
    parent = await pills.one(connection, parent_id) if parent_id else None
    if origin == "branch" and (parent is None or not branch):
        raise pills.NotFound(parent_id or "")
    await tastes.ensure_defaults(connection)
    context = await _pill_context(connection)
    family_list: list[tastes.Family] = context["families"]
    if origin == "branch" and parent is not None:
        family = next((one for one in family_list if one.key == parent.family_key), family_list[0])
    else:
        avoid = {parent.family_key} if parent is not None else set()
        family = pills.choose(
            family_list, await pills.history(connection), now, rng or random.Random(), avoid
        )
    key = f"more:{local:%Y%m%d}-{uuid4().hex[:12]}"
    profile = await insights.profile(connection)
    prompt = pill_brief(
        profile,
        talk.spanish_day(local),
        local.date(),
        key,
        family,
        context,
        origin=origin,
        parent=parent,
        branch=branch,
    )
    await _send(
        connection,
        "more",
        key,
        1,
        prompt,
        WEB,
        origin=origin,
        parent_id=parent.id if parent else None,
        branch=branch,
        family=family.key,
    )
    found = await pills.ask_by_key(connection, key)
    assert found is not None
    return found
