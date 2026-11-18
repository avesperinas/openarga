from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


class Unreadable(Exception):
    pass


@dataclass(frozen=True)
class Line:
    reference: str
    booked_on: date
    amount: Decimal
    description: str
    value_on: date | None = None
    counterparty: str | None = None


@dataclass
class Statement:
    lines: list[Line] = field(default_factory=list)
    balance: tuple[date, Decimal] | None = None


COLUMNS = {
    "booked_on": ("date", "booking date", "booked", "posted", "transaction date", "operation date"),
    "value_on": ("value date", "valuation date", "effective date"),
    "amount": ("amount", "value", "sum"),
    "debit": ("debit", "withdrawal", "paid out"),
    "credit": ("credit", "deposit", "paid in"),
    "description": (
        "description",
        "details",
        "memo",
        "text",
        "concept",
        "narrative",
        "reference text",
    ),
    "reference": ("reference", "id", "ref", "transaction id", "fitid"),
    "counterparty": ("counterparty", "payee", "name", "beneficiary", "merchant"),
    "balance": ("balance", "running balance"),
}


def _fold(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().replace("_", " ").split())


def amount_of(raw: str) -> Decimal:
    cleaned = re.sub(r"[^\d,.\-+()]", "", raw.replace("−", "-"))
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    if not re.search(r"\d", cleaned):
        raise Unreadable(f"'{raw}' is not an amount")
    comma, dot = cleaned.rfind(","), cleaned.rfind(".")
    if comma >= 0 and dot >= 0:
        decimal_mark = "," if comma > dot else "."
    elif comma >= 0 and cleaned.count(",") == 1:
        after = len(cleaned) - comma - 1
        whole = cleaned[:comma].lstrip("+-")
        decimal_mark = "," if after != 3 or whole == "0" else None
    elif dot >= 0 and cleaned.count(".") == 1:
        decimal_mark = "."
    else:
        decimal_mark = None
    if decimal_mark:
        other = "." if decimal_mark == "," else ","
        cleaned = cleaned.replace(other, "").replace(decimal_mark, ".")
    else:
        cleaned = cleaned.replace(",", "").replace(".", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as error:
        raise Unreadable(f"'{raw}' is not an amount") from error
    return -value if negative else value


def day_of(raw: str) -> date:
    value = raw.strip()
    for pattern, order in (
        (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),
        (r"(\d{4})/(\d{2})/(\d{2})", "ymd"),
        (r"(\d{4})(\d{2})(\d{2})", "ymd"),
        (r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", "dmy"),
    ):
        found = re.match(pattern, value)
        if found:
            a, b, c = (int(g) for g in found.groups())
            y, m, d = (a, b, c) if order == "ymd" else (c, b, a)
            try:
                return date(y, m, d)
            except ValueError as error:
                raise Unreadable(f"'{raw}' is not a date") from error
    raise Unreadable(f"'{raw}' is not a date")


def references(lines: list[Line]) -> list[Line]:
    seen: Counter[str] = Counter()
    out = []
    for line in lines:
        if line.reference:
            out.append(line)
            continue
        basis = f"{line.booked_on}|{line.amount}|{line.description}"
        seen[basis] += 1
        digest = hashlib.sha1(f"{basis}|{seen[basis]}".encode()).hexdigest()[:20]
        out.append(_with(line, f"s{digest}"))
    return out


def _with(line: Line, reference: str) -> Line:
    return Line(
        reference,
        line.booked_on,
        line.amount,
        line.description,
        line.value_on,
        line.counterparty,
    )


def parse_csv(content: str, columns: dict[str, str] | None = None) -> Statement:
    body = content.lstrip("﻿").strip("\r\n")
    if not body:
        raise Unreadable("the file is empty")
    head = body.splitlines()[0]
    delimiter = max(";,\t|", key=head.count)
    rows = list(csv.reader(io.StringIO(body), delimiter=delimiter))
    header = [_fold(h) for h in rows[0]]
    chosen: dict[str, int] = {}
    for key, name in (columns or {}).items():
        if _fold(name) not in header:
            raise Unreadable(f"there is no column '{name}'")
        chosen[key] = header.index(_fold(name))
    for key, names in COLUMNS.items():
        if key in chosen:
            continue
        for name in names:
            if name in header:
                chosen[key] = header.index(name)
                break
    if "booked_on" not in chosen:
        raise Unreadable("no date column found")
    if "amount" not in chosen and not ("debit" in chosen or "credit" in chosen):
        raise Unreadable("no amount column found")

    def cell(row: list[str], key: str) -> str:
        i = chosen.get(key)
        return row[i].strip() if i is not None and i < len(row) else ""

    statement = Statement()
    last_balance: tuple[date, Decimal] | None = None
    lines = []
    for number, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        try:
            on = day_of(cell(row, "booked_on"))
            if cell(row, "amount"):
                amount = amount_of(cell(row, "amount"))
            else:
                credit = amount_of(cell(row, "credit")) if cell(row, "credit") else Decimal(0)
                debit = amount_of(cell(row, "debit")) if cell(row, "debit") else Decimal(0)
                amount = credit - abs(debit)
            value_on = day_of(cell(row, "value_on")) if cell(row, "value_on") else None
            if cell(row, "balance"):
                last_balance = (on, amount_of(cell(row, "balance")))
        except Unreadable as error:
            raise Unreadable(f"line {number}: {error}") from error
        lines.append(
            Line(
                cell(row, "reference"),
                on,
                amount,
                " ".join(cell(row, "description").split()),
                value_on,
                cell(row, "counterparty") or None,
            )
        )
    statement.lines = references(lines)
    statement.balance = last_balance
    return statement


def _tag(block: str, name: str) -> str | None:
    found = re.search(rf"<{name}>\s*([^<\r\n]*)", block, re.IGNORECASE)
    return found.group(1).strip() if found else None


def parse_ofx(content: str) -> Statement:
    start = re.search(r"<OFX>", content, re.IGNORECASE)
    if not start:
        raise Unreadable("not an OFX file")
    body = content[start.start() :]
    statement = Statement()
    lines = []
    parts = re.split(r"<STMTTRN>", body, flags=re.IGNORECASE)[1:]
    for part in parts:
        block = re.split(r"</STMTTRN>|</BANKTRANLIST>", part, flags=re.IGNORECASE)[0]
        posted, amount = _tag(block, "DTPOSTED"), _tag(block, "TRNAMT")
        if not posted or amount is None:
            raise Unreadable("a transaction has no date or amount")
        name, memo = _tag(block, "NAME"), _tag(block, "MEMO")
        user = _tag(block, "DTUSER")
        lines.append(
            Line(
                _tag(block, "FITID") or "",
                day_of(posted),
                amount_of(amount),
                " ".join(" ".join(p for p in (name, memo) if p).split()),
                day_of(user) if user else None,
                name,
            )
        )
    ledger = re.search(
        r"<LEDGERBAL>(.*?)(?:</LEDGERBAL>|<AVAILBAL>|</STMTRS>|</CCSTMTRS>|$)",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    if ledger:
        amount, asof = _tag(ledger.group(1), "BALAMT"), _tag(ledger.group(1), "DTASOF")
        if amount is not None and asof:
            statement.balance = (day_of(asof), amount_of(amount))
    statement.lines = references(lines)
    return statement


def parse(
    content: str, kind: str | None = None, columns: dict[str, str] | None = None
) -> Statement:
    kind = kind or ("ofx" if re.search(r"<OFX>", content[:4000], re.IGNORECASE) else "csv")
    return parse_ofx(content) if kind == "ofx" else parse_csv(content, columns)


async def store(connection: AsyncConnection, account: str, statement: Statement) -> dict:
    added = 0
    for line in statement.lines:
        done = await connection.execute(
            text("""
                insert into money.money_v1_statement_line
                    (account, reference, booked_on, value_on, amount, description, counterparty)
                values (:a, :r, :d, :v, :m, :t, :c)
                on conflict (user_id, account, reference) do nothing
            """),
            {
                "a": account,
                "r": line.reference,
                "d": line.booked_on,
                "v": line.value_on,
                "m": line.amount,
                "t": line.description,
                "c": line.counterparty,
            },
        )
        added += done.rowcount
    if statement.balance:
        await connection.execute(
            text("""
                insert into money.money_v1_statement_balance (account, on_date, amount)
                values (:a, :d, :m)
                on conflict (user_id, account, on_date) do update set amount = excluded.amount
            """),
            {"a": account, "d": statement.balance[0], "m": statement.balance[1]},
        )
    return {"lines": len(statement.lines), "new": added, "balance": statement.balance is not None}
