from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

NOISE_PREFIXES = (
    "compra en",
    "compra tarjeta",
    "compra",
    "pago en",
    "pago tarjeta",
    "pago",
    "recibo",
    "adeudo",
    "cargo en",
    "cargo",
    "tarj",
    "tarjeta",
    "movimiento",
)

LEGAL_FORMS = frozenset(
    {"sa", "sl", "sau", "slu", "sll", "srl", "sc", "scp", "coop", "sociedad", "limitada", "anonima"}
)

STOPWORDS = frozenset({"el", "la", "los", "las", "un", "una", "de", "del", "y", "en", "al", "a"})

GENERIC_TOKENS = frozenset(
    {
        "supermercado",
        "supermercados",
        "superm",
        "super",
        "supm",
        "market",
        "shopping",
        "tienda",
        "comercial",
        "farmacia",
        "parafarmacia",
        "bar",
        "cafeteria",
        "cafe",
        "restaurante",
        "rest",
        "panaderia",
        "pasteleria",
        "libreria",
        "papeleria",
        "gasolinera",
        "estacion",
        "servicio",
        "carburantes",
        "talleres",
        "taller",
        "clinica",
        "dental",
        "centro",
        "central",
        "online",
        "shop",
        "store",
        "es",
        "km",
    }
)

AUTO_MERGE_CONFIDENCE = 0.8

MIN_STORE_DIGITS = 2
MIN_TRUNCATION = 12

_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_LETTERS_OR_DIGITS = re.compile(r"[a-z]+|\d+")


@dataclass(frozen=True)
class Normalised:
    original: str
    text: str
    alpha: tuple[str, ...]
    numeric: tuple[str, ...]
    distinctive: frozenset[str]


@dataclass(frozen=True)
class Match:
    rule: str
    confidence: float
    evidence: str


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _strip_noise_prefix(value: str) -> str:
    for prefix in NOISE_PREFIXES:
        if value.startswith(f"{prefix} "):
            return value[len(prefix) + 1 :]
    return value


def normalise(alias: str) -> Normalised:
    flattened = _NOT_ALPHANUMERIC.sub(" ", _strip_accents(alias).lower()).strip()
    flattened = _strip_noise_prefix(flattened)

    tokens = [run for token in flattened.split() for run in _LETTERS_OR_DIGITS.findall(token)]
    alpha = tuple(
        token for token in tokens if token.isalpha() and len(token) > 1 and token not in LEGAL_FORMS
    )
    numeric = tuple(token.lstrip("0") or "0" for token in tokens if token.isdigit())
    distinctive = frozenset(
        token for token in alpha if token not in STOPWORDS and token not in GENERIC_TOKENS
    )

    return Normalised(
        original=alias,
        text=" ".join(alpha),
        alpha=alpha,
        numeric=numeric,
        distinctive=distinctive,
    )


def _shared_store_number(left: Normalised, right: Normalised) -> str | None:
    shared = {
        number
        for number in set(left.numeric) & set(right.numeric)
        if len(number) >= MIN_STORE_DIGITS
    }
    return min(shared) if shared else None


def match(left: Normalised, right: Normalised) -> Match | None:
    if not left.distinctive or not right.distinctive:
        return None

    shared_distinctive = left.distinctive & right.distinctive
    store = _shared_store_number(left, right)

    if left.text == right.text and left.numeric == right.numeric:
        return Match("identical", 0.99, f"misma forma normalizada: '{left.text}'")

    if left.text == right.text:
        return Match(
            "same_name_other_store",
            0.85,
            f"misma forma normalizada '{left.text}', establecimientos "
            f"{sorted(set(left.numeric) ^ set(right.numeric))}",
        )

    if shared_distinctive:
        short, long = sorted((left.text, right.text), key=len)
        if len(short) >= MIN_TRUNCATION and long.startswith(short):
            return Match("truncated", 0.9, f"'{long}' empieza por '{short}'")

        if store:
            return Match(
                "same_store_number",
                0.8,
                f"establecimiento {store} y token propio {sorted(shared_distinctive)}",
            )

        smaller, larger = sorted((left.distinctive, right.distinctive), key=len)
        if len(smaller) >= 2 and smaller <= larger:
            return Match(
                "token_subset", 0.75, f"tokens propios {sorted(smaller)} contenidos en el otro"
            )

        if len(shared_distinctive) >= 2:
            return Match(
                "shared_tokens", 0.7, f"tokens propios compartidos {sorted(shared_distinctive)}"
            )

    return None


def compare(left: str, right: str) -> Match | None:
    return match(normalise(left), normalise(right))
