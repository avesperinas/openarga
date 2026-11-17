from __future__ import annotations

import hashlib
import html
import re
import tomllib
import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from hub import finance
from hub.funds import CASH, symbol_of
from hub.instruments import PENCE, Line

BALANCE = "finance.balance"
MOVEMENT = "finance.movement"
ACCOUNT = "finance.account"
HOLDING = "finance.holding"
CENT = Decimal("0.01")
SOURCE = "statement"
DEDUP_LIMIT = 200
PAGES = tomllib.loads(
    (Path(__file__).resolve().parent / "catalogs" / "statements.toml").read_text()
)
RENAULT_PAGE = PAGES["renault"]
FINIZENS_PAGE = PAGES["finizens"]


class StatementError(ValueError):
    pass


@dataclass(frozen=True)
class Account:
    key: str
    entity: str
    name: str
    kind: str
    iban: str | None = None


@dataclass(frozen=True)
class Balance:
    account: str
    on: date
    amount: Decimal
    contributed: Decimal | None = None


@dataclass(frozen=True)
class Movement:
    account: str
    booked_on: date
    amount: Decimal
    description: str
    reference: str
    value_on: date | None = None
    nature: str | None = None


@dataclass(frozen=True)
class Holding:
    account: str
    on: date
    symbol: str
    name: str
    value: Decimal
    quantity: Decimal | None = None
    price: Decimal | None = None
    line: Line | None = None


@dataclass
class Read:
    entity: str
    accounts: list[Account] = field(default_factory=list)
    balances: list[Balance] = field(default_factory=list)
    movements: list[Movement] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    holdings: list[Holding] = field(default_factory=list)


def lines(page: str) -> list[str]:
    page = re.sub(r"(?is)<(script|style|svg|noscript|template)[^>]*>.*?</\1>", " ", page)
    text = re.sub(r"(?s)<[^>]+>", "\n", page)
    found = (html.unescape(line).replace(" ", " ").strip() for line in text.split("\n"))
    return [re.sub(r"\s+", " ", line) for line in found if line.strip()]


AMOUNT = re.compile(r"^([+\-−]?)\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€$")
DAY = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def euros(raw: str) -> Decimal:
    match = AMOUNT.match(raw.strip())
    if not match:
        raise StatementError(f"'{raw}' is not an amount")
    try:
        value = Decimal(match.group(2).replace(".", "").replace(",", "."))
    except InvalidOperation as error:
        raise StatementError(f"'{raw}' is not an amount") from error
    return -value if match.group(1) in ("-", "−") else value


NUMBER = re.compile(r"^(\d{1,3}(?:\.\d{3})*(?:,\d+)?)$")
PERCENT = re.compile(r"^(\d{1,3}(?:,\d+)?)\s*%$")


def number(raw: str) -> Decimal:
    match = NUMBER.match(raw.strip())
    if not match:
        raise StatementError(f"'{raw}' is not a number")
    return Decimal(match.group(1).replace(".", "").replace(",", "."))


def percent(raw: str) -> Decimal | None:
    match = PERCENT.match(raw.strip())
    return Decimal(match.group(1).replace(",", ".")) / 100 if match else None


def is_amount(raw: str) -> bool:
    return bool(AMOUNT.match(raw.strip()))


def day(raw: str) -> date:
    match = DAY.match(raw.strip())
    if not match:
        raise StatementError(f"'{raw}' is not a date")
    return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))


def is_day(raw: str) -> bool:
    return bool(DAY.match(raw.strip()))


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


RENAULT = "Renault Bank"
IBAN = re.compile(r"\b(ES\d{2}(?: ?\d{4}){5})\b")


def renault(page: str, today: date) -> Read:
    del today
    text = lines(page)
    iban = next((IBAN.search(line) for line in text if IBAN.search(line)), None)
    if iban is None:
        raise StatementError("the account IBAN does not appear")
    number = iban.group(1).replace(" ", "")
    key = f"statement:renault:{number}"
    read = Read(RENAULT, [Account(key, RENAULT, RENAULT_PAGE["product"], "savings", number)])

    try:
        start = text.index(RENAULT_PAGE["balance"]) + 1
    except ValueError as error:
        raise StatementError("the movements table does not appear") from error
    rows: list[tuple[date, str, Decimal, Decimal, date | None, str]] = []
    index = start
    while index + 4 < len(text):
        if not is_day(text[index]):
            index += 1
            continue
        if is_day(text[index + 1]):
            index += 1
            continue
        kind, amount, after = text[index + 1], text[index + 2], text[index + 3]
        if not (is_amount(amount) and is_amount(after)):
            index += 1
            continue
        value_on, concept, step = None, kind, 4
        if text[index + 4 : index + 5] == [RENAULT_PAGE["value_date"]] and index + 5 < len(text):
            value_on = day(text[index + 5]) if is_day(text[index + 5]) else None
            step = 6
            if text[index + 6 : index + 7] == [RENAULT_PAGE["concept"]] and index + 7 < len(text):
                concept, step = text[index + 7], 8
        rows.append((day(text[index]), kind, euros(amount), euros(after), value_on, concept))
        index += step
    if not rows:
        raise StatementError("the movements table is empty")

    ends: dict[date, Decimal] = {}
    for on, _, _, after, _, _ in rows:
        ends.setdefault(on, after)
    read.balances = [Balance(key, on, amount) for on, amount in sorted(ends.items())]

    seen: Counter[str] = Counter()
    for position, (on, kind, amount, after, value_on, concept) in enumerate(rows):
        if position + 1 == len(rows):
            read.skipped.append(
                f"the oldest entry ({on:%d/%m/%Y}, {amount} €) does not say whether it is in or out"
            )
            continue
        change = after - rows[position + 1][3]
        if abs(change) != amount:
            raise StatementError(
                f"the balance of {on:%d/%m/%Y} does not match its amount: an entry is missing"
            )
        identity = f"{on.isoformat()}:{change}:{after}"
        seen[identity] += 1
        read.movements.append(
            Movement(
                account=key,
                booked_on=on,
                amount=change,
                description=concept if concept != kind else kind,
                reference=f"{identity}:{seen[identity]}",
                value_on=value_on,
            )
        )
    return read


FINIZENS = "Finizens"
CAPITAL = set(FINIZENS_PAGE["capital"])
IN_VALUE = set(FINIZENS_PAGE["in_value"])
WITHOUT_AMOUNT = set(FINIZENS_PAGE["without_amount"])


def finizens_account(name: str) -> Account:
    kind = "pension" if FINIZENS_PAGE["pension"] in name.lower() else "roboadvisor"
    return Account(f"statement:finizens:{slug(name)}", FINIZENS, name, kind)


def finizens(page: str, today: date) -> Read:
    text = lines(page)
    if FINIZENS_PAGE["latest"] in text and FINIZENS_PAGE["selected"] in text:
        return finizens_movements(text)
    if FINIZENS_PAGE["portfolio"] in text and FINIZENS_PAGE["selected"] in text:
        return finizens_plan(text)
    if FINIZENS_PAGE["overview"] in text and FINIZENS_PAGE["plans"] in text:
        return finizens_position(text, today)
    raise StatementError("it is neither the overall position nor the movements of a plan")


def finizens_position(text: list[str], today: date) -> Read:
    read = Read(FINIZENS)
    start = text.index(FINIZENS_PAGE["plans"])
    values: dict[str, tuple[Decimal, Decimal]] = {}
    index = start
    while index < len(text):
        if text[index] != FINIZENS_PAGE["contributed"]:
            index += 1
            continue
        value, name = text[index - 1], text[index - 2]
        contributed = next((line for line in text[index + 1 : index + 4] if is_amount(line)), None)
        if not is_amount(value) or contributed is None:
            raise StatementError(f"plan '{name}' lacks its value and what was paid in")
        before = values.get(name, (Decimal(0), Decimal(0)))
        values[name] = (before[0] + euros(value), before[1] + euros(contributed))
        index += 1
        if text[index : index + 1] == [FINIZENS_PAGE["see_plan"]]:
            break
    if not values:
        raise StatementError("the overall position has no plan")
    for name, (value, contributed) in values.items():
        account = finizens_account(name)
        read.accounts.append(account)
        read.balances.append(Balance(account.key, today, value, contributed))
    return read


PLAN_DAY = re.compile(r"^A (\d{2}/\d{2}/\d{4})$")
FUND_ROW = 9
ROUNDING = Decimal("0.005")


def finizens_plan(text: list[str]) -> Read:
    name = text[text.index(FINIZENS_PAGE["selected"]) + 1]
    on = next((day(m.group(1)) for line in text if (m := PLAN_DAY.match(line))), None)
    if on is None:
        raise StatementError(f"the portfolio of '{name}' does not say which day it is from")
    end = text.index(FINIZENS_PAGE["portfolio"])
    summary = max((i for i in range(end) if text[i] == FINIZENS_PAGE["contributed"]), default=None)
    if summary is None or not is_amount(text[summary - 1]) or not is_amount(text[summary + 1]):
        raise StatementError(f"the portfolio of '{name}' lacks its value and what was paid in")
    total, contributed = euros(text[summary - 1]), euros(text[summary + 1])

    if FINIZENS_PAGE["net_asset_value"] in text:
        funds = [
            Shown(row[0], value=number(row[1]), quantity=number(row[7]), price=euros(row[8]))
            for row in fund_rows(text, text.index(FINIZENS_PAGE["net_asset_value"]) + 1)
        ]
    else:
        funds = [Shown(fund, weight=weight) for fund, weight in weights(text)]
    return portfolio(FINIZENS, name, on, total, contributed, funds)


@dataclass(frozen=True)
class Shown:
    name: str
    value: Decimal | None = None
    weight: Decimal | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    line: Line | None = None
    unpriced: str | None = None
    symbol: str | None = None


def portfolio(
    entity: str,
    name: str,
    on: date,
    total: Decimal,
    contributed: Decimal | None,
    funds: list[Shown],
) -> Read:
    account = (
        finizens_account(name)
        if slug(entity) == slug(FINIZENS)
        else Account(
            f"statement:{slug(entity)}:{slug(name)}",
            entity,
            name,
            "pension" if FINIZENS_PAGE["pension"] in name.lower() else "roboadvisor",
        )
    )
    read = Read(account.entity, [account])
    read.balances.append(Balance(account.key, on, total, contributed))
    held = Decimal(0)
    for fund in funds:
        if fund.value is not None:
            value = fund.value
        elif fund.weight is not None:
            value = (total * fund.weight).quantize(CENT)
        else:
            raise StatementError(f"'{fund.name}' gives neither its value nor its weight")
        held += value
        symbol = fund.line.symbol if fund.line else fund.symbol or symbol_of(fund.name)
        if symbol is not None and any(h.symbol == symbol for h in read.holdings):
            raise StatementError(f"'{fund.name}' is twice in the portfolio of '{name}'")
        if symbol is None:
            why = fund.unpriced or "its price is unknown"
            read.skipped.append(f"'{fund.name}': {why}, it stays in today's value")
        cash = symbol == CASH
        read.holdings.append(
            Holding(
                account.key,
                on,
                symbol or f"name:{slug(fund.name)}",
                fund.name,
                value,
                value if cash else fund.quantity,
                Decimal(1) if cash else fund.price,
                fund.line,
            )
        )
    if not funds:
        raise StatementError(f"the portfolio of '{name}' lacks its funds")
    if abs(held - total) > max(total * ROUNDING, Decimal(1)):
        raise StatementError(
            f"the funds of '{name}' add up to {held} and the product is worth {total}"
        )
    return read


def fund_rows(text: list[str], start: int) -> list[list[str]]:
    rows = []
    index = start
    while index + FUND_ROW <= len(text) and not text[index].startswith(FINIZENS_PAGE["prospectus"]):
        row = text[index : index + FUND_ROW]
        if not is_amount(row[8]) or not NUMBER.match(row[1]):
            raise StatementError(f"fund '{row[0]}' lacks its value and its net asset value")
        rows.append(row)
        index += FUND_ROW
    return rows


def weights(text: list[str]) -> list[tuple[str, Decimal]]:
    start = next(
        (
            i + 2
            for i in range(len(text) - 1)
            if text[i : i + 2] == [FINIZENS_PAGE["fund"], FINIZENS_PAGE["distribution"]]
        ),
        None,
    )
    found = []
    index = start if start is not None else len(text)
    while index + 1 < len(text) and (weight := percent(text[index + 1])) is not None:
        found.append((text[index], weight))
        index += 2
    return found


def finizens_movements(text: list[str]) -> Read:
    chosen = text.index(FINIZENS_PAGE["selected"])
    name, profile = text[chosen + 1], text[chosen + 2]
    account = finizens_account(name)
    read = Read(FINIZENS, [account])
    start = text.index(FINIZENS_PAGE["latest"]) + 1
    seen: Counter[str] = Counter()
    index = start
    while index < len(text):
        label = text[index]
        if label in (FINIZENS_PAGE["own_portfolio"], FINIZENS_PAGE["new_product"]):
            break
        if label in WITHOUT_AMOUNT:
            index += 1
            continue
        if index + 2 < len(text) and is_amount(text[index + 1]) and is_day(text[index + 2]):
            amount, on = euros(text[index + 1]), day(text[index + 2])
            description = text[index + 3] if index + 3 < len(text) else label
            if label in IN_VALUE:
                read.skipped.append(f"{label} of {on:%d/%m/%Y}: already in the plan's value")
            elif label in CAPITAL:
                identity = f"{slug(profile)}:{on.isoformat()}:{slug(label)}:{amount}"
                seen[identity] += 1
                read.movements.append(
                    Movement(
                        account=account.key,
                        booked_on=on,
                        amount=amount,
                        description=f"{label} · {description}",
                        reference=f"{identity}:{seen[identity]}",
                        nature="contribution",
                    )
                )
            else:
                read.skipped.append(f"'{label}' of {on:%d/%m/%Y}: unknown kind")
            index += 3
            continue
        index += 1
    return read


@dataclass(frozen=True)
class Reader:
    entity: str
    recognises: Callable[[str], bool]
    read: Callable[[str, date], Read]


READERS = (
    Reader(
        RENAULT, lambda page: "Renault Bank" in page and RENAULT_PAGE["product"] in page, renault
    ),
    Reader(
        FINIZENS, lambda page: "app.finizens.com" in page or "<title>Finizens" in page, finizens
    ),
)


def read(page: str, today: date) -> Read:
    for reader in READERS:
        if reader.recognises(page):
            return reader.read(page, today)
    raise StatementError("not a page arga can read: Renault Bank or Finizens")


def midnight(on: date) -> str:
    return datetime.combine(on, datetime.min.time(), UTC).isoformat()


def dedup(*parts: str) -> str:
    return ":".join([SOURCE, *parts])[:DEDUP_LIMIT]


def line_of(line: Line) -> dict[str, str]:
    return {
        "isin": line.isin,
        "kind": line.kind,
        "quote_currency": PENCE.get(line.currency, line.currency),
        **({"mic": line.mic} if line.mic else {}),
    }


def events_of(found: Read) -> list[dict[str, Any]]:
    names = {account.key: account for account in found.accounts}
    events: list[dict[str, Any]] = []
    for account in found.accounts:
        events.append(
            {
                "ts": datetime.now(UTC).isoformat(),
                "type": ACCOUNT,
                "payload": {
                    "bank": account.entity,
                    "account": account.key,
                    "name": account.name,
                    "iban": account.iban,
                    "iban_tail": account.iban[-4:] if account.iban else None,
                    "kind": account.kind,
                    "currency": "EUR",
                },
                "dedup_hash": dedup("account", account.key),
            }
        )
    for balance in found.balances:
        account = names.get(balance.account)
        events.append(
            {
                "ts": midnight(balance.on),
                "type": BALANCE,
                "payload": {
                    "account": balance.account,
                    "name": account.name if account else balance.account,
                    "kind": account.kind if account else None,
                    "account_currency": "EUR",
                    "on": balance.on.isoformat(),
                    "amount": str(balance.amount),
                    "currency": "EUR",
                    **(
                        {"contributed": str(balance.contributed)}
                        if balance.contributed is not None
                        else {}
                    ),
                },
                "dedup_hash": dedup(balance.account, balance.on.isoformat(), str(balance.amount)),
            }
        )
    for movement in found.movements:
        events.append(
            {
                "ts": midnight(movement.booked_on),
                "type": MOVEMENT,
                "payload": {
                    "account": movement.account,
                    "reference": movement.reference,
                    "booked_on": movement.booked_on.isoformat(),
                    "value_on": movement.value_on.isoformat() if movement.value_on else None,
                    "amount": str(movement.amount),
                    "currency": "EUR",
                    "description": movement.description,
                    "counterparty": found.entity,
                    "raw_descriptor": movement.description,
                    **({"nature": movement.nature} if movement.nature else {}),
                },
                "dedup_hash": dedup(movement.account, movement.reference),
            }
        )
    photos: dict[tuple[str, date], list[Holding]] = {}
    for holding in found.holdings:
        photos.setdefault((holding.account, holding.on), []).append(holding)
    for (account_key, on), held in photos.items():
        content = "|".join(sorted(f"{h.symbol}={h.value}" for h in held))
        photo = hashlib.sha256(f"{account_key}:{on}:{content}".encode()).hexdigest()[:16]
        for holding in held:
            events.append(
                {
                    "ts": midnight(holding.on),
                    "type": HOLDING,
                    "payload": {
                        "account": holding.account,
                        "symbol": holding.symbol,
                        "name": holding.name,
                        "on": holding.on.isoformat(),
                        "value": str(holding.value),
                        "photo": photo,
                        **(
                            {"quantity": str(holding.quantity)}
                            if holding.quantity is not None
                            else {}
                        ),
                        **({"price": str(holding.price)} if holding.price is not None else {}),
                        **(line_of(holding.line) if holding.line else {}),
                    },
                    "dedup_hash": dedup(
                        "holding", photo, holding.account, on.isoformat(), holding.symbol
                    ),
                }
            )
    return finance.enrich(events, found.entity)
