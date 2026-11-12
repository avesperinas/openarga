from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from hub.declare import Provider, Secret, Sync
from hub.providers import SourceError

WINDOW_MS = 10_000
ANNOUNCE = "finance.account"
BALANCE = "finance.balance"
HOLDING = "finance.holding"
TRADE = "finance.trade"
PAGE = 100
ACCOUNT = "bitvavo"
LEGACY_SOURCE = "exchange"
CENT = Decimal("0.01")

API_KEY = "api_key"
API_SECRET = "api_secret"


def api_url() -> str:
    return os.environ.get("BITVAVO_URL", "https://api.bitvavo.com/v2").rstrip("/")


def normalise(raw: str) -> str:
    token = raw.strip()
    if not re.fullmatch(r"[A-Za-z0-9]{16,256}", token):
        raise ValueError("no parece una clave de API: pégala tal cual, sin espacios")
    return token


def signature(secret: str, timestamp: int, method: str, path: str, body: str = "") -> str:
    message = f"{timestamp}{method}/v2{path}{body}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Key:
    key: str = field(repr=False)
    secret: str = field(repr=False)


class Bitvavo:
    def __init__(self, client: httpx.AsyncClient, key: Key | None = None) -> None:
        self.client = client
        self.key = key

    async def _get(self, path: str, signed: bool) -> Any:
        headers = {}
        if signed:
            assert self.key is not None
            now = int(time.time() * 1000)
            headers = {
                "bitvavo-access-key": self.key.key,
                "bitvavo-access-signature": signature(self.key.secret, now, "GET", path),
                "bitvavo-access-timestamp": str(now),
                "bitvavo-access-window": str(WINDOW_MS),
            }
        try:
            response = await self.client.get(f"{api_url()}{path}", headers=headers, timeout=30.0)
        except httpx.HTTPError as error:
            raise SourceError(
                f"Bitvavo no contesta: {type(error).__name__}", transient=True
            ) from error
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success or (isinstance(body, dict) and "errorCode" in body):
            code = body.get("errorCode") if isinstance(body, dict) else None
            message = body.get("error") if isinstance(body, dict) else response.text[:200]
            raise SourceError(
                f"Bitvavo {response.status_code} {code}: {message}",
                transient=response.status_code >= 500,
                rate_limited=response.status_code == 429,
            )
        return body

    async def balance(self) -> dict[str, Decimal]:
        found = {}
        for row in await self._get("/balance", signed=True):
            quantity = Decimal(row.get("available") or "0") + Decimal(row.get("inOrder") or "0")
            if quantity:
                found[row["symbol"]] = quantity
        return found

    async def history(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        page = 1
        while True:
            body = await self._get(f"/account/history?page={page}&maxItems={PAGE}", signed=True)
            found += body.get("items") or []
            if page >= int(body.get("totalPages") or 1):
                return found
            page += 1

    async def prices_in_euros(self) -> dict[str, Decimal]:
        return {
            row["market"].removesuffix("-EUR"): Decimal(row["price"])
            for row in await self._get("/ticker/price", signed=False)
            if row.get("market", "").endswith("-EUR") and row.get("price")
        }


def midnight(day: date) -> str:
    return datetime.combine(day, datetime.min.time(), UTC).isoformat()


def valued(
    holdings: dict[str, Decimal], prices: dict[str, Decimal]
) -> tuple[list[dict[str, Any]], Decimal, list[str]]:
    rows, total, unpriced = [], Decimal(0), []
    for symbol, quantity in sorted(holdings.items()):
        price = Decimal(1) if symbol == "EUR" else prices.get(symbol)
        value = (quantity * price).quantize(CENT, ROUND_HALF_UP) if price is not None else None
        if value is None:
            unpriced.append(symbol)
        else:
            total += value
        rows.append({"symbol": symbol, "quantity": quantity, "price": price, "value": value})
    return rows, total, unpriced


def account_event(day: date) -> dict:
    return {
        "ts": midnight(day),
        "type": ANNOUNCE,
        "payload": {
            "bank": "Bitvavo",
            "account": ACCOUNT,
            "name": "Bitvavo",
            "kind": "crypto",
            "currency": "EUR",
        },
        "dedup_hash": f"{ACCOUNT}:account",
    }


def events(holdings: dict[str, Decimal], prices: dict[str, Decimal], day: date) -> list[dict]:
    rows, total, unpriced = valued(holdings, prices)
    found = [
        {
            "ts": midnight(day),
            "type": HOLDING,
            "payload": {
                "account": ACCOUNT,
                "symbol": row["symbol"],
                "on": day.isoformat(),
                "quantity": str(row["quantity"]),
                "price": str(row["price"]) if row["price"] is not None else None,
                "value": str(row["value"]) if row["value"] is not None else None,
            },
            "dedup_hash": f"{LEGACY_SOURCE}:{ACCOUNT}:{row['symbol']}:{day.isoformat()}",
        }
        for row in rows
    ]
    found.append(
        {
            "ts": midnight(day),
            "type": BALANCE,
            "payload": {
                "account": ACCOUNT,
                "name": "Bitvavo",
                "kind": "crypto",
                "on": day.isoformat(),
                "amount": str(total.quantize(CENT, ROUND_HALF_UP)),
                "currency": "EUR",
                "account_currency": "EUR",
                "unpriced": unpriced,
            },
            "dedup_hash": f"{LEGACY_SOURCE}:{ACCOUNT}:{day.isoformat()}",
        }
    )
    return found


def _amount(raw: Any) -> Decimal | None:
    if raw in (None, ""):
        return None
    value = Decimal(str(raw))
    return value if value else None


def _plain(value: Decimal) -> str:
    return f"{value.quantize(Decimal('1e-8'), ROUND_HALF_UP).normalize():f}"


def _leg(
    item: dict[str, Any],
    side: str,
    symbol: str,
    quantity: Decimal,
    price: Decimal | None,
    suffix: str = "",
) -> dict:
    id_, at = str(item["transactionId"]), item["executedAt"]
    fee, fee_currency = _amount(item.get("feesAmount")), item.get("feesCurrency") or "EUR"
    fee_eur = None
    if fee is not None and suffix in ("", ":sell"):
        if fee_currency == "EUR":
            fee_eur = fee
        elif price is not None and fee_currency == symbol:
            fee_eur = (fee * price).quantize(CENT, ROUND_HALF_UP)
    payload = {
        "account": ACCOUNT,
        "id": id_ + suffix,
        "at": at,
        "side": side,
        "symbol": symbol,
        "quantity": _plain(quantity),
        "price": _plain(price) if price is not None else None,
        "fee": _plain(fee_eur) if fee_eur is not None else None,
        "origin": item.get("type"),
    }
    if suffix:
        payload["group"] = id_
    return {
        "ts": at,
        "type": TRADE,
        "payload": payload,
        "dedup_hash": f"{ACCOUNT}:trade:{id_}{suffix}",
    }


def trades(history: list[dict[str, Any]]) -> list[dict]:
    found = []
    for item in history:
        if item.get("type") == "withdrawal_cancelled":
            continue
        sent_n, got_n = _amount(item.get("sentAmount")), _amount(item.get("receivedAmount"))
        sent = (item.get("sentCurrency") or "") if sent_n else ""
        got = (item.get("receivedCurrency") or "") if got_n else ""
        if sent in ("", "EUR") and got in ("", "EUR"):
            continue
        if sent == "EUR":
            found.append(_leg(item, "buy", got, got_n, sent_n / got_n))
        elif got == "EUR":
            found.append(_leg(item, "sell", sent, sent_n, got_n / sent_n))
        elif sent and got:
            value = _amount(item.get("priceAmount"))
            if item.get("priceCurrency") != "EUR" or value is None:
                raise SourceError(
                    f"Bitvavo: la permuta {item['transactionId']} no dice su valor en euros"
                )
            found.append(_leg(item, "sell", sent, sent_n, value * got_n / sent_n, ":sell"))
            found.append(_leg(item, "buy", got, got_n, value, ":buy"))
        elif got:
            found.append(_leg(item, "in", got, got_n, None))
        else:
            found.append(_leg(item, "out", sent, sent_n, None))
    return found


async def sync(
    client: httpx.AsyncClient,
    secrets: dict[str, str],
    connection: Any = None,
    *,
    today: date | None = None,
) -> list[dict]:
    if not (secrets.get(API_KEY) and secrets.get(API_SECRET)):
        raise SourceError("falta la clave o el secreto de Bitvavo")
    api = Bitvavo(client, Key(secrets[API_KEY], secrets[API_SECRET]))
    holdings = await api.balance()
    prices = await api.prices_in_euros()
    day = today or datetime.now(UTC).date()
    found = [account_event(day), *events(holdings, prices, day)]
    return found + trades(await api.history())


SOURCES = (
    Provider(
        id="bitvavo",
        name="Bitvavo",
        category="finance",
        description="Tus posiciones en cripto, valoradas en euros una vez al día, y cada compra, "
        "venta y movimiento, con una clave de solo lectura.",
        capabilities=("sync",),
        serves=("bitvavo.handoff",),
        secrets=(
            Secret(
                "api_key",
                "Clave de API",
                "En Bitvavo, Ajustes → API: crea una clave solo de lectura, sin permiso para "
                "operar ni para retirar.",
            ),
            Secret("api_secret", "Secreto", "Bitvavo solo lo enseña una vez, al crear la clave."),
        ),
        emits=("finance.account", "finance.balance", "finance.holding", "finance.trade"),
        available=True,
        schedule="0 5 * * *",
        single=True,
        sync=Sync("holdings", sync),
        normalise=lambda _key, raw: normalise(raw),
    ),
)
