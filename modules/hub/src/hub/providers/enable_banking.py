from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from hub import finance
from hub.declare import Provider, Secret, Sync
from hub.providers import Fetched, SourceError

MOVEMENT = "finance.movement"
DETAIL = "finance.movement_detail"
BALANCE = "finance.balance"
ACCOUNT = "finance.account"
SOURCE = "bank"
MERCHANT = "merchant"

APP_ID = "app_id"
PRIVATE_KEY = "private_key"
SESSION = "session"

LIFETIME_SECONDS = 3600
CONSENT_OVER = frozenset({"EXPIRED_SESSION", "CLOSED_SESSION", "REVOKED_SESSION"})
REDIRECT_NOT_ALLOWED = "REDIRECT_URI_NOT_ALLOWED"
DEFAULT_VALIDITY = timedelta(days=180)
FIRST_WINDOW = timedelta(days=365)
FALLBACK_WINDOW = timedelta(days=90)
OVERLAP = timedelta(days=10)
MIN_INTERVAL = timedelta(hours=5)
DAILY_BUDGET = 4
BALANCE_PREFERENCE = ("CLBD", "ITBD", "XPCD", "OPBD", "CLAV", "ITAV", "OPAV", "FWAV", "VALU")
DEDUP_LIMIT = 200
KINDS = {
    "CACC": "checking",
    "CASH": "checking",
    "TRAN": "checking",
    "SVGS": "savings",
    "CARD": "card",
}


def api_url() -> str:
    return os.environ.get("ENABLE_BANKING_URL", "https://api.enablebanking.com").rstrip("/")


class BankError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message

    @property
    def consent_over(self) -> bool:
        return self.code in CONSENT_OVER

    @property
    def transient(self) -> bool:
        return self.status >= 500 or self.status in (408, 429)

    def as_source_error(self) -> SourceError:
        return SourceError(
            f"El banco contesta {self.status} {self.code}: {self.message}",
            transient=self.transient and self.status != 429,
            rate_limited=self.status == 429,
            code="consent_over" if self.consent_over else None,
        )


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def token(app_id: str, private_key_pem: str, now: float | None = None) -> str:
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("la clave de Enable Banking tiene que ser RSA")
    issued = int(now if now is not None else time.time())
    header = {"typ": "JWT", "alg": "RS256", "kid": app_id}
    claims = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": issued,
        "exp": issued + LIFETIME_SECONDS,
    }
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64(signature)}"


PEM = re.compile(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", re.S)


def normalise_private_key(raw: str) -> str:
    found = PEM.search(raw.strip())
    if found is None:
        raise ValueError("no es una clave PEM: empieza por -----BEGIN PRIVATE KEY-----")
    label, body = found.group(1), re.sub(r"\s+", "", found.group(2))
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    pem = f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----\n"
    try:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
    except (ValueError, TypeError) as error:
        raise ValueError(
            "la clave no se puede leer; pégala entera, con su cabecera y su pie"
        ) from error
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("la clave de Enable Banking tiene que ser RSA")
    return pem


def normalise_app_id(raw: str) -> str:
    try:
        return str(UUID(raw.strip()))
    except ValueError as error:
        raise ValueError("el id de la aplicación es un UUID, como aparece en su panel") from error


def normalise(key: str, raw: str) -> str:
    if key == PRIVATE_KEY:
        return normalise_private_key(raw)
    if key == APP_ID:
        return normalise_app_id(raw)
    return raw.strip()


@dataclass(frozen=True)
class App:
    app_id: str = field(repr=False)
    private_key: str = field(repr=False)


class EnableBanking:
    def __init__(self, client: httpx.AsyncClient, app: App) -> None:
        self.client = client
        self.app = app

    async def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"authorization": f"Bearer {token(self.app.app_id, self.app.private_key)}"}
        try:
            response = await self.client.request(
                method, f"{api_url()}{path}", headers=headers, timeout=30.0, **kwargs
            )
        except httpx.HTTPError as error:
            raise BankError(503, "UNREACHABLE", type(error).__name__) from error
        if response.is_success:
            return response.json() if response.content else {}
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {}
        raise BankError(
            response.status_code,
            str(body.get("error") or body.get("code") or "UNKNOWN"),
            str(body.get("message") or body.get("detail") or response.text[:200]),
        )

    async def banks(self, country: str) -> list[dict[str, Any]]:
        return (await self._call("GET", "/aspsps", params={"country": country}))["aspsps"]

    async def authorise(
        self, bank: str, country: str, valid_until: str, state: str, redirect_url: str
    ) -> str:
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": bank, "country": country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": "personal",
        }
        return (await self._call("POST", "/auth", json=body))["url"]

    async def open_session(self, code: str) -> dict[str, Any]:
        return await self._call("POST", "/sessions", json={"code": code})

    async def balances(self, account_uid: str) -> list[dict[str, Any]]:
        return (await self._call("GET", f"/accounts/{account_uid}/balances"))["balances"]

    async def details(self, account_uid: str) -> dict[str, Any]:
        return await self._call("GET", f"/accounts/{account_uid}/details")

    async def transactions(self, account_uid: str, since: date) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        params: dict[str, str] = {"date_from": since.isoformat(), "transaction_status": "BOOK"}
        while True:
            page = await self._call("GET", f"/accounts/{account_uid}/transactions", params=params)
            found.extend(page.get("transactions") or [])
            following = page.get("continuation_key")
            if not following:
                return found
            params = {**params, "continuation_key": following}


def validity_for(bank: dict[str, Any], now: datetime) -> str:
    maximum = bank.get("maximum_consent_validity")
    validity = min(DEFAULT_VALIDITY, timedelta(seconds=maximum)) if maximum else DEFAULT_VALIDITY
    return (now + validity).isoformat()


def clean_iban(raw: Any) -> str | None:
    iban = re.sub(r"\s+", "", str(raw or "")).upper()
    return iban or None


def iban_of(account: dict[str, Any] | None) -> str | None:
    return clean_iban((account or {}).get("iban"))


def account_of(raw: dict[str, Any]) -> dict[str, Any]:
    iban = iban_of(raw.get("account_id")) or ""
    return {
        "uid": raw["uid"],
        "key": raw["identification_hash"],
        "name": raw.get("name") or raw.get("product") or "Cuenta",
        "currency": raw.get("currency") or "EUR",
        "iban_tail": iban[-4:] if iban else None,
        "iban": iban or None,
        "kind": KINDS.get(raw.get("cash_account_type") or "", "other"),
    }


def natural_key(account_key: str, fact: str) -> str:
    plain = f"{SOURCE}:{account_key}:{fact}"
    if len(plain) <= DEDUP_LIMIT:
        return plain
    digest = hashlib.sha256(account_key.encode()).hexdigest()
    return f"{SOURCE}:sha256-{digest}:{fact}"


def midnight(day: str) -> str:
    return datetime.combine(date.fromisoformat(day), datetime.min.time(), UTC).isoformat()


def account_event(connection: str, bank: str, account: dict[str, Any]) -> dict[str, Any]:
    fact = "account:iban" if account.get("iban") else "account"
    return {
        "ts": datetime.now(UTC).isoformat(),
        "type": ACCOUNT,
        "payload": {
            "connection": connection,
            "bank": bank,
            "account": account["key"],
            "name": account["name"],
            "iban_tail": account.get("iban_tail"),
            "iban": account.get("iban"),
            "kind": account.get("kind") or "other",
            "currency": account.get("currency") or "EUR",
        },
        "dedup_hash": f"account:{connection}:{natural_key(account['key'], fact)}"[:DEDUP_LIMIT],
    }


def movement_event(account: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any] | None:
    reference = raw.get("entry_reference") or raw.get("transaction_id")
    if not reference:
        return None
    outgoing = raw.get("credit_debit_indicator") == "DBIT"
    amount = raw["transaction_amount"]["amount"].lstrip("-")
    party = (raw.get("creditor") if outgoing else raw.get("debtor")) or {}
    other = (raw.get("creditor_account") if outgoing else raw.get("debtor_account")) or {}
    iban = "".join(str(other.get("iban") or "").split()).upper() or None
    remittance = [line for line in raw.get("remittance_information") or [] if line]
    booked = raw.get("booking_date") or raw.get("value_date") or raw.get("transaction_date")
    descriptor = party.get("name") or (remittance[0] if remittance else None)
    event: dict[str, Any] = {
        "ts": midnight(booked),
        "type": MOVEMENT,
        "payload": {
            "account": account["key"],
            "reference": reference,
            "booked_on": booked,
            "value_on": raw.get("value_date"),
            "amount": f"-{amount}" if outgoing else amount,
            "currency": raw["transaction_amount"]["currency"],
            "description": " ".join(remittance) or None,
            "counterparty": party.get("name"),
            "counterparty_iban": iban,
            "raw_descriptor": descriptor,
        },
        "dedup_hash": natural_key(account["key"], reference),
    }
    if descriptor:
        event["entity"] = {"alias": descriptor, "kind": MERCHANT}
    return event


def transaction_code(raw: dict[str, Any]) -> dict[str, str | None] | None:
    code = raw.get("bank_transaction_code") or {}
    found = {
        "code": code.get("code") or None,
        "sub_code": code.get("sub_code") or None,
        "description": code.get("description") or None,
    }
    return found if any(found.values()) else None


def detail_event(account: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any] | None:
    reference = raw.get("entry_reference") or raw.get("transaction_id")
    if not reference:
        return None
    outgoing = raw.get("credit_debit_indicator") == "DBIT"
    creditor = (raw.get("creditor") or {}).get("name") or None
    debtor = (raw.get("debtor") or {}).get("name") or None
    booked = raw.get("booking_date") or raw.get("value_date") or raw.get("transaction_date")
    return {
        "ts": midnight(booked),
        "type": DETAIL,
        "payload": {
            "account": account["key"],
            "reference": reference,
            "counterparty_iban": iban_of(
                raw.get("creditor_account") if outgoing else raw.get("debtor_account")
            ),
            "counterparty_name": creditor if outgoing else debtor,
            "creditor_name": creditor,
            "debtor_name": debtor,
            "bank_transaction_code": transaction_code(raw),
        },
        "dedup_hash": natural_key(account["key"], f"{reference}:detail"),
    }


def balance_event(
    account: dict[str, Any], balances: list[dict[str, Any]], today: date
) -> dict[str, Any] | None:
    ranked = sorted(
        (b for b in balances if b.get("balance_type") in BALANCE_PREFERENCE),
        key=lambda b: BALANCE_PREFERENCE.index(b["balance_type"]),
    )
    if not ranked:
        return None
    chosen = ranked[0]
    on = chosen.get("reference_date") or today.isoformat()
    return {
        "ts": midnight(on),
        "type": BALANCE,
        "payload": {
            "account": account["key"],
            "name": account["name"],
            "iban_tail": account.get("iban_tail"),
            "kind": account.get("kind") or "other",
            "account_currency": account.get("currency") or "EUR",
            "on": on,
            "amount": chosen["balance_amount"]["amount"],
            "currency": chosen["balance_amount"]["currency"],
            "balance_type": chosen["balance_type"],
        },
        "dedup_hash": natural_key(account["key"], on),
    }


def app_of(secrets: dict[str, str | None]) -> App:
    return App(secrets[APP_ID] or "", secrets[PRIVATE_KEY] or "")


async def learn_ibans(api: EnableBanking, accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    learned = []
    for account in accounts:
        if account.get("iban") or not account.get("uid"):
            learned.append(account)
            continue
        try:
            iban = iban_of((await api.details(account["uid"])).get("account_id"))
        except BankError as error:
            if error.consent_over:
                raise
            iban = None
        learned.append({**account, "iban": iban} if iban else account)
    return learned


async def sync(
    client: httpx.AsyncClient,
    secrets: dict[str, str],
    connection: Any,
    *,
    now: datetime | None = None,
) -> Fetched:
    now = now or datetime.now(UTC)
    api = EnableBanking(client, app_of(secrets))
    config = connection.config or {}
    last_ok = connection.last_ok
    whole = last_ok is None or not config.get("details_from")
    since = (now - FIRST_WINDOW if whole else last_ok - OVERLAP).date()
    events: list[dict[str, Any]] = []
    without_reference = 0
    try:
        before = config.get("accounts") or []
        accounts = await learn_ibans(api, before)
        for account, previous in zip(accounts, before, strict=True):
            if account.get("iban") and not previous.get("iban"):
                events.append(account_event(str(connection.id), config.get("bank", ""), account))
        for account in accounts:
            balance = balance_event(account, await api.balances(account["uid"]), now.date())
            if balance is not None:
                events.append(balance)
            try:
                raws = await api.transactions(account["uid"], since)
            except BankError as error:
                if not (whole and error.code == "WRONG_TRANSACTIONS_PERIOD"):
                    raise
                raws = await api.transactions(account["uid"], (now - FALLBACK_WINDOW).date())
            for raw in raws:
                event = movement_event(account, raw)
                if event is None:
                    without_reference += 1
                    continue
                events.append(event)
                detail = detail_event(account, raw)
                if detail is not None:
                    events.append(detail)
    except BankError as error:
        raise error.as_source_error() from error
    note = f"{without_reference} apuntes sin identidad del banco" if without_reference else None
    remembered = {"accounts": accounts} if accounts != before else {}
    if whole:
        remembered["details_from"] = since.isoformat()
    events = finance.enrich(events, config.get("bank", ""))
    return Fetched(events, note=note, config=remembered or None)


SOURCES = (
    Provider(
        id="enable_banking",
        name="Bancos (PSD2)",
        category="finance",
        description="Movimientos y saldos de tus cuentas y tarjetas, cuatro veces al día, por "
        "Enable Banking. Cada banco se autoriza con tu biometría y caduca cada pocos meses.",
        capabilities=("sync",),
        serves=("enable_banking.handoff",),
        secrets=(
            Secret(
                "app_id",
                "Id de la aplicación",
                "Da de alta tu aplicación en enablebanking.com (Restricted Production) y copia su "
                "id, el UUID de su panel.",
            ),
            Secret(
                "private_key",
                "Clave privada",
                "El .pem que descargaste al crear la aplicación: pégalo entero, con su cabecera y "
                "su pie.",
                multiline=True,
            ),
        ),
        emits=(
            "finance.movement",
            "finance.movement_detail",
            "finance.balance",
            "finance.account",
        ),
        available=True,
        schedule="0 */6 * * *",
        authorizes=True,
        shared=("app_id", "private_key"),
        daily_budget=4,
        source="bank",
        internal=("session",),
        sync=Sync("accounts", sync, policy="budget"),
        normalise=normalise,
    ),
)
