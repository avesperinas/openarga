from __future__ import annotations

import asyncio
import contextlib
import email
import email.policy
import imaplib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx

from hub import extractors, rules
from hub.declare import Provider, Secret, Setting, Sync
from hub.providers import Fetched, SourceError

BALANCE = "finance.balance"
MOVEMENT = "finance.movement"
ACCOUNT = "finance.account"
PASSWORD = "password"

FIRST_WINDOW = timedelta(days=365)
OVERLAP = timedelta(days=10)
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Header:
    uid: str
    sender: str
    subject: str
    received: datetime | None


class Mailbox(Protocol):
    def headers(self, since: date) -> list[Header]: ...

    def message(self, uid: str) -> EmailMessage: ...

    def close(self) -> None: ...


class Imap:
    def __init__(self, host: str, port: int, username: str, password: str, folder: str) -> None:
        try:
            self.client = imaplib.IMAP4_SSL(host, port, timeout=TIMEOUT_SECONDS)
            self.client.login(username, password)
            status, _ = self.client.select(folder, readonly=True)
        except (OSError, imaplib.IMAP4.error) as error:
            raise SourceError(
                f"El buzón no deja entrar: {error}", transient=isinstance(error, OSError)
            ) from error
        if status != "OK":
            raise SourceError(f"El buzón no tiene la carpeta '{folder}'")

    def headers(self, since: date) -> list[Header]:
        day = f"{since.day:02d}-{MONTHS[since.month - 1]}-{since.year}"
        status, found = self.client.uid("search", None, f"SINCE {day}")
        if status != "OK":
            raise SourceError(f"El buzón no deja buscar: {found}")
        uids = found[0].split() if found and found[0] else []
        result = []
        for uid in uids:
            status, data = self.client.uid(
                "fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            )
            if status != "OK" or not data or not isinstance(data[0], tuple):
                continue
            parsed = email.message_from_bytes(data[0][1], policy=email.policy.default)
            result.append(header_of(uid.decode(), parsed))
        return result

    def message(self, uid: str) -> EmailMessage:
        status, data = self.client.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK" or not data or not isinstance(data[0], tuple):
            raise SourceError(f"El buzón no da el mensaje {uid}")
        parsed = email.message_from_bytes(data[0][1], policy=email.policy.default)
        return parsed  # type: ignore[return-value]

    def close(self) -> None:
        with contextlib.suppress(OSError, imaplib.IMAP4.error):
            self.client.logout()


def header_of(uid: str, parsed: Any) -> Header:
    try:
        received = parsedate_to_datetime(parsed["date"]) if parsed["date"] else None
    except (TypeError, ValueError):
        received = None
    return Header(uid, str(parsed["from"] or ""), str(parsed["subject"] or ""), received)


Opener = Callable[[dict[str, Any], str], Mailbox]


def open_imap(config: dict[str, Any], password: str) -> Mailbox:
    return Imap(
        config["host"],
        int(config.get("port") or 993),
        config["username"],
        password,
        config.get("folder") or "INBOX",
    )


OPENER: list[Opener] = [open_imap]


def normalise(key: str, raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("falta la contraseña")
    return value


def clean_settings(raw: dict[str, Any]) -> dict[str, Any]:
    host = str(raw.get("host") or "").strip()
    username = str(raw.get("username") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9.-]{3,253}", host):
        raise ValueError("el servidor IMAP es un nombre como imap.gmail.com")
    if not username or len(username) > 254:
        raise ValueError("falta el usuario del buzón, normalmente su dirección")
    try:
        port = int(raw.get("port") or 993)
    except (TypeError, ValueError) as error:
        raise ValueError("el puerto es un número, normalmente 993") from error
    if not 1 <= port <= 65535:
        raise ValueError("el puerto es un número, normalmente 993")
    folder = str(raw.get("folder") or "INBOX").strip() or "INBOX"
    return {"host": host, "port": port, "username": username, "folder": folder}


def midnight(day: date) -> str:
    return datetime.combine(day, datetime.min.time(), UTC).isoformat()


def account_key(extractor: extractors.Extractor, account: str) -> str:
    return f"mail:{extractor.id}:{account}"


def events_of(
    connection: Any, extractor: extractors.Extractor, facts: list[extractors.Fact]
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    accounts: dict[str, extractors.Fact] = {}
    for fact in facts:
        key = account_key(extractor, fact.account)
        accounts.setdefault(key, fact)
        if isinstance(fact, extractors.Balance):
            found.append(
                {
                    "ts": midnight(fact.on),
                    "type": BALANCE,
                    "payload": {
                        "account": key,
                        "name": fact.name,
                        "kind": fact.kind,
                        "account_currency": fact.currency,
                        "on": fact.on.isoformat(),
                        "amount": str(fact.amount),
                        "currency": fact.currency,
                    },
                    "dedup_hash": extractors.dedup(extractor.id, fact.account, fact.on.isoformat()),
                }
            )
        else:
            identity = fact.reference or f"{fact.booked_on.isoformat()}:{fact.amount}:{fact.kind}"
            found.append(
                {
                    "ts": midnight(fact.booked_on),
                    "type": MOVEMENT,
                    "payload": {
                        "account": key,
                        "reference": identity,
                        "booked_on": fact.booked_on.isoformat(),
                        "value_on": None,
                        "amount": str(fact.amount),
                        "currency": fact.currency,
                        "description": fact.description,
                        "counterparty": extractor.entity,
                        "raw_descriptor": None,
                        **({"nature": fact.nature} if fact.nature else {}),
                    },
                    "dedup_hash": extractors.dedup(extractor.id, fact.account, identity),
                }
            )
    for key, fact in accounts.items():
        found.append(
            {
                "ts": datetime.now(UTC).isoformat(),
                "type": ACCOUNT,
                "payload": {
                    "connection": str(connection.id),
                    "bank": extractor.entity,
                    "account": key,
                    "name": getattr(fact, "name", extractor.entity),
                    "iban_tail": None,
                    "kind": getattr(fact, "kind", "investment"),
                    "currency": fact.currency,
                },
                "dedup_hash": f"account:{connection.id}:{key}"[: extractors.DEDUP_LIMIT],
            }
        )
    return found


def readers(config: dict[str, Any]) -> list[extractors.Extractor]:
    return [*map(rules.extractor_of, rules.of(config)), *extractors.EXTRACTORS.values()]


def announced(connection: Any) -> list[dict[str, Any]]:
    found = {}
    for rule in rules.of(connection.config or {}):
        key = f"mail:{rules.EXTRACTOR}:{rules.slug(rule['entity'], rule['product'])}"
        found.setdefault(
            key,
            {
                "ts": datetime.now(UTC).isoformat(),
                "type": ACCOUNT,
                "payload": {
                    "connection": str(connection.id),
                    "bank": rule["entity"],
                    "account": key,
                    "name": rule["product"],
                    "iban_tail": None,
                    "kind": "investment",
                    "currency": "EUR",
                },
                "dedup_hash": f"account:{connection.id}:{key}"[: extractors.DEDUP_LIMIT],
            },
        )
    return list(found.values())


def read(mailbox: Mailbox, since: date, connection: Any) -> Fetched:
    events: list[dict[str, Any]] = announced(connection)
    problems: list[str] = []
    found = readers(connection.config or {})
    for header in mailbox.headers(since):
        for extractor in found:
            if not extractor.matches(header.sender, header.subject):
                continue
            when = f"{header.received:%d/%m/%Y}" if header.received else "sin fecha"
            try:
                facts = extractor.parse(mailbox.message(header.uid))
            except extractors.ExtractorError as error:
                problems.append(f"{extractor.entity} no entiende su correo del {when}: {error}")
                continue
            if not facts:
                problems.append(f"{extractor.entity} no encuentra nada en su correo del {when}")
            events.extend(events_of(connection, extractor, facts))
    return Fetched(events, problem="; ".join(problems) or None)


TRIAL_WINDOW = timedelta(days=180)
TRIAL_LIMIT = 8


def trial(config: dict[str, Any], password: str, rule: dict[str, str]) -> list[dict[str, Any]]:
    extractor = rules.extractor_of(rule)
    mailbox = OPENER[0](config, password)
    try:
        since = (datetime.now(UTC) - TRIAL_WINDOW).date()
        matching = [
            header
            for header in mailbox.headers(since)
            if extractor.matches(header.sender, header.subject)
        ]
        matching.sort(key=lambda header: header.received or datetime.min.replace(tzinfo=UTC))
        results = []
        for header in reversed(matching[-TRIAL_LIMIT:]):
            row: dict[str, Any] = {
                "on": header.received.date().isoformat() if header.received else None,
                "subject": header.subject[:140],
                "amount": None,
                "problem": None,
            }
            try:
                facts = extractor.parse(mailbox.message(header.uid))
                row["amount"] = str(facts[0].amount)
            except extractors.ExtractorError as error:
                row["problem"] = str(error)
            results.append(row)
        return results
    finally:
        mailbox.close()


async def sync(client: httpx.AsyncClient, secrets: dict[str, str], connection: Any) -> Fetched:
    config = connection.config or {}
    last_ok = connection.last_ok
    now = datetime.now(UTC)
    since = (now - FIRST_WINDOW if last_ok is None else last_ok - OVERLAP).date()

    def work() -> Fetched:
        mailbox = OPENER[0](config, secrets[PASSWORD])
        try:
            return read(mailbox, since, connection)
        finally:
            mailbox.close()

    got = await asyncio.to_thread(work)
    if not readers(config) and not got.problem:
        got.note = "Sin reglas todavía: el buzón se lee cuando pongas una en su ficha."
    return got


SOURCES = (
    Provider(
        id="imap",
        name="Correo",
        category="finance",
        description="Un buzón dedicado al que reenvías los avisos de entidades sin API, como "
        "roboadvisors o cuentas de ahorro. Solo lectura, y solo los correos de las entidades que "
        "arga sabe leer.",
        capabilities=("sync",),
        secrets=(
            Secret(
                "password",
                "Contraseña de aplicación",
                "La que da tu proveedor de correo para una aplicación, no la de siempre. Nunca las "
                "claves de tu banco o de tu gestora: aquí solo se lee correo.",
            ),
        ),
        settings=(
            Setting("host", "Servidor IMAP", "Por ejemplo imap.gmail.com."),
            Setting("port", "Puerto", "Casi siempre 993.", "993"),
            Setting("username", "Usuario", "La dirección del buzón dedicado."),
            Setting("folder", "Carpeta", "Donde llegan los reenvíos.", "INBOX"),
        ),
        emits=("finance.movement", "finance.balance", "finance.account"),
        available=True,
        schedule="0 * * * *",
        sync=Sync("mail", sync),
        normalise=normalise,
        clean=clean_settings,
    ),
)
