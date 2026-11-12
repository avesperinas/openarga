from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from money.history import Valuation
from money.model import Account, Book, Holding

ZERO = Decimal(0)
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Value:
    amount: Decimal
    since: date | None
    """El día del valor del que se parte. Si es anterior al pedido, el valor es arrastrado."""
    known: bool = True
    """Sin ningún valor anterior al día, no se sabe: cuenta 0 y se dice."""
    estimated: date | None = None
    """El día del último precio con que se ha movido la cartera desde `since`, si se ha movido."""


def value_at(book: Book, account: Account, on: date, valuations: list[Valuation]) -> Value:
    anchors: list[tuple[date, int, Decimal]] = [
        (b.on, 1, b.amount) for b in book.balances if b.account == account.id and b.on <= on
    ]
    anchors += [(v.on, 0, v.value) for v in valuations if v.account == account.id and v.on <= on]
    if anchors:
        since, _, amount = max(anchors, key=lambda a: (a[0], a[1]))
    elif account.asset_class == "receivable" and any(
        f.account == account.id and (f.value_on or f.on) <= on for f in book.facts
    ):
        since, amount = date.min, ZERO
    else:
        return Value(ZERO, None, known=False)

    if account.asset_class in ("cash", "receivable"):
        for f in book.facts:
            if f.account != account.id or not (since < (f.value_on or f.on) <= on):
                continue
            if f.source == "inferred" and account.movements == "api":
                continue
            amount += f.amount
    elif account.asset_class == "investment":
        moved, estimated = drift(book, account.id, since, amount, on)
        amount += moved
        for t in book.transfers:
            inn = book.fact(t.in_fact)
            if inn.account == account.id and since < inn.on <= on:
                amount += inn.amount
            if t.out_fact:
                out = book.fact(t.out_fact)
                if out.account == account.id and since < out.on <= on:
                    amount += out.amount
        amount += in_transit(book, account.id, on)
        return Value(amount, since, estimated=estimated)

    amount += in_transit(book, account.id, on)
    return Value(amount, since if since != date.min else None)


def price_on(series: list[tuple[date, Decimal]], on: date) -> tuple[date, Decimal] | None:
    index = bisect_right(series, on, key=lambda point: point[0])
    return series[index - 1] if index else None


SAME_PRICE = Decimal("0.002")


def start_price(
    series: list[tuple[date, Decimal]], held: Holding, since: date
) -> tuple[date, Decimal] | None:
    if held.on == since and held.price:
        same = [
            point
            for point in series
            if point[0] <= since and abs(point[1] / held.price - 1) <= SAME_PRICE
        ]
        if same:
            return same[-1]
    return price_on(series, since)


def drift(
    book: Book, account: str, since: date, amount: Decimal, on: date
) -> tuple[Decimal, date | None]:
    if on <= since:
        return ZERO, None
    shot = max(
        (h.on for h in book.holdings if h.account == account and h.on <= since), default=None
    )
    if shot is None:
        return ZERO, None
    held = [h for h in book.holdings if h.account == account and h.on == shot]
    whole = sum((h.value for h in held), ZERO)
    if whole <= 0:
        return ZERO, None
    moved, last = ZERO, None
    for h in held:
        series = book.prices.get(h.symbol)
        if not series:
            continue
        start, end = start_price(series, h, since), price_on(series, on)
        if start is None or end is None or end[0] <= start[0]:
            continue
        moved += amount * (h.value / whole) * (end[1] / start[1] - 1)
        last = max(last or end[0], end[0])
    return moved.quantize(CENT), last


def in_transit(book: Book, account: str, on: date) -> Decimal:
    total = ZERO
    for t in book.transfers:
        if not t.out_fact:
            continue
        out, inn = book.fact(t.out_fact), book.fact(t.in_fact)
        if inn.account == account and inn.source != "inferred" and out.on <= on < inn.on:
            total += inn.amount
    return total
