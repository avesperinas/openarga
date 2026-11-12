from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from notebook import digest, notes
from notebook import markdown as md
from notebook.notes import MADRID, PropertyFilter

MODULE = "notebook"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"
AUTHOR = "tool"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


NOTE = Field(
    description="La nota: su título (`DE 2.3 Perfekt`), su ruta si hay dos con el mismo título "
    "(`Study/Alemán/DE 2.3 Perfekt`) o su id.",
    min_length=1,
    max_length=1200,
)


def _when(value: datetime) -> str:
    return value.astimezone(MADRID).isoformat(timespec="seconds")


def _summary(one: notes.NoteSummary) -> dict[str, Any]:
    by = "claude" if one.updated_by == "tool" else one.updated_by
    return {
        "path": one.path,
        "updated_at": _when(one.updated_at),
        "updated_by": one.updated_app or by,
    }


def _written(one: notes.Note, **extra: Any) -> dict[str, Any]:
    return {"id": one.id, "path": one.path, "version": one.version, **extra}


class SearchNotes(BaseModel):
    query: str | None = Field(
        default=None,
        max_length=300,
        description="Palabras a buscar en título, texto y propiedades. Da igual acentos, diéresis "
        "y mayúsculas, y una palabra encuentra las que empiezan por ella.",
    )
    folder: str | None = Field(default=None, description="Solo en esta carpeta y sus subcarpetas.")
    tag: str | None = Field(default=None, description="Solo con este tag o uno hijo suyo.")
    properties: list[PropertyFilter] = Field(
        default_factory=list,
        max_length=10,
        description="Filtros por propiedad del frontmatter. `op`: eq, ne, lt, lte, gt, gte, "
        "exists, missing. Las fechas se comparan como texto ISO, y `today` es hoy. En una lista, "
        "`eq` es que la contiene.",
    )
    since: date | None = Field(
        default=None,
        description="Solo las cambiadas desde este día, y cuántas veces cambió cada una. Es lo "
        "que cambió en un periodo: sin palabras, de lo más reciente a lo más viejo.",
    )
    until: date | None = Field(default=None, description="Solo las cambiadas hasta este día.")
    by: str | None = Field(
        default=None,
        pattern="^(me|claude|import)$",
        description="Solo las que cambiaste tú, Claude o la importación por última vez.",
    )
    limit: int = Field(default=20, ge=1, le=100)


def _href(one: notes.NoteSummary) -> str:
    return f"/notebook/nota/{one.id}"


async def search_notes(connection: AsyncConnection, arguments: SearchNotes) -> dict[str, Any]:
    author = {"me": "app", "claude": "tool", "import": "import"}.get(arguments.by or "")
    found = await notes.search(
        connection,
        arguments.query,
        arguments.folder,
        arguments.tag,
        arguments.properties,
        arguments.limit,
        datetime.combine(arguments.since, time(), MADRID) if arguments.since else None,
        (
            datetime.combine(arguments.until + timedelta(days=1), time(), MADRID)
            if arguments.until
            else None
        ),
        author,  # type: ignore[arg-type]
    )
    out = []
    for hit in found:
        one = {**_summary(hit), "href": _href(hit), "snippet": hit.snippet, "tags": hit.tags}
        if hit.changes is not None:
            one["changes"] = hit.changes
        if hit.source is not None:
            one["from_app"] = hit.source.model_dump()
        out.append(one)
    return {"notes": out, "count": len(found)}


class ReadNote(BaseModel):
    note: str | None = Field(
        default=None,
        description="La nota: su título (`DE 2.3 Perfekt`), su ruta si hay dos con el mismo título "
        "(`Study/Alemán/DE 2.3 Perfekt`) o su id. Sin ella, la nota del día de `day`.",
        min_length=1,
        max_length=1200,
    )
    day: date | None = Field(
        default=None,
        description="La nota de ese día (`2026-09-28`), en vez de `note`. Sin ninguno de los dos, "
        "la de hoy.",
    )
    section: str | None = Field(
        default=None,
        description="Solo lo que hay bajo este encabezado, con sus subsecciones. Sin él, entera.",
    )
    links: bool = Field(
        default=False,
        description="Con sus enlaces: a qué nota llega cada uno, y las notas que la enlazan con "
        "la línea donde lo hacen.",
    )


async def read_note(connection: AsyncConnection, arguments: ReadNote) -> dict[str, Any]:
    if arguments.note is None:
        day = arguments.day or notes.today()
        found_day = await notes.daily(connection, day, False, AUTHOR)
        if found_day is None:
            return {"date": day.isoformat(), "exists": False}
        one = found_day
    else:
        one = await notes.find(connection, arguments.note)
    content = one.content
    if arguments.section:
        try:
            found = md.section(content, arguments.section)
        except md.NotFoundInNote as error:
            raise notes.Invalid(str(error)) from error
        except md.Ambiguous as error:
            raise notes.Conflict(str(error)) from error
        content = content[found.start : found.end]
    backlinks = await notes.backlinks(connection, one.id)
    owner = await notes.owner(connection, one.id)
    found = {
        "id": one.id,
        **_summary(one),
        "href": _href(one),
        "version": one.version,
        "properties": one.properties,
        "tags": one.tags,
        "outline": [f"{'#' * h['level']} {h['text']}" for h in one.outline],
        "backlinks": len(backlinks),
        "content": content,
    }
    if owner is not None:
        found["of_apps"] = {
            "apps": [app["name"] for app in owner.apps],
            "properties": owner.properties,
            "note": "El bloque entre `%% arga %%` y `%% /arga %%` y estas propiedades los "
            "escribe la app y se cambian con sus tools; lo de fuera del bloque es tuyo.",
        }
    if arguments.note is None:
        found["date"] = (arguments.day or notes.today()).isoformat()
        found["exists"] = True
    if arguments.links:
        outgoing = await notes.links_of(connection, one.id)
        found["links"] = [
            {
                "written": link.target + (f"#{link.heading}" if link.heading else ""),
                "kind": link.kind,
                "line": link.line + 1,
                "note": link.note.path if link.note else None,
            }
            for link in outgoing
        ]
        found["backlinks"] = [{"path": b.note.path, "lines": b.lines} for b in backlinks]
    return found


class ExploreGraph(BaseModel):
    note: str = NOTE
    depth: int = Field(default=1, ge=1, le=2, description="Saltos desde la nota: 1 o 2.")


async def explore_graph(connection: AsyncConnection, arguments: ExploreGraph) -> dict[str, Any]:
    found = await notes.graph(connection, arguments.note, arguments.depth)
    paths = {n.id: md.path_of(n.folder, n.title) for n in found.nodes}
    return {
        "notes": [
            {"path": paths[n.id], "depth": n.depth, "links": n.links}
            for n in sorted(found.nodes, key=lambda n: (n.depth or 0, -n.links, paths[n.id]))
        ],
        "edges": [[paths[a], paths[b]] for a, b in found.edges],
    }


class ListFolder(BaseModel):
    folder: str | None = Field(
        default=None, description="La ruta. Sin ella, la raíz, y además todos los tags."
    )


async def list_folder(connection: AsyncConnection, arguments: ListFolder) -> dict[str, Any]:
    found = await notes.list_folder(connection, arguments.folder)
    out: dict[str, Any] = {
        "folder": found.path,
        "folders": [{"path": f.path, "notes": f.notes} for f in found.folders],
        "notes": [n.title for n in found.notes],
    }
    if not arguments.folder:
        out["tags"] = [t.model_dump() for t in await notes.all_tags(connection)]
    return out


class GetDigest(BaseModel):
    period: str | None = Field(
        default=None,
        pattern=r"^\d{4}-([Ww]\d{1,2}|[Tt][1-4]|\d{1,2})$",
        description="`2026-W41`, `2026-09` o `2026-T4`. Sin él, la última semana cerrada.",
    )


async def get_digest(connection: AsyncConnection, arguments: GetDigest) -> dict[str, Any]:
    if arguments.period:
        try:
            period = digest.parse(arguments.period)
        except ValueError:
            return {"note": f"no entiendo el periodo «{arguments.period}»"}
    else:
        period = digest.of("week", notes.today()).previous()
    content = await digest.compose(connection, period)
    try:
        written = await notes.find_row(connection, period.path)
    except notes.NotFound:
        written = None
    return {
        "period": period.title,
        "from": period.start.isoformat(),
        "to": period.end.isoformat(),
        "note": period.path if written else None,
        "content": content,
    }


class CreateNote(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="Sin `/ \\ : [ ] # ^ |`.")
    folder: str | None = Field(
        default=None, description="La carpeta; se crea si no existe. Sin ella, en la raíz."
    )
    content: str = Field(default="", max_length=notes.MAX_CONTENT)
    properties: dict[str, Any] = Field(
        default_factory=dict, description="El frontmatter. Una fecha, como texto ISO."
    )


async def create_note(connection: AsyncConnection, arguments: CreateNote) -> dict[str, Any]:
    content = arguments.content
    if arguments.properties:
        content = md.with_properties(content, arguments.properties)
    created = await notes.create(connection, arguments.folder, arguments.title, content, AUTHOR)
    return _written(created)


class AppendToNote(BaseModel):
    note: str = NOTE
    text: str = Field(min_length=1, max_length=200_000)
    heading: str | None = Field(
        default=None,
        description="Al final de la sección de este encabezado, antes del siguiente. Sin él, al "
        "final de la nota.",
    )


async def append_to_note(connection: AsyncConnection, arguments: AppendToNote) -> dict[str, Any]:
    _, saved = await notes.edit(
        connection,
        arguments.note,
        lambda content: md.append(content, arguments.text, arguments.heading),
        AUTHOR,
    )
    return _written(saved)


class EditNote(BaseModel):
    note: str = NOTE
    old_text: str = Field(
        min_length=1,
        max_length=200_000,
        description="El fragmento exacto que hay ahora. Tiene que aparecer una sola vez.",
    )
    new_text: str = Field(max_length=200_000, description="Por lo que se cambia. Vacío, lo quita.")


async def edit_note(connection: AsyncConnection, arguments: EditNote) -> dict[str, Any]:
    _, saved = await notes.edit(
        connection,
        arguments.note,
        lambda content: md.replace_fragment(content, arguments.old_text, arguments.new_text),
        AUTHOR,
    )
    return _written(saved)


class ReplaceSection(BaseModel):
    note: str = NOTE
    heading: str = Field(min_length=1, max_length=300, description="El encabezado, que se queda.")
    text: str = Field(max_length=200_000, description="Lo nuevo bajo el encabezado.")


async def replace_section(connection: AsyncConnection, arguments: ReplaceSection) -> dict[str, Any]:
    _, saved = await notes.edit(
        connection,
        arguments.note,
        lambda content: md.replace_section(content, arguments.heading, arguments.text),
        AUTHOR,
    )
    return _written(saved)


class SetProperties(BaseModel):
    note: str = NOTE
    set: dict[str, Any] = Field(
        default_factory=dict, description="Las propiedades a poner o cambiar, con su valor."
    )
    remove: list[str] = Field(default_factory=list, description="Las propiedades a quitar.")


async def set_properties(connection: AsyncConnection, arguments: SetProperties) -> dict[str, Any]:
    if not arguments.set and not arguments.remove:
        raise notes.Invalid("no hay nada que poner ni quitar")
    _, saved = await notes.edit(
        connection,
        arguments.note,
        lambda content: md.set_properties(content, arguments.set, arguments.remove),
        AUTHOR,
    )
    return _written(saved, properties=saved.properties)


class AddToDailyNote(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    day: date | None = Field(default=None, description="El día. Por defecto, hoy.")
    heading: str | None = Field(default=None, description="Bajo este encabezado, si lo tiene.")


async def add_to_daily_note(
    connection: AsyncConnection, arguments: AddToDailyNote
) -> dict[str, Any]:
    daily = await notes.daily(connection, arguments.day, True, AUTHOR)
    assert daily is not None
    _, saved = await notes.edit(
        connection,
        daily.id,
        lambda content: md.append(content, arguments.text, arguments.heading),
        AUTHOR,
    )
    return _written(saved)


class MoveNote(BaseModel):
    note: str = NOTE
    folder: str | None = Field(
        default=None, description='La carpeta nueva; `""` es la raíz. Sin ella, la misma.'
    )
    title: str | None = Field(default=None, description="El título nuevo. Sin él, el mismo.")


async def move_note(connection: AsyncConnection, arguments: MoveNote) -> dict[str, Any]:
    if arguments.folder is None and arguments.title is None:
        raise notes.Invalid("di a qué carpeta o con qué título")
    moved, relinked = await notes.move(
        connection, arguments.note, arguments.folder, arguments.title, AUTHOR
    )
    return _written(moved, relinked_notes=relinked)


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[[AsyncConnection, Any], Awaitable[dict[str, Any]]]


TOOLS: dict[str, Tool] = {
    "search_notes": Tool(SearchNotes, search_notes),
    "get_digest": Tool(GetDigest, get_digest),
    "read_note": Tool(ReadNote, read_note),
    "explore_graph": Tool(ExploreGraph, explore_graph),
    "list_folder": Tool(ListFolder, list_folder),
    "create_note": Tool(CreateNote, create_note),
    "append_to_note": Tool(AppendToNote, append_to_note),
    "edit_note": Tool(EditNote, edit_note),
    "replace_section": Tool(ReplaceSection, replace_section),
    "set_properties": Tool(SetProperties, set_properties),
    "add_to_daily_note": Tool(AddToDailyNote, add_to_daily_note),
    "move_note": Tool(MoveNote, move_note),
}
