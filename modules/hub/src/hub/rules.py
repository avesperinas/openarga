from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import date
from decimal import Decimal
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Any

from hub import extractors

FACTS = ("balance", "deposit", "withdrawal")
MAX_RULES = 30
EXTRACTOR = "rules"

AMOUNT = re.compile(
    r"^\s*[:=\-–]?\s*(?:EUR|€)?\s*(?P<amount>[-−+]?\s?\d{1,3}(?:[.  ]\d{3})+(?:,\d{1,2})?"
    r"|[-−+]?\s?\d+(?:,\d{1,2})?)(?![.,]?\d)",
    re.IGNORECASE,
)


class Invalid(ValueError):
    pass


def slug(*parts: str) -> str:
    raw = " ".join(parts)
    plain = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:60] or "producto"


def text_field(raw: dict[str, Any], key: str, label: str, low: int, high: int) -> str:
    value = re.sub(r"\s+", " ", str(raw.get(key) or "")).strip()
    if not low <= len(value) <= high:
        if low and not value:
            raise Invalid(f"falta {label}")
        raise Invalid(f"{label} va de {low} a {high} caracteres")
    return value


def clean(raw: dict[str, Any]) -> dict[str, str]:
    fact = str(raw.get("fact") or "")
    if fact not in FACTS:
        raise Invalid("el importe es el valor, una aportación o una retirada")
    rule_id = str(raw.get("id") or "")
    if not re.fullmatch(r"[a-f0-9]{8,32}", rule_id):
        rule_id = secrets.token_hex(6)
    return {
        "id": rule_id,
        "entity": text_field(raw, "entity", "la entidad", 1, 80),
        "product": text_field(raw, "product", "el producto", 1, 80),
        "sender": text_field(raw, "sender", "el remitente", 3, 200),
        "subject": text_field(raw, "subject", "el asunto", 0, 200),
        "anchor": text_field(raw, "anchor", "el texto de antes del importe", 2, 120),
        "fact": fact,
    }


def clean_all(raw: list[Any]) -> list[dict[str, str]]:
    if len(raw) > MAX_RULES:
        raise Invalid(f"como mucho {MAX_RULES} reglas en un buzón")
    cleaned = [clean(item if isinstance(item, dict) else {}) for item in raw]
    ids = [rule["id"] for rule in cleaned]
    if len(set(ids)) != len(ids):
        raise Invalid("dos reglas con el mismo id")
    return cleaned


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def day_of(message: EmailMessage) -> date:
    try:
        return parsedate_to_datetime(str(message["date"])).date()
    except (TypeError, ValueError) as error:
        raise extractors.ExtractorError("el correo no dice de qué día es") from error


def amount_after(body: str, anchor: str) -> Decimal:
    found = re.search(re.escape(flat(anchor)), flat(body), re.IGNORECASE)
    if found is None:
        raise extractors.ExtractorError(f"no aparece '{anchor}'")
    tail = flat(body)[found.end() : found.end() + 60]
    matched = AMOUNT.match(tail)
    if matched is None:
        raise extractors.ExtractorError(f"detrás de '{anchor}' no hay un importe: '{tail[:30]}'")
    raw = re.sub(r"[\s ]", "", matched["amount"]).replace("−", "-").replace("+", "")
    return extractors.euros(raw)


def facts_of(rule: dict[str, str], message: EmailMessage) -> list[extractors.Fact]:
    on = day_of(message)
    amount = amount_after(extractors.body_text(message), rule["anchor"])
    account = slug(rule["entity"], rule["product"])
    if rule["fact"] == "balance":
        return [extractors.Balance(account=account, name=rule["product"], on=on, amount=amount)]
    signed = abs(amount) if rule["fact"] == "deposit" else -abs(amount)
    return [
        extractors.Movement(
            account=account,
            booked_on=on,
            amount=signed,
            description="Aportación" if signed > 0 else "Retirada",
            kind=rule["fact"],
            nature="contribution",
        )
    ]


def extractor_of(rule: dict[str, str]) -> extractors.Extractor:
    return extractors.Extractor(
        id=EXTRACTOR,
        entity=rule["entity"],
        category="finance",
        sender=re.compile(re.escape(rule["sender"]), re.IGNORECASE),
        subject=re.compile(re.escape(rule["subject"]), re.IGNORECASE),
        parse=lambda message: facts_of(rule, message),
    )


def of(config: dict[str, Any]) -> list[dict[str, str]]:
    found = []
    for raw in config.get("rules") or []:
        try:
            found.append(clean(raw))
        except Invalid:
            continue
    return found
