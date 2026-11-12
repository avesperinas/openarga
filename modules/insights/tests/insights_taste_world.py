from __future__ import annotations

import base64
import json
from typing import Any

import httpx

PARAGRAPH = (
    "En el año 371 antes de nuestra era, en la llanura de Leuctra, un ejército tebano rompió la "
    "formación espartana con una columna de cincuenta filas en el ala izquierda. Epaminondas "
    "concentró allí su fuerza y dejó el resto atrás, en escalón, para que llegara tarde al choque. "
    "Fue la primera derrota de Esparta en campo abierto en generaciones y cambió el equilibrio de "
    "Grecia para siempre."
)


def pill(run_key: str, **overrides: Any) -> dict[str, Any]:
    sections = [
        {"title": f"Sección {n}", "text": "\n\n".join([PARAGRAPH] * 4)} for n in range(1, 4)
    ]
    return {
        "run_key": run_key,
        "family_key": "historia",
        "topic": "La batalla de Leuctra",
        "headline": "La columna que rompió Esparta",
        "lead": PARAGRAPH,
        "sections": sections,
        "to_tell": "Esparta no había perdido una batalla campal en siglos antes de Leuctra.",
        "to_think": "¿Por qué una innovación táctica tan sencilla tardó tanto en llegar?",
        "branches": [
            {"title": "El Batallón Sagrado de Tebas", "why": "150 parejas que decidieron batallas"},
            {"title": "Epaminondas", "why": "El general que enseñó a Filipo de Macedonia"},
            {"title": "La caída de Esparta", "why": "De Leuctra a la irrelevancia"},
        ],
        "sources": [
            {
                "title": "Batalla de Leuctra",
                "url": "https://es.wikipedia.org/wiki/Batalla_de_Leuctra",
            }
        ],
    } | overrides


def facts(day: str, count: int = 5) -> dict[str, Any]:
    return {
        "day": day,
        "facts": [
            {
                "family_key": "ciencia",
                "text": f"El dato número {n} es cierto, sorprendente y lleva su fuente comprobada.",
                "source": {"title": "Fuente", "url": f"https://example.org/dato/{n}"},
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
                "title": "Las legiones malditas",
                "authors": ["Santiago Posteguillo"],
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
                "creators": ["Alejandro Amenábar"],
                "wikipedia": "https://es.wikipedia.org/wiki/%C3%81gora_(pel%C3%ADcula)",
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
            return httpx.Response(503, json={"detail": "Hub está caído"})
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
        return httpx.Response(404, json={"detail": f"nadie sirve {capability}"})
