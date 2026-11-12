from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from outings import agenda, explore
from outings.common import today


class EventIn(BaseModel):
    title: Annotated[str, Field(min_length=2, max_length=200)]
    starts_on: date
    ends_on: date | None = None
    time: Annotated[str, Field(pattern=r"^\d{1,2}:\d{2}$")] | None = None
    venue: Annotated[str, Field(max_length=200)] | None = None
    town: Annotated[str, Field(max_length=120)] | None = None
    category: agenda.Category
    summary: Annotated[str, Field(max_length=400)] | None = None
    link: Annotated[str, Field(max_length=1000)] = Field(
        description="La página que anuncia el evento, la que lo respalda."
    )
    programme: Annotated[
        list[Annotated[str, Field(min_length=2, max_length=160)]], Field(max_length=40)
    ] = Field(
        default_factory=list,
        description='Los actos de una fiesta, un festival o un ciclo: "Sáb 3, 12:00 · Concurso".',
    )
    highlight: bool = Field(
        default=False, description="De lo grande: lo que merece ir aunque haya que moverse."
    )

    @field_validator("link")
    @classmethod
    def _link(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("el enlace es la dirección de la página que lo anuncia, con https://")
        return value.strip()


class Outcome(BaseModel):
    title: str
    outcome: str
    event_id: str | None = None
    reason: str | None = None


KNOWN = text("""
    select event_id::text as event_id, fingerprint from outings.outings_event_source
    where connection is null and key = :key
""")

SAVE = text("""
    insert into outings.outings_event_source
        (event_id, connection, origin, key, fingerprint, payload)
    values (cast(:event as uuid), null, 'tool', :key, :fingerprint, cast(:payload as jsonb))
    on conflict (user_id, key) where connection is null do update
    set fingerprint = excluded.fingerprint, payload = excluded.payload, removed = false,
        last_seen = now()
""")


def payload_of(item: EventIn) -> dict[str, Any]:
    host = urlsplit(item.link).netloc.removeprefix("www.")
    body = {
        "title": " ".join(item.title.split()),
        "starts_on": item.starts_on.isoformat(),
        "ends_on": (item.ends_on or item.starts_on).isoformat(),
        "time": item.time,
        "venue": item.venue,
        "town": item.town,
        "category": item.category,
        "summary": item.summary,
        "link": item.link,
        "source_name": f"Claude · {host}",
        "source_page": item.link,
        "programme": [" ".join(one.split()) for one in item.programme],
        "highlight": item.highlight,
    }
    body["key"] = hashlib.sha256(
        f"{agenda.fold(body['title'])}\n{body['starts_on']}".encode()
    ).hexdigest()[:24]
    body["fingerprint"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:32]
    return body


async def add(connection: AsyncConnection, items: list[EventIn]) -> list[Outcome]:
    first = today() - timedelta(days=1)
    last = today() + timedelta(days=366)
    out: list[Outcome] = []
    for item in items:
        ends = item.ends_on or item.starts_on
        if ends < item.starts_on:
            out.append(
                Outcome(title=item.title, outcome="dropped", reason="acaba antes de empezar")
            )
            continue
        if ends < first or item.starts_on > last:
            out.append(
                Outcome(
                    title=item.title,
                    outcome="dropped",
                    reason="fuera de fechas: ya pasó o es de dentro de más de un año",
                )
            )
            continue
        body = payload_of(item)
        found = (await connection.execute(KNOWN, {"key": body["key"]})).one_or_none()
        if found is not None and found.fingerprint == body["fingerprint"]:
            out.append(Outcome(title=item.title, outcome="unchanged", event_id=found.event_id))
            continue
        if found is not None:
            event_id, outcome = found.event_id, "updated"
        else:
            twin = await agenda.twin(connection, body)
            if twin is not None:
                event_id, outcome = twin, "joined"
            else:
                event_id = await connection.scalar(
                    agenda.NEW_EVENT,
                    {
                        "title": body["title"],
                        "starts_on": item.starts_on,
                        "ends_on": ends,
                        "category": item.category,
                    },
                )
                outcome = "added"
        await connection.execute(
            SAVE,
            {
                "event": event_id,
                "key": body["key"],
                "fingerprint": body["fingerprint"],
                "payload": json.dumps(body),
            },
        )
        await agenda.refresh(connection, event_id)
        out.append(Outcome(title=item.title, outcome=outcome, event_id=event_id))
    return out


AGENDAS = (
    ("Ayuntamiento de Pamplona", "https://www.pamplona.es/actualidad/eventos"),
    ("Turismo de Navarra", "https://www.visitnavarra.es/es/agenda"),
    ("Cultura Navarra", "https://www.culturanavarra.es/es/agenda"),
    ("Baluarte", "https://www.baluarte.com/es/agenda"),
    ("Navarra Arena", "https://www.navarrarena.com/es/agenda"),
)

ALWAYS = (
    "shopping medieval o recreación histórica en Navarra",
    "fiestas de interés turístico de Navarra",
    "visitas guiadas y teatralizadas en Pamplona y Navarra",
    "festivales de teatro de calle, circo y artes de calle en Navarra",
    "festivales de música, cine y teatro en Navarra",
    "exposiciones importantes en Pamplona (Museo Universidad de Navarra, Museo de Navarra, "
    "Ciudadela, Baluarte)",
)

MONTHLY = (
    "fiestas de los pueblos de Navarra en {mes} de {año}",
    "fiestas de los barrios de Pamplona en {mes} de {año}",
    "mercadillos, ferias de artesanía y mercados de productores en Pamplona y Navarra en {mes} "
    "de {año}",
    "semanas y jornadas gastronómicas, catas y concursos populares en Pamplona y Navarra en {mes} "
    "de {año}",
    "teatro de calle, pasacalles, circo y espectáculos al aire libre en Pamplona en {mes} de {año}",
    "actividades del Ayuntamiento de Pamplona y de los de su comarca (Burlada, Villava, Barañáin, "
    "Zizur, Ansoáin, Berriozar, Egüés, Huarte) en {mes} de {año}",
    "qué hacer en Navarra en {mes} de {año}: agenda de fin de semana",
)

YEARLY = (
    "fiestas, ferias y tradiciones de Navarra en {mes} de {año}: fechas",
    "jornadas gastronómicas y ferias de producto en Navarra en {mes} de {año}: fechas",
)

SEASON = {
    1: ("trufa", "sidra y txotx", "carnavales rurales"),
    2: ("trufa", "sidra y txotx", "carnavales rurales"),
    3: ("alcachofa", "sidra y txotx"),
    4: ("verdura", "alcachofa", "espárrago"),
    5: ("espárrago", "croqueta", "pintxo"),
    6: ("cereza", "espárrago", "queso"),
    7: ("queso", "cordero"),
    8: ("vino", "queso"),
    9: ("pochas", "vendimia", "piquillo"),
    10: ("piquillo", "setas", "caza", "vendimia"),
    11: ("setas", "caza", "vino nuevo"),
    12: ("trufa", "caza", "mercados de Navidad"),
}

TRADITIONS = {
    1: ("hogueras de San Antón", "carnaval de Ituren y Zubieta"),
    2: ("carnaval de Lantz", "carnavales de Pamplona"),
    3: ("Javierada",),
    4: (
        "Fiestas de la Verdura de Tudela",
        "Semana Santa en Tudela: el Volatín y la Bajada del Ángel",
    ),
    5: ("Día de la Almadía de Burgui",),
    6: ("San Juan y la noche de las hogueras",),
    7: ("San Fermín", "Tributo de las Tres Vacas", "Festival de Teatro de Olite"),
    8: ("Shopping Medieval de Olite", "fiestas de Estella y Tafalla"),
    9: ("Fiesta de la Vendimia de Olite",),
    10: ("Exaltación del Piquillo de Lodosa",),
    11: ("Ferias de San Andrés de Estella",),
    12: ("Olentzero", "Feria de Navidad de Pamplona"),
}

NEAR_DAYS = 90
FAR_DAYS = 365


def months_between(first: date, last: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def searches(first: date, last: date, far: date | None = None) -> list[str]:
    out = list(ALWAYS)
    near = months_between(first, last)
    for year, month in near:
        name = MONTHS[month - 1]
        out.extend(one.format(mes=name, año=year) for one in MONTHLY)
        out.extend(
            f"{thing} en Navarra en {name} de {year}: fiestas, ferias y jornadas"
            for thing in SEASON[month]
        )
    for year, month in months_between(first, far or last):
        if (year, month) in near:
            continue
        name = MONTHS[month - 1]
        out.extend(one.format(mes=name, año=year) for one in YEARLY)
        out.extend(f"{one} {year}: fechas" for one in TRADITIONS[month])
    return out


MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


def _day(day: date) -> str:
    return f"{day.day} de {MONTHS[day.month - 1]} de {day.year}"


def prompt(
    day: date | None = None,
    days: int = NEAR_DAYS,
    liked: list[str] | None = None,
    muted: list[str] | None = None,
) -> str:
    day = day or today()
    until = day + timedelta(days=days)
    far = day + timedelta(days=FAR_DAYS)
    agendas = "\n".join(f"- {name}: {url}" for name, url in AGENDAS)
    looked = "\n".join(f"- {one}" for one in searches(day, until, far))
    extra = ""
    if liked:
        extra += "\nMe interesa especialmente: " + ", ".join(liked) + ". Búscalo a propósito.\n"
    if muted:
        extra += "\nNo me interesa nada que tenga que ver con: " + ", ".join(muted) + ".\n"
    return f"""Rellena la agenda de Outings, en arga, con planes para salir en Pamplona y \
Navarra: con detalle del {_day(day)} al {_day(until)}, y de ahí al {_day(far)}, lo que \
vuelve cada año y ya tiene fecha.

Lo que más me interesa es lo de la calle y lo de los pueblos: mercadillos y ferias, fiestas de
pueblo y de barrio, lo que organizan los ayuntamientos, espectáculos de calle, gastronomía y
tradiciones. Los conciertos, solo los que salgan en las agendas de Baluarte y del Navarra Arena: no
los busques aparte.

1. Mira lo que ya está con la tool find_events (when: quarter y when: year), para no repetirlo.
2. Lee estas agendas:
{agendas}
3. Busca en la web, una por una (y sigue los enlaces que encuentres a otras agendas, a la del
   pueblo, a la del barrio o a la de la feria):
{looked}
{extra}
Qué apuntar: todo lo que a alguien de Pamplona le haría salir de casa, en Pamplona, en cualquier
pueblo de Navarra y en lo de alrededor que esté a menos de dos horas si es especial.
- Sí: mercadillos, rastros, mercados de productores y ferias de artesanía; ferias de producto y de
  ganado; semanas y jornadas gastronómicas (de la croqueta, del pintxo, de la cazuelica, de las
  setas), catas populares, concursos de cocina y txotx; fiestas del vino y vendimias; fiestas de
  los pueblos y de los barrios; teatro de calle, circo, pasacalles, gigantes y cabezudos, cine al
  aire libre; lo que el ayuntamiento organiza para el público (programas de fiestas, ciclos
  culturales, ferias, actividades de Navidad, de verano o del Día de Navarra); mercados medievales
  y recreaciones; carnavales; romerías y tradiciones con nombre; visitas guiadas abiertas; rutas y
  pruebas populares conocidas; y teatro, danza y festivales.
- Lo lejano: de los meses que no se miran con detalle, apunta lo que ya tiene la fecha de su
  edición nueva en una página (la del organizador, la del ayuntamiento o la prensa). Si solo
  encuentras la del año pasado, no lo apuntes: saldrá cuando se anuncie.
- Una fiesta, un festival, una feria o una semana es UN evento, con sus fechas de principio a fin
  y sus actos en programme ("Sáb 3, 12:00 · Concurso de tortillas"), nunca un evento por acto. Las
  fiestas patronales de un pueblo son una fila, con lo especial (encierros, gigantes, concursos,
  comidas populares) en su programa. Un mercadillo que se repite cada semana o cada mes es una
  fila, con su próxima fecha y cada cuánto en el resumen.
- highlight: true para lo grande: una fiesta famosa, una feria con nombre, un festival, lo que
  tiene una edición con número, un concierto de alguien muy conocido.
- No apuntes: congresos, jornadas profesionales o técnicas, cursos y talleres de biblioteca,
  cuentacuentos, festivos (Todos los Santos, la Fiesta Nacional, Halloween), actos protocolarios
  (plenos, inauguraciones, homenajes), conciertos de salas pequeñas ni lo que sea para un público
  muy concreto.

4. Apunta con la tool add_events, en tandas de hasta 40. De cada evento: título tal como lo escribe
   su página, fechas de inicio y fin (AAAA-MM-DD), hora si la hay, lugar, pueblo, categoría, un
   resumen de una frase, programme si tiene actos, highlight y, siempre, el enlace a la página que
   lo anuncia. Categorías: eat (gastronomía), stage (música, teatro, danza, cine), culture
   (exposiciones, charlas, visitas), festival (fiestas, ferias, mercadillos y lo de la calle) y
   outdoors (deporte y naturaleza).
5. Si en find_events ves actos sueltos de algo que ya está como un evento con su programa, o cosas
   de las que no hay que apuntar, apártalas con la tool hide_events.

Solo lo que leas en una página, nada de memoria: si no encuentras la página, no lo apuntes. Al
final, dime cuántos has apuntado (y cuántos de ellos no son conciertos), cuántos estaban ya,
cuántos apartaste y cuáles se descartaron y por qué."""


async def brief(connection: AsyncConnection, days: int = NEAR_DAYS) -> str:
    found = await explore.interests(connection)
    return prompt(
        today(),
        days,
        [one.term for one in found if one.kind == "like"],
        [one.term for one in found if one.kind == "mute"],
    )
