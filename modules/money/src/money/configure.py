from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from money import catalog, products
from money.book import Loaded, bump, dumps
from money.interpret import fold
from money.texts import currency

CENT = Decimal("0.01")
ROUNDING = Decimal("0.01")
IBAN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{8,30}$")


class Refused(Exception):
    pass


def slug(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return "_".join(re.findall(r"[a-z0-9]+", plain))[:40].strip("_") or "cuenta"


def clean_ibans(ibans: list[str]) -> list[str]:
    out = []
    for raw in ibans:
        iban = raw.replace(" ", "").upper()
        if not IBAN.match(iban):
            raise Refused(f"'{raw}' is not an IBAN")
        if iban not in out:
            out.append(iban)
    return out


def check_type(kind: str) -> None:
    if kind not in catalog.account_types():
        raise Refused("no such product type")


async def _source_match(lo: Loaded, source_key: str) -> tuple[str, str, str]:
    found = next((s for s in lo.source_accounts if s.key == source_key), None)
    if found is None:
        raise Refused("no such account in your sources")
    if source_key in lo.source_of:
        raise Refused("that account of your sources is already another product")
    movements = "statement" if source_key.startswith("statement:") else "api"
    return movements, found.bank, found.iban_tail or found.name


async def create_account(
    connection: AsyncConnection,
    lo: Loaded,
    *,
    name: str,
    kind: str,
    institution: str,
    ownership: Decimal = Decimal(1),
    shared: bool = False,
    ibans: list[str] | None = None,
    source_key: str | None = None,
) -> str:
    check_type(kind)
    name, institution = name.strip(), institution.strip()
    if not name or not institution:
        raise Refused("the name or the institution is missing")
    movements, bank, key_of_source = "matched", None, None
    if source_key:
        movements, bank, key_of_source = await _source_match(lo, source_key)
    base = slug(name)
    key, n = base, 2
    while key in lo.book.accounts:
        suffix = f"_{n}"
        key, n = base[: 40 - len(suffix)] + suffix, n + 1
    await connection.execute(
        text("""
        insert into money.money_v1_account
            (key, name, institution, type, movements, ownership, shared_space, ibans,
             match_bank, match_key, position)
        values (:key, :name, :institution, :type, :movements, :ownership, :shared, :ibans,
                :bank, :match,
                coalesce((select max(position) from money.money_v1_account), 0) + 1)
    """),
        {
            "key": key,
            "name": name,
            "institution": institution,
            "type": kind,
            "movements": movements,
            "ownership": ownership,
            "shared": shared,
            "ibans": clean_ibans(ibans or []),
            "bank": bank,
            "match": key_of_source,
        },
    )
    await bump(connection)
    return key


@dataclass
class Change:
    name: str | None = None
    kind: str | None = None
    institution: str | None = None
    ownership: Decimal | None = None
    shared: bool | None = None
    ibans: list[str] | None = None
    value_mode: str | None = None
    source_key: str | None = None


async def update_account(connection: AsyncConnection, lo: Loaded, key: str, change: Change) -> None:
    if key not in lo.book.accounts:
        raise Refused("no such product")
    sets, params = [], {"key": key}
    if change.name is not None:
        if not change.name.strip():
            raise Refused("the name is missing")
        sets.append("name = :name")
        params["name"] = change.name.strip()
    if change.kind is not None:
        check_type(change.kind)
        sets.append("type = :type")
        params["type"] = change.kind
    if change.institution is not None:
        if not change.institution.strip():
            raise Refused("the institution is missing")
        sets.append("institution = :institution")
        params["institution"] = change.institution.strip()
    if change.ownership is not None:
        if not Decimal(0) < change.ownership <= 1:
            raise Refused("your share goes from 1% to 100%")
        sets.append("ownership = :ownership")
        params["ownership"] = change.ownership
    if change.shared is not None:
        sets.append("shared_space = :shared")
        params["shared"] = change.shared
    if change.ibans is not None:
        sets.append("ibans = :ibans")
        params["ibans"] = clean_ibans(change.ibans)
    if change.value_mode is not None:
        if change.value_mode and change.value_mode not in products.VALUE_HOW:
            raise Refused("no such way of valuing")
        sets.append("value = :value")
        params["value"] = change.value_mode or None
    if change.source_key is not None:
        movements, bank, match = await _source_match(lo, change.source_key)
        sets += ["movements = :movements", "match_bank = :bank", "match_key = :match"]
        params |= {"movements": movements, "bank": bank, "match": match}
    if not sets:
        return
    await connection.execute(
        text(f"update money.money_v1_account set {', '.join(sets)} where key = :key"), params
    )
    await bump(connection)


def _canonical(name: str) -> str:
    swap = {"idx": "index", "gbl": "global", "govt": "gov", "government": "gov"}
    drop = {"fund", "the", "etf", "acc", "eur", "accumulating", "class", "shares", "inst", "plus"}
    drop |= {"h", "hedged"}
    words = re.findall(r"[a-z0-9]+", fold(name).lower())
    return " ".join(swap.get(w, w) for w in words if w not in drop)


def known_funds(lo: Loaded) -> dict[str, str]:
    out = {symbol: data["name"] for symbol, data in catalog.funds().items()}
    for h in lo.book.holdings:
        if h.name and not h.symbol.startswith("name:"):
            out.setdefault(h.symbol, h.name)
    return out


def symbol_for(lo: Loaded, name: str) -> str:
    wanted = _canonical(name)
    if wanted in ("liquidez", "efectivo", "cash"):
        return currency()
    for h in lo.book.holdings:
        if h.name and _canonical(h.name) == wanted and not h.symbol.startswith("name:"):
            return h.symbol
    for symbol, known in known_funds(lo).items():
        if _canonical(known) == wanted:
            return symbol
    return "name:" + "-".join(wanted.split())


@dataclass
class Typed:
    name: str
    value: Decimal | None = None
    weight: Decimal | None = None
    """In percent."""
    symbol: str | None = None


async def set_composition(
    connection: AsyncConnection,
    lo: Loaded,
    key: str,
    on: date,
    funds: list[Typed],
    total: Decimal | None = None,
) -> dict:
    account = lo.book.accounts.get(key)
    if account is None:
        raise Refused("no such product")
    if account.asset_class != "investment":
        raise Refused("only an investment product has funds")
    if not funds:
        raise Refused("at least one fund is missing")
    if total is None and any(f.value is None for f in funds):
        now = products.analysis.valued(lo, account, on)
        if not now.known or now.amount <= 0:
            raise Refused("with weights, what the product is worth is needed")
        total = now.amount
    rows: dict[str, tuple[str, Decimal]] = {}
    for f in funds:
        if f.value is None and f.weight is None:
            raise Refused(f"'{f.name}' gives neither its value nor its weight")
        value = f.value if f.value is not None else (total * f.weight / 100).quantize(CENT)
        if value < 0:
            raise Refused(f"'{f.name}' cannot be worth less than zero")
        symbol = f.symbol or symbol_for(lo, f.name)
        if symbol in rows:
            raise Refused(f"'{f.name}' is there twice")
        rows[symbol] = (f.name.strip(), value)
    held = sum((v for _, v in rows.values()), Decimal(0))
    if total is not None and abs(held - total) > max(total * ROUNDING, Decimal(1)):
        raise Refused(f"the funds add up to {held} and the product is worth {total}")
    await connection.execute(
        text("delete from money.money_v1_holding where account = :a and on_date = :d"),
        {"a": key, "d": on},
    )
    for symbol, (name, value) in rows.items():
        await connection.execute(
            text("""
            insert into money.money_v1_holding (account, on_date, symbol, name, value)
            values (:a, :d, :s, :n, :v)
        """),
            {"a": key, "d": on, "s": symbol, "n": name, "v": value},
        )
    await _valuation(connection, key, on, total if total is not None else held)
    await bump(connection)
    unknown = [
        name
        for symbol, (name, _) in rows.items()
        if symbol not in catalog.funds() and symbol not in lo.funds
    ]
    return {
        "funds": len(rows),
        "value": total if total is not None else held,
        "unclassified": unknown,
    }


async def remove_composition(connection: AsyncConnection, key: str, on: date) -> None:
    await connection.execute(
        text("delete from money.money_v1_holding where account = :a and on_date = :d"),
        {"a": key, "d": on},
    )
    await bump(connection)


async def _valuation(connection: AsyncConnection, key: str, on: date, value: Decimal) -> None:
    await connection.execute(
        text("""
        insert into money.money_v1_valuation (account, on_date, value, source)
        values (:a, :d, :v, 'manual')
        on conflict (user_id, account, on_date) do update set value = excluded.value,
            source = 'manual'
    """),
        {"a": key, "d": on, "v": value},
    )


async def set_value(
    connection: AsyncConnection, lo: Loaded, key: str, on: date, value: Decimal
) -> None:
    if key not in lo.book.accounts:
        raise Refused("no such product")
    if value < 0:
        raise Refused("the value cannot be negative")
    await _valuation(connection, key, on, value)
    await bump(connection)


async def classify_fund(
    connection: AsyncConnection, symbol: str, asset: str, regions: dict[str, Decimal]
) -> None:
    if asset not in products.ASSETS:
        raise Refused("no such asset class")
    unknown = set(regions) - set(products.REGIONS)
    if unknown:
        raise Refused(f"no such region: {', '.join(sorted(unknown))}")
    kept = {k: v for k, v in regions.items() if v > 0}
    if kept and abs(sum(kept.values(), Decimal(0)) - 100) > Decimal("0.5"):
        raise Refused("the regions have to add up to 100%")
    await connection.execute(
        text("""
        insert into money.money_v1_fund (symbol, asset, regions)
        values (:s, :a, cast(:r as jsonb))
        on conflict (user_id, symbol) do update set asset = excluded.asset,
            regions = excluded.regions
    """),
        {"s": symbol, "a": asset, "r": dumps({k: float(v) for k, v in kept.items()})},
    )
    await bump(connection)


async def unclassify_fund(connection: AsyncConnection, symbol: str) -> None:
    await connection.execute(
        text("delete from money.money_v1_fund where symbol = :s"), {"s": symbol}
    )
    await bump(connection)


def frozen(lo: Loaded, fact_id: str) -> dict | None:
    b = lo.book
    for t in b.transfers:
        if fact_id in (t.out_fact, t.in_fact):
            other = t.in_fact if t.out_fact == fact_id else t.out_fact
            return {"transfer_with": b.fact(other).account} if other else None
    if fact_id in b.returns:
        return {"return": True}
    if fact_id in b.settlements:
        return {"settlement": True}
    parts = [i for i in b.imputations if i.fact == fact_id]
    if parts:
        return {
            "parts": [
                {
                    "amount": str(i.amount),
                    "category": i.category,
                    "payer": i.payer,
                    "equity_in": i.equity_in,
                }
                for i in parts
            ]
        }
    return None


async def delete_rule(
    connection: AsyncConnection, lo: Loaded, rule_id: str, keep: bool = True
) -> int:
    if not any(str(r["id"]) == rule_id for r in lo.rules):
        raise Refused("no such rule")
    kept = 0
    if keep:
        for fact_id in products.ruled_by(lo, rule_id):
            spec = frozen(lo, fact_id)
            if spec is None:
                continue
            await connection.execute(
                text("""
                insert into money.money_v1_label (fact_id, spec)
                values (:f, cast(:s as jsonb))
                on conflict (user_id, fact_id) do nothing
            """),
                {"f": fact_id, "s": dumps(spec)},
            )
            kept += 1
    await connection.execute(
        text("delete from money.money_v1_rule where id = cast(:id as uuid)"), {"id": rule_id}
    )
    await bump(connection)
    return kept
