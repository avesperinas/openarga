from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from money import book as books
from money import importer

MONTHS = 18
HOLDERS = {"alex": "Alex Demo", "sam": "Sam Demo"}
SALARY = {"alex": Decimal("2350"), "sam": Decimal("2080")}
SAVED = {"alex": Decimal("300"), "sam": Decimal("180")}
PARTNER = {"alex": "Sam", "sam": "Alex"}
POSITIONS = {
    "alex": (
        ("IE00B4L5Y983", "Global equity ETF", "42.5", "4200.00", "112.40"),
        ("IE00BKM4GZ66", "Emerging markets ETF", "60", "1800.00", "32.15"),
    ),
    "sam": (("IE00B4L5Y983", "Global equity ETF", "20", "1900.00", "112.40"),),
}

CATEGORIES = [
    {"nature": "income", "ownership": "individual", "name": "Salary"},
    {"nature": "expense", "ownership": "individual", "name": "Food"},
    {"nature": "expense", "ownership": "individual", "name": "Subscriptions"},
    {"nature": "expense", "ownership": "individual", "name": "Transport"},
    {"nature": "expense", "ownership": "individual", "name": "Leisure"},
    {"nature": "expense", "ownership": "shared", "name": "Rent", "split": "fifty_fifty"},
    {"nature": "expense", "ownership": "shared", "name": "Groceries", "split": "proportional"},
    {"nature": "expense", "ownership": "shared", "name": "Utilities", "split": "proportional"},
]
RULES = [
    {"text": "Salary", "category": "income/individual/Salary"},
    {"text": "Savings transfer", "transfer_to": "savings"},
    {"text": "Supermarket|Bakery", "category": "expense/individual/Food"},
    {"text": "Streaming|Music", "category": "expense/individual/Subscriptions"},
    {"text": "Metro|Fuel", "category": "expense/individual/Transport"},
    {"text": "Cinema|Concert", "category": "expense/individual/Leisure"},
]
FUNDS = [
    {
        "symbol": "IE00B4L5Y983",
        "asset": "equity",
        "regions": {"us": 68, "europe": 18, "japan": 6, "other_developed": 8},
    },
    {"symbol": "IE00BKM4GZ66", "asset": "equity", "regions": {"emerging": 100}},
]

LINE = text("""
    insert into money.money_v1_statement_line
        (account, reference, booked_on, value_on, amount, description, counterparty)
    values (:account, :reference, :on, :on, :amount, :description, null)
    on conflict (user_id, account, reference) do nothing
""")
BALANCE = text("""
    insert into money.money_v1_statement_balance (account, on_date, amount)
    values (:account, :on, :amount)
    on conflict (user_id, account, on_date) do update set amount = excluded.amount
""")
POSITION = text("""
    insert into money.money_v1_position (account, symbol, name, units, cost, price, price_on)
    values (:account, :symbol, :name, :units, :cost, :price, :on)
    on conflict (user_id, account, symbol) do update set
        name = excluded.name, units = excluded.units, cost = excluded.cost,
        price = excluded.price, price_on = excluded.price_on
""")


def _month(today: date, back: int) -> tuple[int, int]:
    index = today.year * 12 + today.month - 1 - back
    return index // 12, index % 12 + 1


def _line(year: int, month: int, account: str, kind: str, day: int, amount: Decimal, what: str):
    return {
        "account": account,
        "reference": f"demo-{year}{month:02d}-{kind}",
        "on": date(year, month, day),
        "amount": amount,
        "description": what,
    }


def _lines(persona: Persona, today: date) -> tuple[list[dict], list[dict]]:
    salary, saved = SALARY[persona.key], SAVED[persona.key]
    nudge = 1 if persona.key == "sam" else 0
    current, savings = [], []
    for back in range(MONTHS - 1, -1, -1):
        y, m = _month(today, back)
        bonus = Decimal(25) if back % 3 == 0 else Decimal(0)
        current += [
            _line(y, m, "everyday", "salary", 27, salary + bonus, "Salary demo company"),
            _line(y, m, "everyday", "save", 28, -saved, "Savings transfer"),
            _line(y, m, "everyday", "stream", 5, Decimal("-12.99"), "Streaming demo"),
            _line(y, m, "everyday", "music", 9, Decimal("-9.99"), "Music demo"),
            _line(y, m, "everyday", "metro", 3, Decimal("-40.00"), "Metro monthly pass"),
            _line(
                y,
                m,
                "everyday",
                "bakery",
                12,
                -Decimal(6 + back % 4) - Decimal("0.5"),
                "Bakery demo",
            ),
            _line(y, m, "everyday", "fuel", 18, -Decimal(35 + (back * 5) % 20), "Fuel demo"),
        ]
        for week in range(4):
            cost = Decimal(52 + (back * 7 + week * 13 + nudge * 5) % 31) + Decimal("0.4")
            current.append(
                _line(y, m, "everyday", f"super{week}", 4 + week * 7, -cost, "Supermarket demo")
            )
        if back % 2 == 0:
            current.append(
                _line(y, m, "everyday", "cinema", 21, -Decimal(14 + back % 5), "Cinema demo")
            )
        if back % 5 == 0:
            current.append(
                _line(y, m, "everyday", "concert", 22, Decimal(-45 - back), "Concert demo")
            )
        savings.append(_line(y, m, "savings", "save", 28, saved, "Savings transfer"))
    keep = lambda rows: [r for r in rows if r["on"] <= today]  # noqa: E731
    return keep(current), keep(savings)


def _entry(year: int, month: int, day: int, payer: str, amount: int, what: str, category: str):
    return {
        "payer": payer,
        "on": date(year, month, day),
        "amount": amount,
        "description": what,
        "category": f"expense/shared/{category}",
    }


def _entries(persona: Persona, today: date) -> list[dict]:
    if persona.key != "alex":
        return []
    out = []
    for back in range(MONTHS - 1, -1, -1):
        y, m = _month(today, back)
        out += [
            _entry(y, m, 1, "me", 980, "Rent", "Rent"),
            _entry(y, m, 8, "other", 96 + back % 5 * 3, "Electricity and water", "Utilities"),
            _entry(y, m, 14, "me", 118 + back % 4 * 7, "Weekly shop", "Groceries"),
            _entry(y, m, 24, "other", 109 + back % 6 * 5, "Weekly shop", "Groceries"),
        ]
    return [e for e in out if e["on"] <= today]


def _bundle(persona: Persona, today: date) -> importer.Bundle:
    start = _month(today, MONTHS - 1)
    first = date(start[0], start[1], 1)
    partner = PARTNER[persona.key]
    valuations = [
        {"account": "savings", "on": first, "value": Decimal("2500") + SAVED[persona.key] * 3},
    ]
    held = POSITIONS[persona.key]
    cost = sum(Decimal(p[3]) for p in held)
    for step in range(MONTHS, -1, -3):
        year, month = _month(today, step)
        share = Decimal(MONTHS - step) / MONTHS
        valuations.append(
            {
                "account": "brokerage",
                "on": date(year, month, 1),
                "value": (cost * (Decimal("0.7") + Decimal("0.3") * share)).quantize(Decimal("1")),
            }
        )
    return importer.Bundle.model_validate(
        {
            "settings": {
                "cutoff": first,
                "me_name": persona.name,
                "other_name": partner,
                "holders": [HOLDERS[persona.key]],
                "emergency_months": 3,
            },
            "accounts": [
                {
                    "key": "everyday",
                    "name": "Everyday",
                    "institution": "Demo Bank",
                    "type": "current",
                    "movements": "statement",
                },
                {
                    "key": "savings",
                    "name": "Savings",
                    "institution": "Demo Bank",
                    "type": "savings",
                    "movements": "statement",
                    "role": "emergency_fund",
                },
                {
                    "key": "brokerage",
                    "name": "Brokerage",
                    "institution": "Demo Broker",
                    "type": "etf",
                    "movements": "manual",
                },
            ],
            "categories": CATEGORIES,
            "rules": RULES,
            "entries": _entries(persona, today),
            "incomes": [
                {
                    "person": "me",
                    "from": first,
                    "to": date(today.year, 12, 31),
                    "salary": SALARY[persona.key] * 12,
                },
                {
                    "person": "other",
                    "from": first,
                    "to": date(today.year, 12, 31),
                    "salary": SALARY["sam" if persona.key == "alex" else "alex"] * 12,
                },
            ],
            "valuations": valuations,
            "funds": FUNDS,
        }
    )


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    await importer.apply(connection, _bundle(persona, today))
    current, savings = _lines(persona, today)
    for line in current + savings:
        await connection.execute(LINE, line)
    for account, rows in (("everyday", current), ("savings", savings)):
        if rows:
            await connection.execute(
                BALANCE,
                {"account": account, "on": today, "amount": _closing(persona, account, rows)},
            )
    priced = today - timedelta(days=1)
    for symbol, name, units, cost, price in POSITIONS[persona.key]:
        await connection.execute(
            POSITION,
            {
                "account": "brokerage",
                "symbol": symbol,
                "name": name,
                "units": Decimal(units),
                "cost": Decimal(cost),
                "price": Decimal(price),
                "on": priced,
            },
        )
    await books.bump(connection)


def _closing(persona: Persona, account: str, rows: list[dict]) -> Decimal:
    opening = Decimal("1800") if account == "everyday" else Decimal("2500") + SAVED[persona.key] * 3
    return opening + sum((r["amount"] for r in rows), Decimal(0))
