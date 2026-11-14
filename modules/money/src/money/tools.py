from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import current_user
from money import book as books
from money import common, configure, kpis, products, texts
from money.interpret import fold
from money.shared import totals, year_balance
from money.texts import currency

MODULE = "money"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


@dataclass(frozen=True)
class Tool:
    arguments: type[Arguments]
    run: Callable[[AsyncConnection, Any], Awaitable[dict[str, Any]]]


def money(value: Decimal | None) -> float | None:
    return float(round(value, 2)) if value is not None else None


async def loaded(connection: AsyncConnection) -> books.Loaded:
    return await books.load(connection, current_user.get(None))


class GetSummary(Arguments):
    pass


async def get_summary(connection: AsyncConnection, _: GetSummary) -> dict[str, Any]:
    lo = await loaded(connection)
    return {
        "kpis": [
            {
                "key": k.key,
                "label": k.label,
                "value": money(k.value),
                "a_year_ago": money(k.previous),
                "target": money(k.target),
                "detail": k.detail,
                "carried": k.carried,
            }
            for k in kpis.compute(lo, texts.today())
        ],
        "emergency_months": lo.settings.emergency_months,
    }


class GetMovements(Arguments):
    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    start: date | None = Field(default=None, alias="from")
    end: date | None = Field(default=None, alias="to")
    text: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=60)
    pending_only: bool = False
    limit: int = Field(default=50, ge=1, le=300)


def _period(arguments: GetMovements) -> tuple[date, date]:
    if arguments.month:
        y, m = map(int, arguments.month.split("-"))
        first = date(y, m, 1)
        return first, (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    end = arguments.end or texts.today()
    return arguments.start or end.replace(day=1), end


async def get_movements(connection: AsyncConnection, arguments: GetMovements) -> dict[str, Any]:
    lo = await loaded(connection)
    b = lo.book
    start, end = _period(arguments)
    parts: dict[str, list] = {}
    for i in b.imputations:
        parts.setdefault(i.fact, []).append(i)
    rows = []
    for f in sorted(b.facts, key=lambda f: (f.on, f.id), reverse=True):
        if f.source == "inferred" or not start <= f.on <= end:
            continue
        status = lo.statuses.get(f.id, "pending")
        if arguments.pending_only and status not in ("ask", "pending"):
            continue
        merchant = lo.merchant_of.get(f.id) or f.text
        names = [b.categories[i.category].name for i in parts.get(f.id, [])]
        if arguments.category and not any(fold(arguments.category) == fold(n) for n in names):
            continue
        if arguments.text and fold(arguments.text) not in fold(f"{merchant} {f.text}"):
            continue
        rows.append(
            {
                "id": f.id,
                "on": f.on,
                "amount": money(f.amount),
                "account": b.accounts[f.account].name
                if f.account in b.accounts
                else "outside any account",
                "merchant": merchant,
                "status": status,
                "parts": [
                    {
                        "category": b.categories[i.category].name,
                        "nature": i.nature,
                        "ownership": i.ownership,
                        "amount": money(i.amount),
                    }
                    for i in parts.get(f.id, [])
                ],
            }
        )
    return {
        "from": start,
        "to": end,
        "matching": len(rows),
        "movements": rows[: arguments.limit],
    }


class GetSharedBalance(Arguments):
    year: int | None = Field(default=None, ge=2000, le=2100)


async def get_shared_balance(
    connection: AsyncConnection, arguments: GetSharedBalance
) -> dict[str, Any]:
    lo = await loaded(connection)
    today = texts.today()
    year = arguments.year or today.year
    view = await common.year_view(connection, lo, year, today)
    r = view.ratio_me
    yb = year_balance(view.months, r, year)
    me, other = view.me_name, view.other_name
    owe = abs(yb.balance_me)
    if owe < Decimal("0.005"):
        who = "you are even"
    elif yb.balance_me < 0:
        who = f"{me} owes {money(owe)} {currency()} to {other}"
    else:
        who = f"{other} owes {money(owe)} {currency()} to {me}"
    answer: dict[str, Any] = {
        "year": year,
        "settled": view.settled,
        "balance": who,
        "balance_me": money(yb.balance_me),
        "ratio_me": float(round(r, 4)),
        "total": money(yb.total),
        "by_category": {k: money(v) for k, v in yb.by_category.items()},
    }
    if view.role == common.MEMBER:
        answer["kept_by"] = other
        answer["as_of"] = view.kept_at.isoformat() if view.kept_at else None
        if view.keeper is None:
            answer["note"] = "nobody in the space keeps the shared account in their Money yet"
    else:
        answer["incomes"] = incomes_of(lo, year)
    return answer


def incomes_of(lo: books.Loaded, year: int) -> dict[str, dict[str, Any]]:
    counted = totals(lo.incomes, year)
    names = {"me": lo.settings.me_name, "other": lo.settings.other_name}
    return {names[p]: {"amount": money(counted[p])} for p in ("me", "other")}


class Ambiguous(Exception):
    pass


def category_named(lo: books.Loaded, name: str, nature: str | None, ownership: str | None) -> str:
    found = [
        c
        for c in lo.book.categories.values()
        if fold(c.name) == fold(name)
        and (nature is None or c.nature == nature)
        and (ownership is None or c.ownership == ownership)
    ]
    if len(found) == 1:
        return found[0].id
    if not found:
        raise Ambiguous(f"there is no category '{name}'")
    raise Ambiguous(
        f"there are several '{name}': say whether individual or shared, expense or income"
    )


class CategoriseMovement(Arguments):
    movement_id: str = Field(max_length=300)
    category: str = Field(min_length=1, max_length=60)
    nature: Literal["income", "expense"] | None = None
    ownership: Literal["individual", "shared"] | None = None
    payer: Literal["account", "me", "other"] | None = None


async def categorise_movement(
    connection: AsyncConnection, arguments: CategoriseMovement
) -> dict[str, Any]:
    lo = await loaded(connection)
    try:
        fact = lo.book.fact(arguments.movement_id)
    except KeyError:
        return {"error": "no such movement: find it first with get_movements"}
    try:
        category = category_named(lo, arguments.category, arguments.nature, arguments.ownership)
    except Ambiguous as error:
        return {"error": str(error)}
    cat = lo.book.categories[category]
    payer = None
    if cat.ownership == "shared":
        account = lo.book.accounts.get(fact.account)
        payer = arguments.payer or ("account" if account and account.shared_space else "me")
    spec = {"parts": [{"amount": str(fact.amount), "category": category, "payer": payer}]}
    await save_label(connection, fact.id, spec)
    return {"movement": fact.id, "category": cat.name, "ownership": cat.ownership, "payer": payer}


async def save_label(connection: AsyncConnection, fact_id: str, spec: dict[str, Any]) -> None:
    await connection.execute(
        text("""
        insert into money.money_v1_label (fact_id, spec) values (:f, cast(:s as jsonb))
        on conflict (user_id, fact_id) do update set spec = excluded.spec, updated_at = now()
    """),
        {"f": fact_id, "s": books.dumps(spec)},
    )
    await books.bump(connection)


class MarkTransfer(Arguments):
    movement_id: str = Field(max_length=300)
    product: str = Field(min_length=1, max_length=80)


async def mark_transfer(connection: AsyncConnection, arguments: MarkTransfer) -> dict[str, Any]:
    lo = await loaded(connection)
    try:
        fact = lo.book.fact(arguments.movement_id)
    except KeyError:
        return {"error": "no such movement: find it first with get_movements"}
    if fact.account not in lo.book.accounts:
        return {"error": "that movement is not from any account of yours"}
    try:
        other = product_named(lo, arguments.product)
    except configure.Refused as error:
        return {"error": str(error)}
    if other == fact.account:
        return {"error": "it is its own account: a transfer is with another account of yours"}
    await save_label(connection, fact.id, {"transfer_with": other})
    name = lo.book.accounts[other].name
    return {"movement": fact.id, "transfer": f"{'to' if fact.amount < 0 else 'from'} {name}"}


class RecordSharedExpense(Arguments):
    description: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category: str = Field(min_length=1, max_length=60)
    payer: Literal["me", "other"] = "other"
    on: date | None = None


async def record_shared_expense(
    connection: AsyncConnection, arguments: RecordSharedExpense
) -> dict[str, Any]:
    lo = await loaded(connection)
    if lo.settings.space_id is not None:
        try:
            entry = await common.add_entry(
                connection,
                lo,
                current_user.get(),
                arguments.payer,
                arguments.on or texts.today(),
                arguments.amount,
                arguments.description.strip(),
                arguments.category,
            )
        except common.Refused as error:
            return {"error": str(error)}
        await books.bump(connection)
        return {"entry": entry, "category": arguments.category, "shared_space": True}
    try:
        category = category_named(lo, arguments.category, "expense", "shared")
    except Ambiguous as error:
        return {"error": str(error)}
    row = (
        await connection.execute(
            text("""
            insert into money.money_v1_entry (payer, on_date, amount, description, category_id)
            values (:p, :d, :a, :t, :c) returning id
        """),
            {
                "p": arguments.payer,
                "d": arguments.on or texts.today(),
                "a": arguments.amount,
                "t": arguments.description.strip(),
                "c": category,
            },
        )
    ).first()
    await books.bump(connection)
    return {"entry": str(row.id), "category": lo.book.categories[category].name}


def plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(round(value, 4))
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


class GetProducts(Arguments):
    product: str | None = Field(default=None, max_length=80)


def product_named(lo: books.Loaded, name: str) -> str:
    if name in lo.book.accounts:
        return name
    wanted = fold(name)
    found = [a.id for a in lo.book.accounts.values() if fold(a.name) == wanted]
    if len(found) != 1:
        raise configure.Refused(
            f"there is no product called '{name}': look it up with get_products"
        )
    return found[0]


async def get_products(connection: AsyncConnection, arguments: GetProducts) -> dict[str, Any]:
    lo = await loaded(connection)
    today = texts.today()
    if arguments.product:
        try:
            key = product_named(lo, arguments.product)
        except configure.Refused as error:
            return {"error": str(error)}
        return plain(products.detail(lo, lo.book.accounts[key], today))
    return plain(
        {
            "products": [
                {
                    "key": a.id,
                    "name": a.name,
                    "institution": a.institution,
                    "type": a.type,
                    "value": products.analysis.valued(lo, a, today).amount,
                    "ownership": a.ownership,
                    "has_funds": products.last_shot(lo, a.id, today) is not None,
                }
                for a in lo.book.accounts.values()
            ],
            "types": list(products.catalog.account_types()),
            "unassigned_sources": [
                {"key": u.key, "bank": u.bank, "name": u.name} for u in lo.unmapped
            ],
        }
    )


class GetComposition(Arguments):
    products: list[str] = Field(default_factory=list, max_length=40)


async def get_composition(connection: AsyncConnection, arguments: GetComposition) -> dict[str, Any]:
    lo = await loaded(connection)
    today = texts.today()
    try:
        only = {product_named(lo, p) for p in arguments.products}
    except configure.Refused as error:
        return {"error": str(error)}
    return plain(products.composition(lo, today, today, True, False, today, (), only))


class GetRules(Arguments):
    pass


async def get_rules(connection: AsyncConnection, _: GetRules) -> dict[str, Any]:
    return {"rules": products.describe_rules(await loaded(connection))}


class CreateProduct(Arguments):
    name: str = Field(min_length=1, max_length=80)
    type: str = Field(min_length=1, max_length=40)
    institution: str = Field(min_length=1, max_length=80)
    ownership: Decimal = Field(default=Decimal(100), gt=0, le=100)
    shared: bool = False
    ibans: list[str] = Field(default_factory=list, max_length=10)
    source: str | None = Field(default=None, max_length=200)


async def create_product(connection: AsyncConnection, arguments: CreateProduct) -> dict[str, Any]:
    lo = await loaded(connection)
    try:
        key = await configure.create_account(
            connection,
            lo,
            name=arguments.name,
            kind=arguments.type,
            institution=arguments.institution,
            ownership=arguments.ownership / 100,
            shared=arguments.shared,
            ibans=arguments.ibans,
            source_key=arguments.source,
        )
    except configure.Refused as error:
        return {"error": str(error)}
    return {"created": key, "name": arguments.name.strip()}


class UpdateProduct(Arguments):
    product: str = Field(min_length=1, max_length=80)
    name: str | None = Field(default=None, max_length=80)
    type: str | None = Field(default=None, max_length=40)
    institution: str | None = Field(default=None, max_length=80)
    ownership: Decimal | None = Field(default=None, gt=0, le=100)
    shared: bool | None = None
    ibans: list[str] | None = Field(default=None, max_length=10)
    value_mode: Literal["balance", "computed", "snapshot", "manual", ""] | None = None
    source: str | None = Field(default=None, max_length=200)


async def update_product(connection: AsyncConnection, arguments: UpdateProduct) -> dict[str, Any]:
    lo = await loaded(connection)
    try:
        key = product_named(lo, arguments.product)
        await configure.update_account(
            connection,
            lo,
            key,
            configure.Change(
                name=arguments.name,
                kind=arguments.type,
                institution=arguments.institution,
                ownership=arguments.ownership / 100 if arguments.ownership is not None else None,
                shared=arguments.shared,
                ibans=arguments.ibans,
                value_mode=arguments.value_mode,
                source_key=arguments.source,
            ),
        )
    except configure.Refused as error:
        return {"error": str(error)}
    return {"updated": key}


class FundIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    value: Decimal | None = Field(default=None, ge=0)
    weight: Decimal | None = Field(default=None, ge=0, le=100)


class RecordComposition(Arguments):
    product: str = Field(min_length=1, max_length=80)
    on: date | None = None
    value: Decimal | None = Field(default=None, gt=0)
    funds: list[FundIn] = Field(min_length=1, max_length=60)


async def record_composition(
    connection: AsyncConnection, arguments: RecordComposition
) -> dict[str, Any]:
    lo = await loaded(connection)
    try:
        key = product_named(lo, arguments.product)
        out = await configure.set_composition(
            connection,
            lo,
            key,
            arguments.on or texts.today(),
            [configure.Typed(f.name, f.value, f.weight) for f in arguments.funds],
            arguments.value,
        )
    except configure.Refused as error:
        return {"error": str(error)}
    return plain({"product": key, **out})


class RecordValue(Arguments):
    product: str = Field(min_length=1, max_length=80)
    value: Decimal = Field(ge=0)
    on: date | None = None


async def record_value(connection: AsyncConnection, arguments: RecordValue) -> dict[str, Any]:
    lo = await loaded(connection)
    try:
        key = product_named(lo, arguments.product)
        await configure.set_value(
            connection, lo, key, arguments.on or texts.today(), arguments.value
        )
    except configure.Refused as error:
        return {"error": str(error)}
    return {"product": key, "value": float(arguments.value)}


class ClassifyFund(Arguments):
    fund: str = Field(min_length=1, max_length=160)
    asset: Literal["equity", "bond", "real_estate", "cash", "crypto", "other"]
    regions: dict[str, Decimal] = Field(default_factory=dict)


async def classify_fund(connection: AsyncConnection, arguments: ClassifyFund) -> dict[str, Any]:
    lo = await loaded(connection)
    symbol = (
        arguments.fund
        if arguments.fund in configure.known_funds(lo)
        or any(h.symbol == arguments.fund for h in lo.book.holdings)
        else configure.symbol_for(lo, arguments.fund)
    )
    try:
        await configure.classify_fund(connection, symbol, arguments.asset, arguments.regions)
    except configure.Refused as error:
        return {"error": str(error)}
    return {"fund": symbol, "asset": arguments.asset}


class DeleteRule(Arguments):
    rule_id: str = Field(min_length=1, max_length=60)
    keep: bool = True


async def delete_rule(connection: AsyncConnection, arguments: DeleteRule) -> dict[str, Any]:
    lo = await loaded(connection)
    try:
        kept = await configure.delete_rule(connection, lo, arguments.rule_id, arguments.keep)
    except configure.Refused as error:
        return {"error": str(error)}
    return {"deleted": arguments.rule_id, "kept_as_they_are": kept}


TOOLS: dict[str, Tool] = {
    "get_summary": Tool(GetSummary, get_summary),
    "get_movements": Tool(GetMovements, get_movements),
    "get_shared_balance": Tool(GetSharedBalance, get_shared_balance),
    "categorise_movement": Tool(CategoriseMovement, categorise_movement),
    "mark_transfer": Tool(MarkTransfer, mark_transfer),
    "record_shared_expense": Tool(RecordSharedExpense, record_shared_expense),
    "get_products": Tool(GetProducts, get_products),
    "get_composition": Tool(GetComposition, get_composition),
    "get_rules": Tool(GetRules, get_rules),
    "create_product": Tool(CreateProduct, create_product),
    "update_product": Tool(UpdateProduct, update_product),
    "record_composition": Tool(RecordComposition, record_composition),
    "record_value": Tool(RecordValue, record_value),
    "classify_fund": Tool(ClassifyFund, classify_fund),
    "delete_rule": Tool(DeleteRule, delete_rule),
}
