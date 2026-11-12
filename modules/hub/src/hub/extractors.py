from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from email.message import EmailMessage

DEDUP_LIMIT = 200


class ExtractorError(ValueError):
    pass


@dataclass(frozen=True)
class Balance:
    account: str
    name: str
    on: date
    amount: Decimal
    currency: str = "EUR"
    kind: str = "investment"


@dataclass(frozen=True)
class Movement:
    account: str
    booked_on: date
    amount: Decimal
    currency: str = "EUR"
    description: str | None = None
    reference: str | None = None
    kind: str = "movement"
    nature: str | None = None


Fact = Balance | Movement


@dataclass(frozen=True)
class Extractor:
    id: str
    entity: str
    category: str
    sender: re.Pattern[str]
    subject: re.Pattern[str]
    parse: Callable[[EmailMessage], list[Fact]]

    def matches(self, sender: str, subject: str) -> bool:
        return bool(self.sender.search(sender or "")) and bool(self.subject.search(subject or ""))


EXTRACTORS: dict[str, Extractor] = {}


def body_text(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        raise ExtractorError("el correo no tiene cuerpo")
    content = part.get_content()
    if part.get_content_subtype() == "html":
        content = re.sub(r"<[^>]+>", " ", content)
    return re.sub(r"[ \t\u00a0]+", " ", content)


def euros(raw: str) -> Decimal:
    cleaned = raw.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except ArithmeticError as error:
        raise ExtractorError(f"'{raw}' no es un importe") from error


def dedup(*parts: str) -> str:
    return ":".join(["mail", *parts])[:DEDUP_LIMIT]
