from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona, localizer
from money import book as books
from money import importer

say = localizer(Path(__file__).parent / "seed" / "i18n")

MONTHS = 18
HOLDERS = {"alex": "Alex Demo", "sam": "Sam Demo"}
SALARY = {"alex": Decimal("2350"), "sam": Decimal("2080")}
SAVED = {"alex": Decimal("300"), "sam": Decimal("180")}
PARTNER = {"alex": "Sam", "sam": "Alex"}
POSITIONS = {
    "alex": (
        ("IE00B4L5Y983", "Global equity ETF", "255", "25200.00", "112.40"),
        ("IE00BKM4GZ66", "Emerging markets ETF", "360", "10800.00", "32.15"),
    ),
    "sam": (("IE00B4L5Y983", "Global equity ETF", "160", "15200.00", "112.40"),),
}

CATEGORIES = [
    {"nature": "income", "ownership": "individual", "name": "Salary"},
    {"nature": "expense", "ownership": "individual", "name": "Food"},
    {"nature": "expense", "ownership": "individual", "name": "Restaurants"},
    {"nature": "expense", "ownership": "individual", "name": "Subscriptions"},
    {"nature": "expense", "ownership": "individual", "name": "Transport"},
    {"nature": "expense", "ownership": "individual", "name": "Leisure"},
    {"nature": "expense", "ownership": "individual", "name": "Health"},
    {"nature": "expense", "ownership": "individual", "name": "Shopping"},
    {"nature": "expense", "ownership": "individual", "name": "Sport"},
    {"nature": "expense", "ownership": "individual", "name": "Phone and internet"},
    {"nature": "expense", "ownership": "individual", "name": "Travel"},
    {"nature": "expense", "ownership": "shared", "name": "Rent", "split": "fifty_fifty"},
    {"nature": "expense", "ownership": "shared", "name": "Groceries", "split": "proportional"},
    {"nature": "expense", "ownership": "shared", "name": "Utilities", "split": "proportional"},
    {"nature": "expense", "ownership": "shared", "name": "Dinners out", "split": "fifty_fifty"},
    {"nature": "expense", "ownership": "shared", "name": "Home", "split": "proportional"},
]
RULES = [
    {"text": "Salary", "category": "income/individual/Salary"},
    {"text": "Savings transfer", "transfer_to": "savings"},
    {"text": "Supermarket|Bakery|Greengrocer", "category": "expense/individual/Food"},
    {"text": "Trattoria|Cafe|Burger|Tapas", "category": "expense/individual/Restaurants"},
    {"text": "Streaming|Music|Cloud storage", "category": "expense/individual/Subscriptions"},
    {"text": "Metro|Fuel|Taxi", "category": "expense/individual/Transport"},
    {"text": "Cinema|Concert|Bookshop", "category": "expense/individual/Leisure"},
    {"text": "Pharmacy|Dentist|Optician", "category": "expense/individual/Health"},
    {"text": "Clothes|Sports shop|Electronics", "category": "expense/individual/Shopping"},
    {"text": "Gym|Climbing", "category": "expense/individual/Sport"},
    {"text": "Mobile plan|Fibre", "category": "expense/individual/Phone and internet"},
    {
        "text": "Skyline Air|Nordic Wings|Atlas Air|Island Jet|Rail Europe|Hotel booking",
        "category": "expense/individual/Travel",
    },
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


BANK_WORDS = (
    "Savings transfer", "Supermarket", "Bakery", "Greengrocer", "Trattoria", "Cafe", "Burger",
    "Tapas", "Streaming", "Music", "Cloud storage", "Metro", "Fuel", "Taxi", "Cinema", "Concert",
    "Bookshop", "Pharmacy", "Dentist", "Optician", "Clothes", "Sports shop", "Electronics",
    "Gym", "Climbing", "Mobile plan", "Fibre", "Hotel booking", "flights", "tickets", "Paris",
    "Salary",
)  # fmt: skip


def _bank(persona: Persona, what: str) -> str:
    whole = say(persona, what)
    if whole != what:
        return whole
    for word in sorted(BANK_WORDS, key=len, reverse=True):
        what = what.replace(word, say(persona, word))
    return what


def _path(persona: Persona, path: str) -> str:
    head, _, name = path.rpartition("/")
    return f"{head}/{say(persona, name)}"


def _rule(persona: Persona, rule: dict) -> dict:
    found = {**rule, "text": "|".join(say(persona, word) for word in rule["text"].split("|"))}
    if "category" in rule:
        found["category"] = _path(persona, rule["category"])
    return found


def _entry_text(persona: Persona, entry: dict) -> dict:
    return {
        **entry,
        "description": say(persona, entry["description"]),
        "category": _path(persona, entry["category"]),
    }


def _spread(persona: Persona, key: str, low: int, high: int) -> int:
    digest = hashlib.sha256(f"{persona.key}:{key}".encode()).digest()
    return low + int.from_bytes(digest[:2], "big") % (high - low + 1)


TRIP_COSTS = {
    "alex": (
        (-430, "Skyline Air flights Rome", 310),
        (-270, "Nordic Wings flights Berlin", 196),
        (-505, "Hotel booking Andalusia", 640),
        (-75, "Skyline Air flights Flanders", 268),
        (-62, "Hotel booking Bruges and Ghent", 360),
        (-50, "Nordic Wings flights Copenhagen", 342),
        (-46, "Hotel booking Copenhagen", 540),
    ),
    "sam": (
        (-460, "Atlas Air flights Marrakech", 240),
        (-225, "Rail Europe tickets Paris", 220),
        (-200, "Island Jet flights Tenerife", 280),
        (-195, "Hotel booking Tenerife", 430),
    ),
}


def _lines(persona: Persona, today: date) -> tuple[list[dict], list[dict]]:
    salary, saved = SALARY[persona.key], SAVED[persona.key]
    alex = persona.key == "alex"
    current, savings = [], []

    def spend(y, m, key, day, what, low, high, every=1, offset=0, back=0):
        if (back + offset) % every == 0:
            cost = Decimal(_spread(persona, f"{key}-{y}{m}", low * 10, high * 10)) / 10
            current.append(_line(y, m, "everyday", key, day, -cost, what))

    for back in range(MONTHS - 1, -1, -1):
        y, m = _month(today, back)
        bonus = Decimal(25) if back % 3 == 0 else Decimal(0)
        extra = Decimal(1100) if m in (6, 12) else Decimal(0)
        current += [
            _line(y, m, "everyday", "salary", 27, salary + bonus + extra, "Salary demo company"),
            _line(y, m, "everyday", "save", 28, -saved, "Savings transfer"),
            _line(y, m, "everyday", "stream", 5, Decimal("-12.99"), "Streaming demo"),
            _line(y, m, "everyday", "music", 9, Decimal("-10.99"), "Music demo"),
            _line(y, m, "everyday", "cloud", 11, Decimal("-2.99"), "Cloud storage"),
            _line(y, m, "everyday", "metro", 3, Decimal("-40.00"), "Metro monthly pass"),
            _line(y, m, "everyday", "mobile", 7, Decimal("-18.50"), "Mobile plan"),
            _line(y, m, "everyday", "fibre", 8, Decimal("-29.90"), "Fibre home"),
            _line(
                y,
                m,
                "everyday",
                "gym",
                2,
                Decimal("-34.00" if alex else "-42.00"),
                "Gym membership",
            ),
        ]
        for week in range(4):
            cost = Decimal(48 + _spread(persona, f"super{week}-{y}{m}", 0, 38)) + Decimal("0.4")
            current.append(
                _line(y, m, "everyday", f"super{week}", 4 + week * 7, -cost, "Supermarket demo")
            )
        spend(y, m, "bakery", 12, "Bakery demo", 5, 11, back=back)
        spend(y, m, "greens", 16, "Greengrocer", 9, 24, back=back)
        spend(y, m, "fuel", 18, "Fuel demo", 32, 58, back=back)
        spend(y, m, "trattoria", 14, "Trattoria Da Mario", 28, 64, back=back)
        spend(y, m, "tapas", 20, "Tapas bar Irunazarra", 18, 46, back=back)
        spend(y, m, "cafe", 10, "Cafe Mercado", 8, 19, back=back)
        spend(y, m, "burger", 25, "Burger Joint", 11, 22, every=2, back=back)
        spend(y, m, "cinema", 21, "Cinema demo", 14, 19, every=2, back=back)
        spend(y, m, "concert", 22, "Concert demo", 38, 72, every=5, back=back)
        spend(y, m, "books", 17, "Bookshop Lectura", 16, 42, every=2, offset=1, back=back)
        spend(y, m, "pharm", 13, "Pharmacy demo", 6, 28, every=2, back=back)
        spend(y, m, "dentist", 19, "Dentist Sonrisa", 60, 120, every=9, back=back)
        spend(y, m, "clothes", 23, "Clothes Atelier Norte", 35, 140, every=3, back=back)
        spend(y, m, "sports", 15, "Sports shop Cumbre", 25, 95, every=4, offset=1, back=back)
        spend(y, m, "taxi", 26, "Taxi", 9, 24, every=3, back=back)
        if m in (11, 12):
            spend(y, m, "gadget", 24, "Electronics Voltio", 40, 220, back=back)
        if not alex and back % 3 == 0:
            spend(y, m, "optician", 9, "Optician Vista", 45, 120, back=back)
        savings.append(_line(y, m, "savings", "save", 28, saved, "Savings transfer"))
    for offset, what, amount in TRIP_COSTS[persona.key]:
        when = today + timedelta(days=offset)
        if (
            when.year * 12 + when.month
            >= _month(today, MONTHS - 1)[0] * 12 + _month(today, MONTHS - 1)[1]
        ):
            key = f"trip{abs(offset)}"
            current.append(
                _line(when.year, when.month, "everyday", key, when.day, -Decimal(amount), what)
            )
    for back in range(0, 16):
        when = today - timedelta(days=back)
        if _spread(persona, f"daily-{when}", 0, 9) < 6:
            current.append(
                _line(
                    when.year,
                    when.month,
                    "everyday",
                    f"daily{when.day}",
                    when.day,
                    -Decimal(_spread(persona, f"amount-{when}", 150, 1450)) / 100,
                    "Cafe Mercado" if back % 2 else "Bakery demo",
                )
            )
    if today.day > 2:
        current.append(
            _line(
                today.year,
                today.month,
                "everyday",
                "card4412",
                today.day - 1,
                Decimal("-23.80"),
                "Card payment 4412",
            )
        )
        current.append(
            _line(
                today.year,
                today.month,
                "everyday",
                "card9034",
                today.day - 2,
                Decimal("-61.35"),
                "Card payment 9034",
            )
        )
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
    swap = {"me": "other", "other": "me"}
    out = []
    for back in range(MONTHS - 1, -1, -1):
        y, m = _month(today, back)
        out += [
            _entry(y, m, 1, "me" if back % 2 == 0 else "other", 980, "Rent", "Rent"),
            _entry(
                y,
                m,
                8,
                "other" if back % 2 == 0 else "me",
                96 + back % 5 * 3,
                "Electricity and water",
                "Utilities",
            ),
            _entry(
                y,
                m,
                14,
                "me" if back % 3 else "other",
                118 + back % 4 * 7,
                "Weekly shop",
                "Groceries",
            ),
            _entry(
                y,
                m,
                24,
                "other" if back % 3 else "me",
                109 + back % 6 * 5,
                "Weekly shop",
                "Groceries",
            ),
            _entry(
                y,
                m,
                18,
                "other" if back % 2 else "me",
                62 + back % 5 * 9,
                "Dinner out",
                "Dinners out",
            ),
            _entry(
                y, m, 6, "other" if back % 2 else "me", 41, "Fibre and mobile bundle", "Utilities"
            ),
        ]
        if back % 4 == 1:
            out.append(_entry(y, m, 20, "me", 180 + back * 3, "Sofa cushions and lamp", "Home"))
        if back % 6 == 2:
            out.append(_entry(y, m, 22, "other", 74, "Cleaning supplies", "Home"))
    kept = [e for e in out if e["on"] <= today]
    if persona.key == "alex":
        return kept
    return [{**e, "payer": swap[e["payer"]]} for e in kept]


def _bundle(persona: Persona, today: date) -> importer.Bundle:
    start = _month(today, MONTHS - 1)
    first = date(start[0], start[1], 1)
    partner = PARTNER[persona.key]
    valuations = [
        {"account": "savings", "on": first, "value": Decimal("2500") + SAVED[persona.key] * 3},
    ]
    current, savings = _lines(persona, today)
    for account, rows in (("everyday", current), ("savings", savings)):
        for stamp, amount in _balances(persona, account, rows, today)[:-1]:
            valuations.append({"account": account, "on": stamp, "value": amount})
    held = POSITIONS[persona.key]
    cost = sum(Decimal(p[3]) for p in held)
    for step in range(MONTHS, -1, -3):
        year, month = _month(today, step)
        share = Decimal(MONTHS - step) / MONTHS
        valuations.append(
            {
                "account": "brokerage",
                "on": date(year, month, 1),
                "value": (cost * (Decimal("0.97") + Decimal("0.08") * share)).quantize(
                    Decimal("1")
                ),
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
                    "name": say(persona, "Everyday"),
                    "institution": "Demo Bank",
                    "type": "current",
                    "movements": "statement",
                },
                {
                    "key": "savings",
                    "name": say(persona, "Savings"),
                    "institution": "Demo Bank",
                    "type": "savings",
                    "movements": "statement",
                    "role": "emergency_fund",
                },
                {
                    "key": "brokerage",
                    "name": say(persona, "Brokerage"),
                    "institution": "Demo Broker",
                    "type": "etf",
                    "movements": "manual",
                },
            ],
            "categories": [{**one, "name": say(persona, one["name"])} for one in CATEGORIES],
            "rules": [_rule(persona, rule) for rule in RULES],
            "entries": [_entry_text(persona, entry) for entry in _entries(persona, today)],
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
            "history_flow": _contributions(persona, today),
            "funds": FUNDS,
        }
    )


def _contributions(persona: Persona, today: date) -> list[dict]:
    cost = sum(Decimal(p[3]) for p in POSITIONS[persona.key])
    monthly = (cost / 12).quantize(Decimal("0.01"))
    flows = []
    for back in range(MONTHS + 12, MONTHS, -1):
        year, month = _month(today, back)
        flows.append(
            {
                "year": year,
                "month": month,
                "kind": "contribution",
                "amount": monthly,
                "account": "brokerage",
            }
        )
    return flows


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    await importer.apply(connection, _bundle(persona, today))
    current, savings = _lines(persona, today)
    for line in current + savings:
        await connection.execute(LINE, {**line, "description": _bank(persona, line["description"])})
    for account, rows in (("everyday", current), ("savings", savings)):
        for stamp, amount in _balances(persona, account, rows, today):
            await connection.execute(BALANCE, {"account": account, "on": stamp, "amount": amount})
    priced = today - timedelta(days=1)
    for symbol, name, units, cost, price in POSITIONS[persona.key]:
        await connection.execute(
            POSITION,
            {
                "account": "brokerage",
                "symbol": symbol,
                "name": say(persona, name),
                "units": Decimal(units),
                "cost": Decimal(cost),
                "price": Decimal(price),
                "on": priced,
            },
        )
    await books.bump(connection)


def _balances(
    persona: Persona, account: str, rows: list[dict], today: date
) -> list[tuple[date, Decimal]]:
    opening = (
        Decimal("30000") if account == "everyday" else Decimal("2500") + SAVED[persona.key] * 3
    )
    ordered = sorted(rows, key=lambda r: r["on"])
    first = _month(today, MONTHS - 1)
    stamps = []
    for back in range(MONTHS - 1, -1, -1):
        year, month = _month(today, back)
        end = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
        stamps.append(min(end, today))
    stamps = [date(first[0], first[1], 1) - timedelta(days=1), *stamps]
    found = []
    for stamp in dict.fromkeys(stamps):
        found.append(
            (stamp, opening + sum((r["amount"] for r in ordered if r["on"] <= stamp), Decimal(0)))
        )
    return found
