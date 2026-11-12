from __future__ import annotations

import unicodedata

RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("comic", ("comic", "graphic novel", "manga", "historieta", "novela grafica")),
    ("poetry", ("poetry", "poesia", "poems", "poemas")),
    (
        "fantasy_scifi",
        ("fantasy", "science fiction", "fantasia", "ciencia ficcion", "sci-fi", "dystopia"),
    ),
    (
        "crime",
        ("detective", "mystery", "crime", "thriller", "policiaca", "novela negra", "suspense"),
    ),
    ("biography", ("biography", "autobiography", "memoir", "biografia", "memorias")),
    ("novel", ("fiction", "novel", "novela", "ficcion", "narrativa")),
    (
        "business",
        (
            "business",
            "economics",
            "management",
            "entrepreneur",
            "leadership",
            "negocio",
            "empresa",
            "economia",
            "finanzas",
        ),
    ),
    (
        "science",
        (
            "science",
            "physics",
            "biology",
            "mathematics",
            "astronomy",
            "chemistry",
            "neuroscience",
            "ciencia",
            "fisica",
            "biologia",
        ),
    ),
    ("history", ("history", "historia")),
    (
        "essay",
        ("essay", "ensayo", "philosophy", "filosofia", "psychology", "psicologia", "self-help"),
    ),
)


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def propose(subjects: list[str]) -> str:
    haystack = " | ".join(_plain(subject) for subject in subjects)
    for genre, needles in RULES:
        if any(needle in haystack for needle in needles):
            return genre
    return "other"
