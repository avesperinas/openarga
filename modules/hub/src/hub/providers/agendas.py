from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from arga_contracts.notify import zone
from hub.declare import Ask, Choice, Offer, Provider, Setting, Sync
from hub.providers import USER_AGENT, Fetched, SourceError

PROVIDER = "agendas"
EVENT = "leisure.event"
PAGES = "pages"
URL = "url"
NAME = "name"
SEARCH = "search"

AI_APP = "hub"
TEXT_LIMIT = 60_000
LINKS_LIMIT = 400
MAX_TOKENS = 12000
MAX_PIECES = 4
DAILY_CALLS = 30
WEEKLY_SEARCHES = 8
PAGES_PER_SEARCH = 3
CATEGORIES = ("eat", "stage", "culture", "festival", "outdoors")


@dataclass(frozen=True)
class Page:
    key: str
    name: str
    url: str


START = (
    Page("baluarte", "Baluarte", "https://www.baluarte.com/es/agenda"),
    Page("pamplona", "Ayuntamiento de Pamplona", "https://www.pamplona.es/actualidad/eventos"),
    Page("cultura", "Cultura Navarra", "https://www.culturanavarra.es/es/agenda"),
    Page("turismo", "Turismo de Navarra", "https://www.visitnavarra.es/es/agenda"),
)
BY_KEY = {page.key: page for page in START}


def normalise(key: str, raw: str) -> str:
    return raw.strip()


def _url(raw: str) -> str:
    value = raw.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("an agenda address starts with https://")
    return value


def clean_settings(raw: dict[str, Any]) -> dict[str, Any]:
    chosen = raw.get(PAGES)
    if isinstance(chosen, str):
        chosen = [part.strip() for part in chosen.split(",") if part.strip()]
    chosen = list(chosen or [])
    pages: list[dict[str, str]] = []
    unknown = [one for one in chosen if one not in BY_KEY and one != SEARCH]
    if unknown:
        raise ValueError(f"unknown agendas: {', '.join(unknown)}")
    for page in START:
        if page.key in chosen:
            pages.append({URL: page.url, NAME: page.name})
    if raw.get(URL):
        url = _url(str(raw[URL]))
        name = " ".join(str(raw.get(NAME) or "").split())[:80] or urlsplit(url).netloc.removeprefix(
            "www."
        )
        pages.append({URL: url, NAME: name})
    for given in raw.get("custom") or []:
        pages.append({URL: _url(str(given[URL])), NAME: str(given.get(NAME) or "")[:80]})
    search = SEARCH in chosen or bool(raw.get(SEARCH) is True)
    if not pages and not search:
        raise ValueError("choose at least one agenda or paste its address")
    out: dict[str, Any] = {PAGES: pages, SEARCH: search}
    if raw.get("model"):
        out["model"] = str(raw["model"])[:80]
    if raw.get("daily_calls"):
        out["daily_calls"] = max(1, min(200, int(raw["daily_calls"])))
    if raw.get("weekly_searches"):
        out["weekly_searches"] = max(1, min(50, int(raw["weekly_searches"])))
    return out


BLOCKS = {
    "p", "div", "li", "ul", "ol", "tr", "td", "th", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "table", "dt", "dd", "time", "span",
}  # fmt: skip
SKIPPED = {"script", "style", "noscript", "svg", "template", "iframe"}


class _Reader(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.parts: list[str] = []
        self.links: list[str] = []
        self.number: dict[str, int] = {}
        self.skipping = 0
        self.href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED:
            self.skipping += 1
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                self.href = urljoin(self.base, href.strip()).split("#")[0]
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED:
            self.skipping = max(0, self.skipping - 1)
        elif tag == "a" and self.href:
            if self.href not in self.number and len(self.links) < LINKS_LIMIT:
                self.links.append(self.href)
                self.number[self.href] = len(self.links)
            if self.href in self.number:
                self.parts.append(f" ⟨{self.number[self.href]}⟩ ")
            self.href = None
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).split("\n"))
        return "\n".join(line for line in lines if line)[:TEXT_LIMIT]


@dataclass
class Read:
    url: str
    name: str
    text: str
    links: list[str]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:32]


def parse(url: str, name: str, html: str) -> Read:
    reader = _Reader(url)
    reader.feed(html)
    reader.close()
    return Read(url=url, name=name, text=reader.text(), links=reader.links)


class _Pace:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.last = 0.0

    async def wait(self, interval: float) -> None:
        async with self.lock:
            pause = self.last + interval - time.monotonic()
            if pause > 0:
                await asyncio.sleep(pause)
            self.last = time.monotonic()


PACE = _Pace()
MIN_INTERVAL = 1.0


async def download(client: httpx.AsyncClient, url: str, name: str) -> Read:
    await PACE.wait(MIN_INTERVAL)
    try:
        response = await client.get(
            url,
            headers={
                "user-agent": USER_AGENT,
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "es",
            },
            timeout=30.0,
            follow_redirects=True,
        )
    except httpx.HTTPError as error:
        raise SourceError(
            f"{name} does not answer ({type(error).__name__})", transient=True
        ) from error
    if response.status_code >= 400:
        raise SourceError(f"{name} answers {response.status_code}")
    return parse(str(response.url), name, response.text)


SYSTEM = """You read the page of a public events agenda and list the events it announces.

Rules:
- Only what the page says. Do not invent, do not complete with what you know, do not add events \
that are not there.
- The title copied from the page as it is, not translated or summarised.
- Dates as YYYY-MM-DD. If the page gives no year, the year of the next day with that date from \
today. If it lasts several days, the first and the last; if it is one day, both the same.
- The start time as HH:MM if the page says it; otherwise nothing.
- The place (hall, bar, square) and the town or city, if the page says them.
- The category, one of: eat (food weeks and days, produce fairs, tastings), stage (music, \
theatre, dance, cinema, comedy), culture (exhibitions, talks, guided visits, books), festival \
(patron saint festivities, tradition, popular fairs), outdoors (sport, nature, routes).
- A summary of one or two sentences, in the language of the page, of what the page says.
- The link: the number ⟨n⟩ next to the event in the text, if it has one.
- recurring: true only if the page says it happens every year ("16th edition", "as every \
October").
- No events that are already over. If there are none, an empty list."""

SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "starts_on": {"type": "string"},
                    "ends_on": {"type": "string"},
                    "time": {"type": ["string", "null"]},
                    "venue": {"type": ["string", "null"]},
                    "town": {"type": ["string", "null"]},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "summary": {"type": ["string", "null"]},
                    "link": {"type": ["integer", "null"]},
                    "recurring": {"type": "boolean"},
                },
                "required": ["title", "starts_on", "ends_on", "category"],
            },
        }
    },
    "required": ["events"],
}


def prompt(page: Read, today: date) -> str:
    return (
        f"Today is {today.isoformat()}. Page: {page.name} ({page.url}).\n\n"
        f"--- page text ---\n{page.text}"
    )


async def ask_model(content: str, system: str = SYSTEM) -> list[dict[str, Any]]:
    from hub import ai
    from hub.connections import Refused

    try:
        answer = await ai.extract(
            AI_APP,
            {
                "role": "fast",
                "instructions": system,
                "input": content,
                "output_schema": SCHEMA,
            },
        )
    except Refused as error:
        if "did not fit" in str(error):
            raise Cut(str(error)) from error
        raise Unreadable(f"the AI layer: {error}", transient=error.status in (502, 503)) from error
    found = answer["output"].get("events")
    return [one for one in found if isinstance(one, dict)] if isinstance(found, list) else []


class Cut(SourceError):
    pass


class Unreadable(SourceError):
    """Nothing more can be read in this pass: no provider, no budget, a refused key."""


def pieces(text: str, parts: int) -> list[str]:
    lines = text.split("\n")
    size = max(1, -(-len(lines) // parts))
    return ["\n".join(lines[start : start + size]) for start in range(0, len(lines), size)]


MONTHS = (
    ("enero", "ene", "urtarrila"),
    ("febrero", "feb", "otsaila"),
    ("marzo", "mar", "martxoa"),
    ("abril", "abr", "apirila"),
    ("mayo", "may", "maiatza"),
    ("junio", "jun", "ekaina"),
    ("julio", "jul", "uztaila"),
    ("agosto", "ago", "abuztua"),
    ("septiembre", "sep", "sept", "iraila"),
    ("octubre", "oct", "urria"),
    ("noviembre", "nov", "azaroa"),
    ("diciembre", "dic", "abendua"),
)


def fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", plain.casefold()).split())


def title_in(title: str, text: str) -> bool:
    wanted = fold(title)
    if not wanted:
        return False
    if wanted in text:
        return True
    words = [word for word in wanted.split() if len(word) > 2]
    if len(words) < 2:
        return False
    for start in [match.start() for match in re.finditer(re.escape(words[0]), text)] or [0]:
        window = text[max(0, start - 200) : start + 300]
        if sum(word in window for word in words) >= max(2, round(len(words) * 0.8)):
            return True
    return False


def date_in(day: date, text: str) -> bool:
    d, m = day.day, day.month
    numeric = [
        rf"\b0?{d} 0?{m}(?: (?:{day.year}|{day.year % 100})\b|(?! \d{{2,4}}\b))",
        rf"\b{day.year} 0?{m} 0?{d}\b",
    ]
    if any(re.search(pattern, text) for pattern in numeric):
        return True
    names = "|".join(MONTHS[m - 1])
    joiners = r"(?: (?:al|a|y|e|eta)?\s*\d{1,2})*"
    patterns = (
        rf"\b0?{d}{joiners} (?:de )?(?:{names})[a-z]*\b",
        rf"\b(?:{names})[a-z]* (?:\d{{1,2}} (?:al |a |y |e |eta )?)*0?{d}\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


@dataclass
class Checked:
    events: list[dict[str, Any]] = field(default_factory=list)
    discarded: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: str) -> None:
        self.discarded[reason] = self.discarded.get(reason, 0) + 1


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _clip(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())[:limit]
    return cleaned or None


def check(found: list[dict[str, Any]], page: Read, connection: str, today: date) -> Checked:
    text = fold(page.text)
    out = Checked()
    seen: set[str] = set()
    for one in found:
        title = _clip(one.get("title"), 200)
        starts, ends = _day(one.get("starts_on")), _day(one.get("ends_on"))
        if not title or starts is None:
            out.drop("no title or no date")
            continue
        ends = ends or starts
        if ends < starts:
            starts, ends = ends, starts
        if one.get("category") not in CATEGORIES:
            out.drop("unknown category")
            continue
        if not title_in(title, text):
            out.drop("the title is not on the page")
            continue
        if not date_in(starts, text) or (ends != starts and not date_in(ends, text)):
            out.drop("the date is not on the page")
            continue
        if ends < today - timedelta(days=1) or starts > today + timedelta(days=366):
            out.drop("out of dates")
            continue
        link = one.get("link")
        if link is None:
            url = page.url
        elif isinstance(link, int) and 1 <= link <= len(page.links):
            url = page.links[link - 1]
        else:
            out.drop("a link that is not on the page")
            continue
        key = hashlib.sha256(f"{page.url}\n{fold(title)}\n{starts}".encode()).hexdigest()[:24]
        if key in seen:
            continue
        seen.add(key)
        clock = _clip(one.get("time"), 5)
        event = {
            "connection": connection,
            "key": key,
            "title": title,
            "starts_on": starts.isoformat(),
            "ends_on": ends.isoformat(),
            "time": clock if clock and re.fullmatch(r"\d{1,2}:\d{2}", clock) else None,
            "venue": _clip(one.get("venue"), 200),
            "town": _clip(one.get("town"), 120),
            "category": one["category"],
            "summary": _clip(one.get("summary"), 400),
            "link": url,
            "source_name": page.name,
            "source_page": page.url,
            "recurring": bool(one.get("recurring")),
        }
        event["fingerprint"] = hashlib.sha256(
            json.dumps(event, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:32]
        out.events.append(event)
    return out


MONTH_NAMES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip
QUERIES = (
    "jornadas gastronómicas Navarra {mes} {año}",
    "semana gastronómica Navarra {mes} {año}",
    "fiestas de los pueblos de Navarra {mes} {año}",
    "ferias en Navarra {mes} {año}",
)


def queries(day: date, recurring: list[dict[str, Any]]) -> list[str]:
    months = [(day.year, day.month), ((day.year + day.month // 12), day.month % 12 + 1)]
    out: list[str] = []
    for year, month in months:
        for template in QUERIES:
            out.append(template.format(mes=MONTH_NAMES[month - 1], año=year))
    near = {month for _, month in months}
    for one in recurring:
        if one.get("month") in near and one.get("title"):
            year = next(year for year, month in months if month == one["month"])
            out.append(f"{one['title']} {year} fechas")
    return list(dict.fromkeys(out))


async def search_pages(client: httpx.AsyncClient, query: str) -> list[str]:
    from hub.ai.tools import Web

    web = Web(client)
    if web.searcher is None:
        return []
    try:
        found = await web.search(query)
    except (httpx.HTTPError, ValueError) as error:
        raise SourceError(f"web search failed ({type(error).__name__})", transient=True) from error
    urls: list[str] = []
    for result in found:
        url = result.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    return urls


def due(config: dict[str, Any], _now: datetime) -> bool:
    return bool(config.get("search_now"))


def _week(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


RECURRING = """
    select distinct on (lower(payload->>'title'))
        payload->>'title' as title, (payload->>'starts_on')::date as starts_on
    from hub.events
    where type = 'leisure.event' and payload->>'connection' = :connection
      and (payload->>'recurring')::boolean
    order by lower(payload->>'title'), ts desc
    limit 40
"""


async def recall(database: Any, connection: Any) -> dict[str, Any]:
    from sqlalchemy import text

    rows = await database.execute(text(RECURRING), {"connection": str(connection.id)})
    return {"recurring": [{"title": row.title, "month": row.starts_on.month} for row in rows]}


def today() -> date:
    return datetime.now(zone()).date()


def _usage(config: dict[str, Any], day: date) -> dict[str, Any]:
    used = dict(config.get("usage") or {})
    if used.get("day") != day.isoformat():
        used = {"day": day.isoformat(), "calls": 0}
    return used


def _said(discarded: dict[str, int]) -> str:
    return ", ".join(f"{reason} ({count})" for reason, count in sorted(discarded.items()))


async def sync(client: httpx.AsyncClient, secrets: dict[str, str], connection: Any) -> Fetched:
    config = connection.config or {}
    limit = int(config.get("daily_calls") or DAILY_CALLS)
    now = datetime.now(zone())
    day = today()
    seen: dict[str, str] = dict(config.get("seen") or {})
    usage = _usage(config, day)
    events: list[dict[str, Any]] = []
    problems: list[str] = []
    discarded: dict[str, int] = {}
    counts = {"read": 0, "unchanged": 0}
    stop = False

    async def read_page(url: str, name: str) -> None:
        nonlocal stop
        try:
            got = await download(client, url, name)
        except SourceError as error:
            problems.append(str(error))
            return
        if seen.get(url) == got.digest:
            counts["unchanged"] += 1
            return
        said: list[dict[str, Any]] = []
        parts = 1
        while True:
            texts = [got.text] if parts == 1 else pieces(got.text, parts)
            said = []
            try:
                for text in texts:
                    if usage["calls"] >= limit:
                        problems.append(
                            f"today's budget is spent ({limit} reads): it goes on tomorrow"
                        )
                        stop = True
                        return
                    usage["calls"] += 1
                    piece = Read(url=got.url, name=got.name, text=text, links=got.links)
                    said.extend(await ask_model(prompt(piece, day)))
                break
            except Cut as error:
                if parts * 2 > MAX_PIECES:
                    problems.append(f"{got.name}: {error}, not even in {parts} pieces")
                    return
                parts *= 2
            except SourceError as error:
                problems.append(f"{got.name}: {error}")
                stop = isinstance(error, Unreadable)
                return
        checked = check(said, got, str(connection.id), day)
        for reason, count in checked.discarded.items():
            discarded[reason] = discarded.get(reason, 0) + count
        events.extend(
            {
                "ts": now.isoformat(),
                "type": EVENT,
                "payload": event,
                "dedup_hash": f"leisure:{connection.id}:{event['key']}:{event['fingerprint']}",
            }
            for event in checked.events
        )
        seen[url] = got.digest
        counts["read"] += 1

    fixed = config.get(PAGES) or []
    for page in fixed:
        await read_page(page[URL], page.get(NAME) or page[URL])
        if stop:
            break

    searched = 0
    state: dict[str, Any] = {}
    if not stop and due(config, now):
        week = _week(day)
        weekly = int(config.get("weekly_searches") or WEEKLY_SEARCHES)
        spent = dict(config.get("searches") or {})
        if spent.get("week") != week:
            spent = {"week": week, "count": 0}
        known = {page[URL] for page in fixed}
        recalled = getattr(connection, "recalled", None) or {}
        for query in queries(day, recalled.get("recurring") or []):
            if spent["count"] >= weekly:
                problems.append(f"this week's search budget is spent ({weekly})")
                break
            spent["count"] += 1
            try:
                found = await search_pages(client, query)
            except SourceError as error:
                problems.append(f"search '{query}': {error}")
                if isinstance(error, Unreadable):
                    stop = True
                    break
                continue
            searched += 1
            for url in [one for one in found if one not in known][:PAGES_PER_SEARCH]:
                known.add(url)
                await read_page(url, urlsplit(url).netloc.removeprefix("www."))
                if stop:
                    break
            if stop:
                break
        state = {"searches": spent, "searched_at": now.isoformat(), "search_now": False}
    read, unchanged = counts["read"], counts["unchanged"]
    note = f"{read} read, {unchanged} unchanged, {len(events)} event(s)"
    if searched:
        note += f"; {searched} search(es)"
    if discarded:
        note += f"; discarded: {_said(discarded)}"
    return Fetched(
        events,
        problem=f"{'; '.join(problems)} · {note}" if problems else None,
        note=note,
        state={"seen": seen, "usage": usage, **state},
    )


SOURCES = (
    Provider(
        id=PROVIDER,
        name="Agendas",
        category="leisure",
        description="What is on in Pamplona and Navarre, read from the pages of its agendas by "
        "the AI layer: Baluarte, the City Council, Cultura Navarra, Turismo de Navarra and any "
        "you add. Only what is on the page goes in. Plugged in from Outings.",
        capabilities=("sync",),
        secrets=(),
        settings=(
            Setting(PAGES, "Agendas", "The starting ones: baluarte, pamplona, cultura, turismo."),
            Setting(URL, "Address", "Another agenda's, starting with https://."),
            Setting(
                SEARCH,
                "Search every week",
                "true to search the web for what is in no agenda (needs web search configured).",
            ),
        ),
        emits=(EVENT,),
        available=True,
        schedule="30 2 * * *",
        offer=Offer(
            title="Pamplona and Navarre agenda",
            subtitle="Concerts, theatre, exhibitions, food weeks and festivities",
            tone=5,
            many=True,
            group="leisure",
            name="Navarre agenda",
            asks=(
                Ask(
                    PAGES,
                    "checks",
                    "Agendas",
                    choices=tuple(Choice(page.key, page.name) for page in START),
                    defaults=tuple(page.key for page in START),
                    help="The AI layer configured in Connections reads them. Searching the web "
                    "for what is in no agenda happens when you refresh. You can add any other "
                    "agenda later.",
                ),
            ),
        ),
        sync=Sync("agenda", sync, recall=recall),
        normalise=normalise,
        clean=clean_settings,
    ),
)
