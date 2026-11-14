from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

import httpx

from hub.declare import Provider, Secret
from hub.providers import USER_AGENT

OPENLIBRARY_SEARCH = "https://openlibrary.org/search.json"
OPENLIBRARY_COVER = "https://covers.openlibrary.org/b/id/{ref}-L.jpg"
GOOGLE_SEARCH = "https://www.googleapis.com/books/v1/volumes"
GOOGLE_COVER = "https://books.google.com/books/content"

OPENLIBRARY_FIELDS = ",".join(
    (
        "key",
        "title",
        "subtitle",
        "author_name",
        "number_of_pages_median",
        "first_publish_year",
        "subject",
        "cover_i",
        "editions",
        "editions.key",
        "editions.title",
        "editions.subtitle",
        "editions.isbn",
        "editions.language",
        "editions.number_of_pages_median",
        "editions.cover_i",
        "editions.publish_year",
    )
)

COVER_MAX_BYTES = 2 * 1024 * 1024
SUBJECTS = 12


def timeout() -> float:
    return float(os.environ.get("BOOK_SOURCE_TIMEOUT_SECONDS", "10"))


class SourceFailed(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    source: str
    source_ref: str
    title: str
    subtitle: str | None = None
    authors: list[str] = field(default_factory=list)
    isbn13: str | None = None
    pages: int | None = None
    language: str | None = None
    year: int | None = None
    subjects: list[str] = field(default_factory=list)
    cover_ref: str | None = None


def _check13(first12: str) -> str:
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(first12))
    return str((10 - total % 10) % 10)


def isbn13(value: str) -> str | None:
    raw = re.sub(r"[\s\-]", "", value).upper()
    if len(raw) == 13 and raw.isdigit() and raw[:3] in ("978", "979"):
        return raw if _check13(raw[:12]) == raw[12] else None
    if len(raw) == 10 and re.fullmatch(r"[0-9]{9}[0-9X]", raw):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(raw))
        if total % 11:
            return None
        first12 = "978" + raw[:9]
        return first12 + _check13(first12)
    return None


def looks_like_isbn(query: str) -> str | None:
    return isbn13(query) if re.fullmatch(r"[\d\s\-Xx]{10,17}", query.strip()) else None


MARC = {
    "spa": "es",
    "eng": "en",
    "baq": "eu",
    "eus": "eu",
    "cat": "ca",
    "glg": "gl",
    "fre": "fr",
    "fra": "fr",
    "ger": "de",
    "deu": "de",
    "ita": "it",
    "por": "pt",
}


def _language(value: str | None) -> str | None:
    if not value:
        return None
    value = value.lower()
    if re.fullmatch(r"[a-z]{2}", value):
        return value
    return MARC.get(value)


def _year(value: object) -> int | None:
    match = re.search(r"\d{4}", str(value or ""))
    year = int(match.group()) if match else None
    return year if year and 1400 <= year <= 2200 else None


def _pages(value: object) -> int | None:
    try:
        pages = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    return pages if 0 < pages < 20000 else None


def _text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _openlibrary_candidate(work: dict, wanted_isbn: str | None) -> Candidate | None:
    editions = (work.get("editions") or {}).get("docs") or []
    edition = editions[0] if editions else {}
    title = _text(edition.get("title") or work.get("title"))
    if not title:
        return None
    isbns = [found for found in (isbn13(one) for one in edition.get("isbn") or []) if found]
    if wanted_isbn and (wanted_isbn in isbns or not isbns):
        chosen: str | None = wanted_isbn
    else:
        chosen = isbns[0] if isbns else None
    languages = edition.get("language") or []
    cover = edition.get("cover_i") or work.get("cover_i")
    years = edition.get("publish_year") or []
    ref = str(edition.get("key") or work.get("key") or "").rsplit("/", 1)[-1]
    if not ref:
        return None
    return Candidate(
        source="openlibrary",
        source_ref=ref,
        title=title,
        subtitle=_text(edition.get("subtitle") or work.get("subtitle")),
        authors=[name for name in (_text(a) for a in work.get("author_name") or []) if name],
        isbn13=chosen,
        pages=_pages(edition.get("number_of_pages_median") or work.get("number_of_pages_median")),
        language=_language(languages[0] if languages else None),
        year=_year(min(years) if years else work.get("first_publish_year")),
        subjects=[s for s in (_text(one) for one in work.get("subject") or []) if s][:SUBJECTS],
        cover_ref=str(cover) if cover else None,
    )


async def search_openlibrary(
    client: httpx.AsyncClient, query: str, limit: int = 10
) -> list[Candidate]:
    wanted = looks_like_isbn(query)
    try:
        response = await client.get(
            OPENLIBRARY_SEARCH,
            params={
                "q": f"isbn:{wanted}" if wanted else query,
                "lang": "es",
                "limit": limit,
                "fields": OPENLIBRARY_FIELDS,
            },
            headers={"user-agent": USER_AGENT},
            timeout=timeout(),
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as error:
        raise SourceFailed(f"Open Library no contestó: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("Open Library contestó algo que no es JSON") from error
    candidates = [_openlibrary_candidate(work, wanted) for work in payload.get("docs") or []]
    return [candidate for candidate in candidates if candidate is not None]


def _google_candidate(volume: dict) -> Candidate | None:
    info = volume.get("volumeInfo") or {}
    title = _text(info.get("title"))
    ref = str(volume.get("id") or "").strip()
    if not title or not ref:
        return None
    identifiers = {
        one.get("type"): one.get("identifier") for one in info.get("industryIdentifiers") or []
    }
    found = isbn13(identifiers.get("ISBN_13") or "") or isbn13(identifiers.get("ISBN_10") or "")
    return Candidate(
        source="google_books",
        source_ref=ref,
        title=title,
        subtitle=_text(info.get("subtitle")),
        authors=[name for name in (_text(a) for a in info.get("authors") or []) if name],
        isbn13=found,
        pages=_pages(info.get("pageCount")),
        language=_language(info.get("language")),
        year=_year(info.get("publishedDate")),
        subjects=[s for s in (_text(one) for one in info.get("categories") or []) if s][:SUBJECTS],
        cover_ref=ref if info.get("imageLinks") else None,
    )


async def search_google(
    client: httpx.AsyncClient, key: str, query: str, limit: int = 10
) -> list[Candidate]:
    if not key:
        raise SourceFailed("sin clave de Google Books: ponla en Hub")
    wanted = looks_like_isbn(query)
    try:
        response = await client.get(
            GOOGLE_SEARCH,
            params={
                "q": f"isbn:{wanted}" if wanted else query,
                "key": key,
                "maxResults": limit,
                "printType": "books",
                "langRestrict": "" if wanted else "es",
            },
            timeout=timeout(),
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (400, 403):
            raise SourceFailed("Google Books no acepta la clave: revísala en Hub") from error
        raise SourceFailed(f"Google Books contestó {error.response.status_code}") from error
    except httpx.HTTPError as error:
        raise SourceFailed(f"Google Books no contestó: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("Google Books contestó algo que no es JSON") from error
    candidates = [_google_candidate(volume) for volume in payload.get("items") or []]
    return [candidate for candidate in candidates if candidate is not None]


SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def image_type(body: bytes) -> str | None:
    for signature, kind in SIGNATURES:
        if body.startswith(signature):
            return kind
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return None


def cover_request(source: str, ref: str) -> tuple[str, dict[str, str]]:
    if source == "openlibrary":
        if not ref.isdigit():
            raise SourceFailed("esa no es una portada de Open Library")
        return OPENLIBRARY_COVER.format(ref=ref), {"default": "false"}
    if source == "google_books":
        if not re.fullmatch(r"[A-Za-z0-9_\-]{4,40}", ref):
            raise SourceFailed("esa no es una portada de Google Books")
        return GOOGLE_COVER, {"id": ref, "printsec": "frontcover", "img": "1", "zoom": "1"}
    raise SourceFailed(f"no hay portadas de '{source}'")


async def fetch_cover(client: httpx.AsyncClient, source: str, ref: str) -> tuple[bytes, str] | None:
    url, params = cover_request(source, ref)
    try:
        response = await client.get(
            url,
            params=params,
            headers={"user-agent": USER_AGENT},
            timeout=timeout(),
            follow_redirects=True,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SourceFailed(f"la portada no llegó: {type(error).__name__}") from error
    body = response.content
    if len(body) > COVER_MAX_BYTES:
        raise SourceFailed("la portada pesa demasiado")
    kind = image_type(body)
    if kind is None or len(body) < 1000:
        return None
    return body, kind


def normalise(key: str, raw: str) -> str:
    value = raw.strip()
    if not value or any(character.isspace() for character in value):
        raise ValueError("no parece una clave: pégala tal cual, sin espacios")
    return value


def as_dict(candidate: Candidate) -> dict:
    return asdict(candidate)


SOURCES = (
    Provider(
        id="openlibrary",
        name="Open Library",
        category="books",
        description="A book's details and cover, by title, author or ISBN, when "
        "you add it in Library. No key: it connects by itself the "
        "first time you search.",
        capabilities=("lookup",),
        serves=("books.search", "books.cover"),
        available=True,
        single=True,
    ),
    Provider(
        id="google_books",
        name="Google Books",
        category="books",
        description="The same as Open Library, and better with recent editions "
        "outside English. Both are asked at once.",
        capabilities=("lookup",),
        serves=("books.search", "books.cover"),
        secrets=(
            Secret(
                "api_key",
                "API key",
                "At console.cloud.google.com: create a project, enable the Books "
                "API and create an API key under Credentials. It is free.",
            ),
        ),
        available=True,
        single=True,
        normalise=normalise,
    ),
)
