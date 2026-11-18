from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from money.model import Holding

ZERO = Decimal(0)


@dataclass(frozen=True)
class Position:
    account: str
    symbol: str
    name: str
    units: Decimal
    cost: Decimal
    price: Decimal | None
    price_on: date | None


@dataclass(frozen=True)
class Valued:
    position: Position
    key: str
    price: Decimal
    on: date
    source: str
    """`hub` (a price it publishes), `manual` (the one written down) or `cost` (what was paid)."""

    @property
    def value(self) -> Decimal:
        return (self.position.units * self.price).quantize(Decimal("0.01"))

    @property
    def gain(self) -> Decimal:
        return self.value - self.position.cost


async def load(connection: AsyncConnection) -> list[Position]:
    rows = (
        await connection.execute(
            text(
                "select account, symbol, name, units, cost, price, price_on "
                "from money.money_v1_position order by account, symbol"
            )
        )
    ).all()
    return [
        Position(
            r.account,
            r.symbol,
            r.name,
            Decimal(str(r.units)),
            Decimal(str(r.cost)),
            Decimal(str(r.price)) if r.price is not None else None,
            r.price_on,
        )
        for r in rows
    ]


def hub_price(
    prices: dict[str, list[tuple[date, Decimal]]], symbol: str, today: date
) -> tuple[str, date, Decimal] | None:
    best: tuple[str, date, Decimal] | None = None
    for key, series in prices.items():
        if key != symbol and not key.startswith(symbol + ":"):
            continue
        known = [(on, price) for on, price in series if on <= today]
        if known and (best is None or known[-1][0] > best[1]):
            best = (key, known[-1][0], known[-1][1])
    return best


def value(position: Position, prices: dict[str, list[tuple[date, Decimal]]], today: date) -> Valued:
    found = hub_price(prices, position.symbol, today)
    written = position.price is not None
    if found and not (written and position.price_on and position.price_on > found[1]):
        key, on, price = found
        return Valued(position, key, price, on, "hub")
    if written:
        return Valued(
            position, position.symbol, position.price, position.price_on or today, "manual"
        )
    return Valued(position, position.symbol, position.cost / position.units, today, "cost")


def holdings(
    stored: list[Position], prices: dict[str, list[tuple[date, Decimal]]], today: date
) -> list[Holding]:
    out = []
    for p in stored:
        v = value(p, prices, today)
        out.append(Holding(p.account, v.on, v.key, v.value, v.price, name=p.name or p.symbol))
    return out


async def save(connection: AsyncConnection, position: Position) -> None:
    await connection.execute(
        text("""
            insert into money.money_v1_position
                (account, symbol, name, units, cost, price, price_on)
            values (:a, :s, :n, :u, :c, :p, :d)
            on conflict (user_id, account, symbol) do update set
                name = excluded.name, units = excluded.units, cost = excluded.cost,
                price = excluded.price, price_on = excluded.price_on
        """),
        {
            "a": position.account,
            "s": position.symbol,
            "n": position.name,
            "u": position.units,
            "c": position.cost,
            "p": position.price,
            "d": position.price_on,
        },
    )


async def remove(connection: AsyncConnection, account: str, symbol: str) -> bool:
    done = await connection.execute(
        text("delete from money.money_v1_position where account = :a and symbol = :s"),
        {"a": account, "s": symbol},
    )
    return done.rowcount > 0


class Refused(Exception):
    pass


def check(accounts: dict, key: str) -> None:
    account = accounts.get(key)
    if account is None:
        raise Refused("no such product")
    if account.asset_class != "investment":
        raise Refused("only an investment product holds positions")


async def record(
    connection: AsyncConnection,
    accounts: dict,
    key: str,
    symbol: str,
    units: Decimal,
    cost: Decimal,
    name: str = "",
    price: Decimal | None = None,
    price_on: date | None = None,
    today: date | None = None,
) -> None:
    check(accounts, key)
    symbol = symbol.strip()
    if not symbol:
        raise Refused("a position needs an ISIN or a ticker")
    when = (price_on or today) if price is not None else None
    await save(connection, Position(key, symbol, name.strip(), units, cost, price, when))


def card(
    stored: list[Position],
    prices: dict[str, list[tuple[date, Decimal]]],
    key: str,
    today: date,
) -> dict:
    rows = []
    for p in stored:
        if p.account != key:
            continue
        v = value(p, prices, today)
        rows.append(
            {
                "symbol": p.symbol,
                "name": p.name,
                "units": p.units,
                "cost": p.cost,
                "price": v.price,
                "price_on": v.on,
                "price_source": v.source,
                "value": v.value,
                "gain": v.gain,
                "gain_pct": (v.gain / p.cost * 100) if p.cost else None,
            }
        )
    cost = sum((r["cost"] for r in rows), ZERO)
    worth = sum((r["value"] for r in rows), ZERO)
    return {
        "product": key,
        "currency": None,
        "positions": rows,
        "cost": cost,
        "value": worth,
        "gain": worth - cost,
    }
