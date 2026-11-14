from __future__ import annotations

import base64
import json
from typing import Any

import httpx

PARAGRAPH = (
    "In the year 371 before our era, on the plain of Leuctra, a Theban army broke the Spartan "
    "formation with a column fifty ranks deep on its left wing. Epaminondas gathered his strength "
    "there and left the rest behind, in echelon, so that it would reach the clash late. It was the "
    "first defeat of Sparta in open battle for generations and it changed the balance of Greece "
    "forever."
)


def pill(run_key: str, **overrides: Any) -> dict[str, Any]:
    sections = [
        {"title": f"Section {n}", "text": "\n\n".join([PARAGRAPH] * 4)} for n in range(1, 4)
    ]
    return {
        "run_key": run_key,
        "family_key": "history",
        "topic": "The battle of Leuctra",
        "headline": "The column that broke Sparta",
        "lead": PARAGRAPH,
        "sections": sections,
        "to_tell": "Sparta had not lost a pitched battle in centuries before Leuctra.",
        "to_think": "Why did such a simple tactical innovation take so long to arrive?",
        "branches": [
            {"title": "The Sacred Band of Thebes", "why": "150 couples who decided battles"},
            {"title": "Epaminondas", "why": "The general who taught Philip of Macedon"},
            {"title": "The fall of Sparta", "why": "From Leuctra to irrelevance"},
        ],
        "sources": [
            {
                "title": "Battle of Leuctra",
                "url": "https://en.wikipedia.org/wiki/Battle_of_Leuctra",
            }
        ],
    } | overrides


def facts(day: str, count: int = 5) -> dict[str, Any]:
    return {
        "day": day,
        "facts": [
            {
                "family_key": "science",
                "text": f"Fact number {n} is true, surprising and carries its checked source.",
                "source": {"title": "Source", "url": f"https://example.org/fact/{n}"},
            }
            for n in range(1, count + 1)
        ],
    }


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAwS2OUAAAAABJRU5ErkJggg=="
)


class FakeKernel:
    def __init__(self) -> None:
        self.asked: list[tuple[str, dict]] = []
        self.books = [
            {
                "source": "openlibrary",
                "source_ref": "OL1M",
                "title": "The Cursed Legions",
                "authors": ["Synthetic Author"],
                "isbn13": "9788466648769",
                "pages": 720,
                "language": "es",
                "year": 2008,
                "cover_ref": "123",
            }
        ]
        self.podcasts = [
            {
                "id": "1",
                "title": "Fall of Civilizations",
                "show": "Paul Cooper",
                "url": "https://podcasts.apple.com/podcast/id1",
                "episodes": 20,
                "language": "en",
            }
        ]
        self.films = [
            {
                "id": "Q1",
                "title": "Agora",
                "year": 2009,
                "creators": ["A. Director"],
                "wikipedia": "https://en.wikipedia.org/wiki/Agora_(film)",
                "minutes": 127,
            }
        ]
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        capability = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        self.asked.append((capability, body))
        assert request.headers["x-arga-module"] == "insights"
        if self.down:
            return httpx.Response(503, json={"detail": "Hub is down"})
        if capability == "books.search":
            return httpx.Response(200, json={"candidates": self.books, "failed": []})
        if capability == "books.cover":
            return httpx.Response(
                200, json={"cover": base64.b64encode(PNG).decode(), "type": "image/png"}
            )
        if capability == "podcasts.search":
            return httpx.Response(200, json={"candidates": self.podcasts})
        if capability == "films.search":
            return httpx.Response(200, json={"candidates": self.films})
        if capability == "books.want":
            return httpx.Response(200, json={"book_id": "b1", "already": False})
        return httpx.Response(404, json={"detail": f"nobody serves {capability}"})
