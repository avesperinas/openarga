from __future__ import annotations

import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Literal
from urllib.parse import quote, quote_plus

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from insights import hub, tastes
from insights.words import say

Kind = Literal[
    "book", "podcast", "episode", "film", "series", "documentary", "video", "article", "course"
]
State = Literal["new", "saved", "doing", "done", "dismissed"]
Origin = Literal["pill", "weekly", "event", "chat"]
ListName = Literal["read", "watch", "listen"]

LISTS: dict[str, ListName] = {
    "book": "read",
    "article": "read",
    "course": "read",
    "podcast": "listen",
    "episode": "listen",
    "film": "watch",
    "series": "watch",
    "documentary": "watch",
    "video": "watch",
}
CHECKED = {"book", "podcast", "episode", "film", "series", "documentary"}
SAME_TITLE = 0.72


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class PickIn(BaseModel):
    kind: Kind = Field(
        description=(
            "`book`, `podcast` (a show), `episode` (one episode), `film`, `series`, "
            "`documentary`, `video`, `article` or `course`."
        )
    )
    title: str = Field(
        min_length=1,
        max_length=200,
        description="The exact title, that of the edition in their language if there is one.",
    )
    creators: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Authorship: author, director, the show of an episode, the outlet.",
    )
    year: int | None = Field(default=None, ge=1000, le=2200)
    why: str = Field(
        min_length=10,
        max_length=400,
        description=(
            "Why for this person, with their own things: a trait, something they read, a trip. "
            "`It is a classic` does not count."
        ),
    )
    because: list[str] = Field(
        default_factory=list,
        max_length=4,
        description=(
            "The traits of theirs you lean on, by their text (those of insights_get_tastes)."
        ),
    )
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")


class Pick(BaseModel):
    id: str
    kind: Kind
    list: ListName
    title: str
    creators: list[str]
    year: int | None
    length: str | None
    language: str | None
    why: str
    because: list[str]
    origin: Origin
    pill_id: str | None
    verified: Literal["catalog", "link"]
    links: list[dict[str, str]]
    state: State
    collections: list[str]
    rating: float | None
    more_like: bool | None
    note: str | None
    sent_to: str | None
    has_cover: bool
    created_at: datetime
    updated_at: datetime


class PickChange(BaseModel):
    state: State | None = None
    collections: list[str] | None = Field(default=None, max_length=10)
    rating: float | None = Field(default=None, ge=0, le=5, multiple_of=0.5)
    more_like: bool | None = None
    note: str | None = Field(default=None, max_length=600)


COLUMNS = (
    "p.id::text as id, p.kind, p.title, p.creators, p.year, p.length, p.language, p.why, "
    "p.because, p.origin, p.pill_id::text as pill_id, p.verified, p.links, p.state, "
    "p.collections, p.rating::float as rating, p.more_like, p.note, p.sent_to, "
    "exists (select 1 from insights.insights_pick_cover c where c.pick_id = p.id) as has_cover, "
    "p.created_at, p.updated_at"
)


def _pick(row: Any) -> Pick:
    found = dict(row._mapping)
    found["list"] = LISTS[found["kind"]]
    return Pick.model_validate(found)


def plain(value: str) -> str:
    key = tastes.key_of(value.split(":")[0].split("(")[0])
    return re.sub(r"[^a-z0-9 ]", "", key).strip()


def same(asked: str, found: str) -> bool:
    a, b = plain(asked), plain(found)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= SAME_TITLE


def _surnames(names: list[str]) -> set[str]:
    return {plain(name).split()[-1] for name in names if plain(name)}


class Checked(BaseModel):
    title: str
    creators: list[str]
    year: int | None = None
    length: str | None = None
    language: str | None = None
    ref: dict[str, Any] = Field(default_factory=dict)
    links: list[dict[str, str]] = Field(default_factory=list)
    verified: Literal["catalog", "link"] = "catalog"
    cover: tuple[str, str] | None = None


def _search_links(wanted: PickIn) -> list[dict[str, str]]:
    query = " ".join([wanted.title, *wanted.creators[:1]])
    if wanted.kind == "video":
        return [
            {
                "label": "YouTube",
                "url": f"https://www.youtube.com/results?search_query={quote_plus(query)}",
            }
        ]
    return [{"label": "Buscar", "url": f"https://www.google.com/search?q={quote_plus(query)}"}]


async def _book(wanted: PickIn) -> Checked | None:
    query = " ".join([wanted.title, *wanted.creators[:1]])
    for candidate in await hub.books(query, 8):
        if not same(wanted.title, candidate.get("title") or ""):
            continue
        authors = list(candidate.get("authors") or [])
        if wanted.creators and authors and not (_surnames(wanted.creators) & _surnames(authors)):
            continue
        isbn = candidate.get("isbn13")
        links = []
        if isbn:
            links.append({"label": "Open Library", "url": f"https://openlibrary.org/isbn/{isbn}"})
            links.append(
                {
                    "label": "Todos tus libros",
                    "url": f"https://www.todostuslibros.com/busquedas?keyword={isbn}",
                }
            )
        else:
            links.append(
                {
                    "label": "Open Library",
                    "url": f"https://openlibrary.org/search?q={quote_plus(query)}",
                }
            )
        pages = candidate.get("pages")
        return Checked(
            title=candidate.get("title") or wanted.title,
            creators=authors or wanted.creators,
            year=candidate.get("year") or wanted.year,
            length=say("pick.pages", pages=pages) if pages else None,
            language=candidate.get("language") or wanted.language,
            ref={
                "source": candidate.get("source"),
                "source_ref": candidate.get("source_ref"),
                "isbn13": isbn,
            },
            links=links,
            cover=(candidate["source"], candidate["cover_ref"])
            if candidate.get("cover_ref")
            else None,
        )
    return None


async def _podcast(wanted: PickIn) -> Checked | None:
    query = " ".join([wanted.title, *wanted.creators[:1]])
    for candidate in await hub.podcasts(query, wanted.kind, 8):
        if not same(wanted.title, candidate.get("title") or ""):
            continue
        show = candidate.get("show") or (wanted.creators[0] if wanted.creators else "")
        minutes = candidate.get("minutes")
        episodes = candidate.get("episodes")
        length = (
            f"{minutes} min"
            if wanted.kind == "episode" and minutes
            else (f"{episodes} episodios" if episodes else None)
        )
        spotify = "episodes" if wanted.kind == "episode" else "podcasts"
        links = []
        if candidate.get("url"):
            links.append({"label": "Apple Podcasts", "url": str(candidate["url"])})
        name = quote(candidate.get("title") or wanted.title)
        links.append(
            {"label": "Spotify", "url": f"https://open.spotify.com/search/{name}/{spotify}"}
        )
        return Checked(
            title=candidate.get("title") or wanted.title,
            creators=[show] if show else wanted.creators,
            year=candidate.get("year") or wanted.year,
            length=length,
            language=candidate.get("language") or wanted.language,
            ref={"source": "apple_podcasts", "id": candidate.get("id")},
            links=links,
        )
    return None


async def _film(wanted: PickIn) -> Checked | None:
    query = wanted.title
    for candidate in await hub.films(query, wanted.kind, 8):
        if not same(wanted.title, candidate.get("title") or ""):
            continue
        year = candidate.get("year")
        if wanted.year and year and abs(int(year) - wanted.year) > 1:
            continue
        name = candidate.get("title") or wanted.title
        links = []
        if candidate.get("wikipedia"):
            links.append({"label": "Wikipedia", "url": str(candidate["wikipedia"])})
        elif candidate.get("id"):
            links.append(
                {"label": "Wikidata", "url": f"https://www.wikidata.org/wiki/{candidate['id']}"}
            )
        links.append(
            {
                "label": say("pick.where_to_watch"),
                "url": f"https://www.justwatch.com/es/buscar?q={quote_plus(name)}",
            }
        )
        seasons = candidate.get("seasons")
        minutes = candidate.get("minutes")
        length = (
            f"{seasons} temporadas"
            if seasons and seasons > 1
            else ("1 temporada" if seasons == 1 else (f"{minutes} min" if minutes else None))
        )
        return Checked(
            title=name,
            creators=list(candidate.get("creators") or wanted.creators),
            year=year or wanted.year,
            length=length,
            language=wanted.language,
            ref={"source": "wikidata", "id": candidate.get("id")},
            links=links,
        )
    return None


async def check(wanted: PickIn) -> Checked | None:
    if wanted.kind == "book":
        return await _book(wanted)
    if wanted.kind in ("podcast", "episode"):
        return await _podcast(wanted)
    if wanted.kind in ("film", "series", "documentary"):
        return await _film(wanted)
    return Checked(
        title=wanted.title,
        creators=wanted.creators,
        year=wanted.year,
        language=wanted.language,
        links=_search_links(wanted),
        verified="link",
    )


READ_BOOKS = text("""
    select payload->'record'->>'title' as title from insights.events
    where payload ? 'record' and payload->'record'->>'kind' = 'Libro'
""")


async def _already_read(connection: AsyncConnection) -> set[str]:
    return {plain(row.title) for row in await connection.execute(READ_BOOKS) if row.title}


async def publish(
    connection: AsyncConnection,
    wanted: list[PickIn],
    origin: Origin,
    pill_id: str | None = None,
) -> tuple[list[Pick], list[str]]:
    if pill_id is not None:
        exists = await connection.scalar(
            text("select count(*) from insights.insights_pill where id = cast(:id as uuid)"),
            {"id": pill_id},
        )
        if not exists:
            raise NotFound(pill_id)
    out: list[Pick] = []
    notes: list[str] = []
    read = await _already_read(connection)
    for one in wanted:
        key = plain(one.title) or tastes.key_of(one.title)
        repeated = await connection.scalar(
            text("select state from insights.insights_pick where kind = :kind and key = :key"),
            {"kind": one.kind, "key": key},
        )
        if repeated:
            notes.append(f"'{one.title}': already recommended")
            continue
        if one.kind == "book" and key in read:
            notes.append(f"'{one.title}': already in their reading")
            continue
        try:
            checked = await check(one)
        except hub.Unavailable as error:
            notes.append(f"'{one.title}': could not be checked ({error})")
            continue
        if checked is None:
            notes.append(f"'{one.title}': not in the catalogue, so it is not published")
            continue
        row = (
            await connection.execute(
                text("""
                    insert into insights.insights_pick
                        (kind, key, title, creators, year, length, language, why, because,
                         origin, pill_id, verified, ref, links)
                    values (:kind, :key, :title, cast(:creators as jsonb), :year, :length,
                            :language, :why, cast(:because as jsonb), :origin,
                            cast(:pill as uuid), :verified, cast(:ref as jsonb),
                            cast(:links as jsonb))
                    on conflict (user_id, kind, key) do nothing
                    returning id::text as id
                """),
                {
                    "kind": one.kind,
                    "key": key,
                    "title": checked.title[:200],
                    "creators": json.dumps(checked.creators[:5]),
                    "year": checked.year,
                    "length": checked.length,
                    "language": checked.language,
                    "why": one.why.strip(),
                    "because": json.dumps(one.because),
                    "origin": origin,
                    "pill": pill_id,
                    "verified": checked.verified,
                    "ref": json.dumps(checked.ref),
                    "links": json.dumps(checked.links),
                },
            )
        ).first()
        if row is None:
            notes.append(f"'{one.title}': already recommended")
            continue
        if checked.cover:
            found = await hub.cover(*checked.cover)
            if found:
                await connection.execute(
                    text("""
                        insert into insights.insights_pick_cover (pick_id, content, type)
                        values (cast(:id as uuid), :content, :type)
                        on conflict (pick_id) do nothing
                    """),
                    {"id": row.id, "content": found[0], "type": found[1]},
                )
        out.append(await one_pick(connection, row.id))
    return out, notes


async def one_pick(connection: AsyncConnection, pick_id: str) -> Pick:
    row = (
        await connection.execute(
            text(f"select {COLUMNS} from insights.insights_pick p where p.id = cast(:id as uuid)"),
            {"id": pick_id},
        )
    ).first()
    if row is None:
        raise NotFound(pick_id)
    return _pick(row)


async def listed(
    connection: AsyncConnection,
    *,
    states: list[str] | None = None,
    pill_id: str | None = None,
    limit: int = 200,
) -> list[Pick]:
    rows = await connection.execute(
        text(f"""
            select {COLUMNS} from insights.insights_pick p
            where (cast(:states as text[]) is null or p.state = any(cast(:states as text[])))
              and (cast(:pill as uuid) is null or p.pill_id = cast(:pill as uuid))
            order by p.updated_at desc limit :limit
        """),
        {"states": states, "pill": pill_id, "limit": limit},
    )
    return [_pick(row) for row in rows]


async def change(connection: AsyncConnection, pick_id: str, wanted: PickChange) -> Pick:
    changes = wanted.model_dump(exclude_unset=True)
    if "collections" in changes and changes["collections"] is not None:
        changes["collections"] = json.dumps(
            sorted({one.strip()[:40] for one in changes["collections"] if one.strip()})
        )
    allowed = ("state", "collections", "rating", "more_like", "note")
    sets = []
    for name in allowed:
        if name in changes:
            cast = "cast(:collections as jsonb)" if name == "collections" else f":{name}"
            sets.append(f"{name} = {cast}")
    if sets:
        done = await connection.execute(
            text(f"""
                update insights.insights_pick set {", ".join(sets)}, updated_at = now()
                where id = cast(:id as uuid)
            """),
            {**{name: changes[name] for name in allowed if name in changes}, "id": pick_id},
        )
        if done.rowcount == 0:
            raise NotFound(pick_id)
    found = await one_pick(connection, pick_id)
    if wanted.rating is not None or wanted.more_like is not None:
        await _learn(connection, found)
    return found


async def _learn(connection: AsyncConnection, found: Pick) -> None:
    if not found.creators or found.kind in ("video", "article", "course"):
        return
    creator = found.creators[0]
    liked = (found.rating is not None and found.rating >= 4) or found.more_like is True
    disliked = (found.rating is not None and found.rating <= 2) or found.more_like is False
    if liked:
        await tastes.remember(
            connection,
            "creator",
            creator,
            2 if (found.rating or 0) >= 4.5 else 1,
            "rated",
            evidence=f"'{found.title}': {found.rating or '–'} of 5",
            confirmed=True,
        )
    elif disliked:
        await tastes.remember(
            connection,
            "creator",
            creator,
            -1,
            "rated",
            evidence=f"'{found.title}': {found.rating or '–'} of 5",
            confirmed=True,
        )


async def cover(connection: AsyncConnection, pick_id: str) -> tuple[bytes, str]:
    row = (
        await connection.execute(
            text("""
                select content, type from insights.insights_pick_cover where pick_id = cast(:id as uuid)
            """),
            {"id": pick_id},
        )
    ).first()
    if row is None:
        raise NotFound(pick_id)
    return bytes(row.content), row.type


async def want_body(connection: AsyncConnection, pick_id: str) -> dict[str, Any]:
    found = await one_pick(connection, pick_id)
    if found.kind != "book":
        raise Conflict("only books are saved in your reading")
    ref = (
        await connection.scalar(
            text("select ref from insights.insights_pick where id = cast(:id as uuid)"),
            {"id": pick_id},
        )
    ) or {}
    body: dict[str, Any] = {"title": found.title, "authors": found.creators[:5]}
    if ref.get("isbn13"):
        body["isbn13"] = ref["isbn13"]
    body["note"] = say("pick.want_note", why=found.why)[:300]
    return body


async def mark_sent(connection: AsyncConnection, pick_id: str, where: str) -> Pick:
    await connection.execute(
        text("""
            update insights.insights_pick
            set sent_to = :where, state = case when state in ('new', 'dismissed') then 'saved'
                                               else state end,
                updated_at = now()
            where id = cast(:id as uuid)
        """),
        {"id": pick_id, "where": where},
    )
    return await one_pick(connection, pick_id)


def described(found: list[Pick]) -> list[str]:
    lines = []
    for one in found[:80]:
        mark = {
            "new": "not opened",
            "saved": "saved",
            "doing": "started",
            "done": "finished",
            "dismissed": "dismissed",
        }[one.state]
        extra = f", {one.rating:g}/5" if one.rating is not None else ""
        extra += ", wants more like it" if one.more_like else ""
        lines.append(f'- {one.kind} "{one.title}" ({", ".join(one.creators[:2])}): {mark}{extra}')
    return lines or ["(You have not recommended anything yet.)"]
