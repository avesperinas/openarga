from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(bare.split())


def key(name: str) -> str:
    return fold(name)


def clean(name: str) -> str:
    words = " ".join(name.split())
    return words[:1].upper() + words[1:]


def starts_a_word(needle: str, name: str) -> bool:
    wanted = fold(needle)
    return bool(wanted) and f" {wanted}" in f" {fold(name)}"
