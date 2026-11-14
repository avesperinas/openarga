from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from money import catalog
from money.interpret import fold
from money.model import Balance, Fact, Holding

TYPES = (
    "finance.account",
    "finance.movement",
    "finance.movement_detail",
    "finance.balance",
    "finance.holding",
    "finance.price",
    "money.movement",
    "money.balance",
)

EVENTS = text("""
    select id, type, source, payload, ingested_at
    from money.events
    where type = any(:types)
    order by ts, id
""")


@dataclass(frozen=True)
class SourceAccount:
    key: str
    bank: str
    name: str
    kind: str | None
    iban_tail: str | None
    iban: str | None


@dataclass
class Loaded:
    facts: list[Fact] = field(default_factory=list)
    balances: list[Balance] = field(default_factory=list)
    merchant_of: dict[str, str] = field(default_factory=dict)
    own_iban: dict[str, str] = field(default_factory=dict)
    sources: list[SourceAccount] = field(default_factory=list)
    unmapped: list[SourceAccount] = field(default_factory=list)
    matched: dict[str, str] = field(default_factory=dict)
    """For each account of a source, the Money account it is."""
    holdings: list[Holding] = field(default_factory=list)
    prices: dict[str, list[tuple[date, Decimal]]] = field(default_factory=dict)


def _match_key(acc: SourceAccount) -> tuple[str, str]:
    return fold(acc.bank), fold(acc.iban_tail or acc.name)


def merchant(
    institution: str, description: str, counterparty: str | None, holders: tuple[str, ...]
) -> str:
    for pattern in catalog.institution(institution).get("merchant", ()):
        found = re.search(pattern, description)
        if found and found.group(1).strip():
            return " ".join(found.group(1).split())
    if counterparty and not any(fold(h) in fold(counterparty) for h in holders):
        return " ".join(counterparty.split())
    return " ".join(description.split())


async def load(
    connection: AsyncConnection,
    matches: dict[tuple[str, str], tuple[str, str]],
    holders: tuple[str, ...],
) -> Loaded:
    rows = (await connection.execute(EVENTS, {"types": list(TYPES)})).all()
    out = Loaded()
    seen: dict[str, SourceAccount] = {}
    for r in rows:
        if r.type == "finance.account":
            p = r.payload
            seen[p["account"]] = SourceAccount(
                key=p["account"],
                bank=(p.get("bank") or "").strip(),
                name=(p.get("name") or "").strip(),
                kind=p.get("kind"),
                iban_tail=p.get("iban_tail"),
                iban=(p.get("iban") or "").replace(" ", "").upper() or None,
            )
    out.sources = list(seen.values())
    lab: dict[str, tuple[str, str]] = {}
    for acc in out.sources:
        hit = matches.get(_match_key(acc))
        if hit:
            lab[acc.key] = hit
            out.matched[acc.key] = hit[0]
            if acc.iban:
                out.own_iban[hit[0]] = acc.iban
        else:
            out.unmapped.append(acc)
    bank_of = {k: a.bank for k, a in seen.items()}

    details = {}
    for r in rows:
        if r.type == "finance.movement_detail":
            p = r.payload
            details[(p.get("account"), p.get("reference"))] = p

    facts: dict[tuple[str, str], Fact] = {}
    for r in rows:
        if r.type not in ("finance.movement", "money.movement"):
            continue
        p = r.payload
        hit = lab.get(p.get("account"))
        if hit is None:
            continue
        account, institution = hit
        ref = p.get("reference") or str(r.id)
        d = details.get((p.get("account"), ref), {})
        cp = (
            d.get("counterparty_name")
            or d.get("creditor_name")
            or d.get("debtor_name")
            or p.get("counterparty")
        )
        if cp and fold(cp) == fold(bank_of.get(p.get("account"), "")):
            cp = None
        description = " ".join((p.get("description") or "").split())
        bank_category = p.get("bank_category")
        if bank_category is None:
            pattern = catalog.institution(institution).get("bank_category")
            found = re.match(pattern, p.get("description") or "") if pattern else None
            bank_category = found.group(1).strip() if found else None
        fact = Fact(
            id=f"{account}:{ref}",
            account=account,
            on=date.fromisoformat(p["booked_on"]),
            amount=Decimal(str(p["amount"])),
            text=description,
            source="statement" if r.source == "statement" else "api",
            counterparty=cp,
            counterparty_iban=(d.get("counterparty_iban") or p.get("counterparty_iban") or None),
            bank_category=bank_category,
            value_on=date.fromisoformat(p["value_on"]) if p.get("value_on") else None,
            own_transfer=bool(p.get("own_transfer")),
        )
        facts[(account, ref)] = fact
        out.merchant_of[fact.id] = p.get("merchant") or merchant(
            institution, p.get("description") or "", cp, holders
        )
    out.facts = list(facts.values())

    balances: dict[tuple[str, date], Balance] = {}
    stated: set[tuple[str, date]] = set()
    for r in rows:
        if r.type not in ("finance.balance", "money.balance"):
            continue
        p = r.payload
        hit = lab.get(p.get("account"))
        if hit is None:
            continue
        on = date.fromisoformat(p["on"])
        kind = "closing"
        if p.get("balance_type") == "CLBD":
            on -= timedelta(days=1)
        elif p.get("balance_type") in ("ITAV", "ITBD", "XPCD"):
            kind = "available"
        found = Balance(hit[0], on, Decimal(str(p["amount"])), kind)
        if r.source == "statement" and (hit[0], on) in stated:
            balances[(hit[0], on)] = found
        else:
            balances.setdefault((hit[0], on), found)
        if r.source == "statement":
            stated.add((hit[0], on))
    out.balances = list(balances.values())

    loose: dict[tuple[str, date], dict[str, Holding]] = {}
    shots: dict[tuple[str, date], dict[str, tuple[object, dict[str, Holding]]]] = {}
    prices: dict[str, dict[date, Decimal]] = {}
    for r in rows:
        p = r.payload
        if r.type == "finance.price":
            prices.setdefault(p["symbol"], {})[date.fromisoformat(p["on"][:10])] = Decimal(
                str(p["price"])
            )
            continue
        if r.type != "finance.holding" or p.get("value") is None:
            continue
        hit = lab.get(p.get("account"))
        if hit is None:
            continue
        on = date.fromisoformat(p["on"][:10])
        held = Holding(
            hit[0],
            on,
            p["symbol"],
            Decimal(str(p["value"])),
            Decimal(str(p["price"])) if p.get("price") is not None else None,
            name=p.get("name") or p["symbol"],
        )
        photo = p.get("photo")
        if photo is None:
            loose.setdefault((hit[0], on), {})[p["symbol"]] = held
            continue
        arrived, funds = shots.setdefault((hit[0], on), {}).get(photo, (None, {}))
        came = getattr(r, "ingested_at", None)
        if came is not None and (arrived is None or came > arrived):
            arrived = came
        funds[p["symbol"]] = held
        shots[(hit[0], on)][photo] = (arrived, funds)
    holdings: dict[tuple[str, date, str], Holding] = {}
    for key in set(loose) | set(shots):
        if key in shots:
            _, funds = max(shots[key].values(), key=lambda shot: (shot[0] is not None, shot[0]))
        else:
            funds = loose[key]
        for symbol, held in funds.items():
            holdings[(key[0], key[1], symbol)] = held
    out.holdings = list(holdings.values())
    out.prices = {symbol: sorted(by_day.items()) for symbol, by_day in prices.items()}
    return out
