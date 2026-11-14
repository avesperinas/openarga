from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import current_spaces, current_user
from arga_widgets import envelope
from money import analysis, catalog, common, configure, history, importer, kpis, products, texts
from money import book as books
from money.db import engine
from money.interpret import merchant_key
from money.ledger import balance_check
from money.model import OTHER, Book
from money.panel import build as home_panel_of
from money.shared import monthly_average, totals, year_balance
from money.texts import t
from money.value import value_at

router = APIRouter()

APP_ROLE = "mod_money"


@asynccontextmanager
async def as_app() -> AsyncIterator[AsyncConnection]:
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{APP_ROLE}"'))
        yield connection


async def loaded(connection: AsyncConnection) -> books.Loaded:
    return await books.load(connection, current_user.get(None))


def money(value: Decimal) -> float:
    return float(round(value, 2))


@router.get("/state")
async def state() -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
    b = lo.book
    today = texts.today()
    checks = [
        balance_check(b, a, today - timedelta(days=60), today)
        for a in b.accounts.values()
        if a.asset_class == "cash" and a.value == "balance"
    ]
    cutoff = lo.settings.cutoff
    counts: dict[str, int] = {}
    for fid, s in lo.statuses.items():
        if cutoff and b.fact(fid).on < cutoff:
            continue
        counts[s] = counts.get(s, 0) + 1
    years = sorted(
        {f.on.year for f in b.facts}
        | {h.year for h in lo.history}
        | history.years(lo.flows, lo.valuations),
        reverse=True,
    )
    return {
        "configured": bool(b.accounts),
        "me": lo.settings.me_name,
        "other": lo.settings.other_name,
        "cutoff": lo.settings.cutoff,
        "accounts": [
            {
                "key": a.id,
                "name": a.name,
                "institution": a.institution,
                "type": a.type,
                "type_label": catalog.account_types().get(a.type, {}).get("label", a.type),
                "group": analysis.group_of(a),
                "asset_class": a.asset_class,
                "liquid": a.liquid,
                "movements": a.movements,
                "value": a.value,
                "shared": a.shared_space,
                "ownership": float(a.ownership),
                "role": a.role,
            }
            for a in b.accounts.values()
        ],
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "nature": c.nature,
                "ownership": c.ownership,
                "split": c.split,
                "not_living": c.not_living,
                "not_basic": c.not_basic,
            }
            for c in b.categories.values()
        ],
        "account_types": [
            {"value": k, "label": t.get("label", k)} for k, t in catalog.account_types().items()
        ],
        "health": [
            {
                "account": c.account,
                "ok": c.ok,
                "first": c.first,
                "last": c.last,
                "gap": money(c.gap) if c.gap is not None else None,
            }
            for c in checks
        ],
        "counts": counts,
        "unmapped": [
            {"key": u.key, "bank": u.bank, "name": u.name, "iban_tail": u.iban_tail}
            for u in lo.unmapped
        ],
        "assets": [{"value": k, "label": v} for k, v in products.assets().items()],
        "regions": [{"value": k, "label": v} for k, v in products.regions().items()],
        "years": years,
        "rules": len(lo.rules),
    }


def account_name(b: Book, key: str, lo: books.Loaded) -> tuple[str, str]:
    if key == OTHER:
        return t("account.outside"), "—"
    a = b.accounts.get(key)
    return (a.name, a.institution) if a else (key, "")


def movement_out(lo: books.Loaded, fact_id: str, transfers: dict[str, tuple]) -> dict:
    b = lo.book
    f = b.fact(fact_id)
    name, institution = account_name(b, f.account, lo)
    status = lo.statuses.get(fact_id, "pending")
    parts = [
        {
            "amount": money(i.amount),
            "category": i.category,
            "category_name": b.categories[i.category].name,
            "nature": i.nature,
            "ownership": i.ownership,
            "payer": i.payer,
            "basis": i.basis,
            "equity_in": i.equity_in,
        }
        for i in b.imputations
        if i.fact == fact_id
    ]
    transfer = None
    if fact_id in transfers:
        other_id, basis = transfers[fact_id]
        if other_id is None:
            transfer = {"account": None, "name": lo.settings.other_name, "basis": basis}
        else:
            other = b.fact(other_id)
            oname, _ = account_name(b, other.account, lo)
            transfer = {
                "account": other.account,
                "name": oname,
                "basis": basis,
                "fact": other.id if other.source != "inferred" else None,
                "on": other.on,
            }
    natures = {p["nature"] for p in parts}
    if status in ("transfer", "return", "settlement", "ask", "pending"):
        kind = status
    elif len(natures) > 1:
        kind = "mixed"
    else:
        kind = next(iter(natures), "pending")
    entry = lo.entries.get(fact_id)
    return {
        "id": f.id,
        "on": f.on,
        "value_on": f.value_on,
        "amount": money(f.amount),
        "account": f.account,
        "account_name": name,
        "institution": institution,
        "merchant": lo.merchant_of.get(f.id) or f.text,
        "text": f.text,
        "counterparty": f.counterparty,
        "counterparty_iban": f.counterparty_iban,
        "bank_category": f.bank_category,
        "source": f.source,
        "status": status,
        "kind": kind,
        "parts": parts,
        "transfer": transfer,
        "labelled": fact_id in lo.labels,
        "before_cutoff": bool(lo.settings.cutoff and f.on < lo.settings.cutoff),
        "entry": entry,
    }


def transfer_index(b: Book) -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    for one in b.transfers:
        if one.out_fact:
            out[one.out_fact] = (one.in_fact, one.basis)
            out[one.in_fact] = (one.out_fact, one.basis)
        else:
            out[one.in_fact] = (None, one.basis)
    return out


@router.get("/movements")
async def movements(
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> dict:
    if end < start or (end - start).days > 400:
        raise HTTPException(
            status_code=422, detail="the period goes from one date to another, at most a year"
        )
    async with as_app() as connection:
        lo = await loaded(connection)
    b = lo.book
    index = transfer_index(b)
    rows = [
        movement_out(lo, f.id, index)
        for f in sorted(b.facts, key=lambda f: (f.on, f.id), reverse=True)
        if start <= f.on <= end and f.source != "inferred"
    ]
    return {"movements": rows, "from": start, "to": end}


@router.get("/movement")
async def movement(fact: Annotated[str, Query(alias="id", max_length=300)]) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
    try:
        lo.book.fact(fact)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="no such movement") from error
    out = movement_out(lo, fact, transfer_index(lo.book))
    out["label"] = lo.labels.get(fact)
    out["same_merchant"] = sum(
        1
        for f in lo.book.facts
        if f.id != fact
        and f.source != "inferred"
        and merchant_key(lo.merchant_of.get(f.id) or f.text) == merchant_key(out["merchant"])
    )
    return out


class PartIn(BaseModel):
    amount: Decimal
    category: str
    payer: Literal["account", "me", "other"] | None = None
    equity_in: str | None = Field(default=None, max_length=40)


class LabelIn(BaseModel):
    parts: list[PartIn] = Field(default_factory=list, max_length=12)
    settlement: bool = False
    is_return: bool = False
    transfer_with: str | None = Field(default=None, max_length=100)
    """A transfer with this other account of yours."""


@router.put("/label")
async def label(request: LabelIn, fact: Annotated[str, Query(alias="id", max_length=300)]) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        try:
            f = lo.book.fact(fact)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="no such movement") from error
        said = [
            bool(request.parts),
            request.settlement,
            request.is_return,
            bool(request.transfer_with),
        ]
        if sum(said) > 1:
            raise HTTPException(
                status_code=422, detail="either parts, settlement, return or transfer"
            )
        if request.parts:
            total = sum((p.amount for p in request.parts), Decimal(0))
            if total.copy_abs() != f.amount.copy_abs():
                raise HTTPException(
                    status_code=422, detail="the parts have to add up to the amount"
                )
            for p in request.parts:
                if p.category not in lo.book.categories:
                    raise HTTPException(status_code=422, detail="that category does not exist")
            sign = -1 if f.amount < 0 else 1
            spec = {
                "parts": [
                    {
                        "amount": str(sign * p.amount.copy_abs()),
                        "category": p.category,
                        "payer": p.payer
                        or _payer(lo, f.account, lo.book.categories[p.category].ownership),
                        "equity_in": p.equity_in,
                    }
                    for p in request.parts
                ]
            }
        elif request.settlement:
            spec = {"settlement": True}
        elif request.is_return:
            spec = {"return": True}
        elif request.transfer_with:
            if request.transfer_with not in lo.book.accounts or request.transfer_with == f.account:
                raise HTTPException(status_code=422, detail="choose another account of yours")
            spec = {"transfer_with": request.transfer_with}
        else:
            raise HTTPException(status_code=422, detail="what it is is missing")
        await connection.execute(
            text("""
            insert into money.money_v1_label (fact_id, spec) values (:f, cast(:s as jsonb))
            on conflict (user_id, fact_id) do update set spec = excluded.spec, updated_at = now()
        """),
            {"f": fact, "s": books.dumps(spec)},
        )
        await books.bump(connection)
        lo = await loaded(connection)
    return movement_out(lo, fact, transfer_index(lo.book))


def _payer(lo: books.Loaded, account: str, ownership: str) -> str | None:
    if ownership != "shared":
        return None
    a = lo.book.accounts.get(account)
    return "account" if a and a.shared_space else "me"


@router.delete("/label")
async def unlabel(fact: Annotated[str, Query(alias="id", max_length=300)]) -> dict:
    async with as_app() as connection:
        await connection.execute(
            text("delete from money.money_v1_label where fact_id = :f"), {"f": fact}
        )
        await books.bump(connection)
        lo = await loaded(connection)
    try:
        return movement_out(lo, fact, transfer_index(lo.book))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="no such movement") from error


class MerchantRuleIn(BaseModel):
    category: str


@router.post("/merchant-rule")
async def merchant_rule(
    request: MerchantRuleIn, fact: Annotated[str, Query(alias="id", max_length=300)]
) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        try:
            f = lo.book.fact(fact)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="no such movement") from error
        if request.category not in lo.book.categories:
            raise HTTPException(status_code=422, detail="that category does not exist")
        name = lo.merchant_of.get(f.id) or f.text
        key = merchant_key(name)
        await connection.execute(
            text("""
            delete from money.money_v1_rule
            where origin = 'merchant' and spec->>'merchant' = :m
        """),
            {"m": key},
        )
        await connection.execute(
            text("""
            insert into money.money_v1_rule (position, spec, origin)
            values (coalesce((select min(position) from money.money_v1_rule), 0) - 1,
                    cast(:s as jsonb), 'merchant')
        """),
            {"s": books.dumps({"merchant": key, "category": request.category})},
        )
        await books.bump(connection)
        lo = await loaded(connection)
    changed = sum(
        1
        for i in lo.book.imputations
        if i.category == request.category
        and i.basis == "rule"
        and merchant_key(lo.merchant_of.get(i.fact) or "") == key
    )
    return {"merchant": name, "movements": changed}


@router.get("/shared")
async def shared(year: Annotated[int | None, Query(ge=2000, le=2100)] = None) -> dict:
    today = texts.today()
    year = year or today.year
    async with as_app() as connection:
        lo = await loaded(connection)
        await common.publish(connection, lo, today)
        view = await common.year_view(connection, lo, year, today)
        if view.role == common.MEMBER:
            entries = await common.member_entries(
                connection, lo.settings.space_id, current_user.get(), year
            )
        else:
            entries = keeper_entries(lo, year)
    months = view.months
    r = view.ratio_me
    yb = year_balance(months, r, year)
    closed, per_month = monthly_average(months, year, today)
    return {
        "year": year,
        "role": view.role,
        "kept_at": view.kept_at,
        "has_keeper": view.role != common.MEMBER or view.keeper is not None,
        "common_categories": view.categories,
        "me": view.me_name,
        "other": view.other_name,
        "settled": view.settled,
        "ratio_me": float(round(r, 4)),
        "balance_me": money(yb.balance_me),
        "total": money(yb.total),
        "by_category": sorted(
            ({"name": k, "amount": money(v)} for k, v in yb.by_category.items()),
            key=lambda c: -c["amount"],
        ),
        "average": {
            "months": closed,
            "total": money(sum(per_month.values(), Decimal(0))) if closed else None,
            "by_category": {k: money(v) for k, v in per_month.items()},
        },
        "months": [
            {
                "month": m.month,
                "source": m.source,
                "total": money(m.total),
                "mine": money(m.obligation_me(r)),
                "balance_me": money(m.balance_me(r)),
                "paid": {
                    "account": money(m.paid_account),
                    "me": money(m.paid_me),
                    "other": money(m.paid_other),
                },
                "deposits": {"me": money(m.deposits_me), "other": money(m.deposits_other)},
                "by_category": sorted(
                    (
                        {"name": k, "amount": money(v), "split": m.split_of.get(k)}
                        for k, v in m.by_category.items()
                    ),
                    key=lambda c: -c["amount"],
                ),
            }
            for m in months
        ],
        "entries": entries,
        "incomes": [
            {
                "person": i.person,
                "from": i.from_on,
                "to": i.to_on,
                "salary": money(i.salary),
                "extra": money(i.extra),
            }
            for i in lo.incomes
            if i.from_on.year <= year <= i.to_on.year
        ],
        **incomes_out(lo, year),
    }


def keeper_entries(lo: books.Loaded, year: int) -> list[dict]:
    b = lo.book
    out = []
    for fid, e in lo.entries.items():
        f = b.fact(fid)
        if f.on.year != year:
            continue
        imp = next(i for i in b.imputations if i.fact == fid)
        out.append(
            {
                "id": e["id"],
                "fact": fid,
                "on": f.on,
                "amount": money(-f.amount),
                "description": f.text,
                "payer": e["payer"],
                "category": imp.category,
                "category_name": b.categories[imp.category].name,
            }
        )
    out.sort(key=lambda e: e["on"], reverse=True)
    return out


def incomes_out(lo: books.Loaded, year: int) -> dict:
    counted = totals(lo.incomes, year)
    space = lo.settings.space_id
    return {
        "income_totals": {p: money(counted[p]) for p in ("me", "other")},
        "space_id": str(space) if space else None,
    }


@router.get("/history")
async def history_year(year: Annotated[int, Query(ge=2000, le=2100)]) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
    months = []
    for m in range(1, 13):
        hm = history.month(lo.flows, year, m)
        end = date(year + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        values = {
            k: money(v.value)
            for k, v in history.latest(lo.valuations, end).items()
            if v.on.year == year and v.on.month == m
        }
        if not (hm.income or hm.expense or hm.contributions or hm.others or values):
            continue
        months.append(
            {
                "month": m,
                "income": {k: money(v) for k, v in hm.income.items()},
                "expense": {k: money(v) for k, v in hm.expense.items()},
                "contributions": {k: money(v) for k, v in hm.contributions.items()},
                "others": {k: money(v) for k, v in hm.others.items()},
                "values": values,
            }
        )
    return {"year": year, "cutoff": lo.settings.cutoff, "months": months}


class EntryIn(BaseModel):
    payer: Literal["me", "other"]
    on: date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)


@router.post("/shared/entries", status_code=201)
async def add_entry(request: EntryIn) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        if lo.settings.space_id is not None:
            name = request.category
            own = lo.book.categories.get(request.category)
            if own is not None:
                name = own.name
            try:
                entry = await common.add_entry(
                    connection,
                    lo,
                    current_user.get(),
                    request.payer,
                    request.on,
                    request.amount,
                    request.description.strip(),
                    name,
                )
            except common.Refused as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            await books.bump(connection)
            return {"id": entry}
        try:
            UUID(request.category)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="that category does not exist") from error
        found = (
            await connection.execute(
                text("select 1 from money.money_v1_category where id = :c"),
                {"c": request.category},
            )
        ).first()
        if not found:
            raise HTTPException(status_code=422, detail="that category does not exist")
        row = (
            await connection.execute(
                text("""
            insert into money.money_v1_entry (payer, on_date, amount, description, category_id)
            values (:p, :d, :a, :t, :c) returning id
        """),
                {
                    "p": request.payer,
                    "d": request.on,
                    "a": request.amount,
                    "t": request.description.strip(),
                    "c": request.category,
                },
            )
        ).first()
        await books.bump(connection)
    return {"id": str(row.id)}


@router.delete("/shared/entries/{entry_id}", status_code=204)
async def remove_entry(entry_id: UUID) -> None:
    async with as_app() as connection:
        if await common.remove_entry(connection, entry_id):
            await books.bump(connection)
            return
        gone = await connection.execute(
            text("delete from money.money_v1_entry where id = :i"), {"i": entry_id}
        )
        if gone.rowcount == 0:
            raise HTTPException(status_code=404, detail="no such expense")
        await books.bump(connection)


class YearIn(BaseModel):
    settled: bool


@router.put("/shared/years/{year}")
async def settle_year(year: int, request: YearIn) -> dict:
    if not 2000 <= year <= 2100:
        raise HTTPException(status_code=422, detail="year out of range")
    async with as_app() as connection:
        if common.role_of(await loaded(connection)) == common.MEMBER:
            raise HTTPException(
                status_code=409, detail="the year is settled by whoever keeps the shared account"
            )
        await connection.execute(
            text("""
            insert into money.money_v1_year (year, settled) values (:y, :s)
            on conflict (user_id, year) do update set settled = excluded.settled
        """),
            {"y": year, "s": request.settled},
        )
        await books.bump(connection)
        await common.publish(connection, await loaded(connection), texts.today())
    return {"year": year, "settled": request.settled}


class IncomeIn(BaseModel):
    person: Literal["me", "other"]
    from_on: date = Field(alias="from")
    to_on: date = Field(alias="to")
    salary: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    extra: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)


class IncomesIn(BaseModel):
    incomes: list[IncomeIn] = Field(max_length=24)


@router.put("/shared/incomes/{year}")
async def set_incomes(year: int, request: IncomesIn) -> dict:
    for i in request.incomes:
        if i.to_on < i.from_on or not (i.from_on.year <= year <= i.to_on.year):
            raise HTTPException(
                status_code=422,
                detail="each range goes from one date to another and touches the year",
            )
    async with as_app() as connection:
        await connection.execute(
            text("""
            delete from money.money_v1_income
            where extract(year from from_on) <= :y and extract(year from to_on) >= :y
        """),
            {"y": year},
        )
        for i in request.incomes:
            await connection.execute(
                text("""
                insert into money.money_v1_income (person, from_on, to_on, salary, extra)
                values (:p, :f, :t, :s, :e)
            """),
                {"p": i.person, "f": i.from_on, "t": i.to_on, "s": i.salary, "e": i.extra},
            )
        await books.bump(connection)
    return {"year": year, "incomes": len(request.incomes)}


class SpaceIn(BaseModel):
    space_id: UUID | None


@router.put("/shared/space")
async def set_space(request: SpaceIn) -> dict:
    if request.space_id is not None and request.space_id not in current_spaces.get():
        raise HTTPException(status_code=404, detail="you are not in that space")
    async with as_app() as connection:
        await connection.execute(
            text("""
            insert into money.money_v1_setting (space_id, me_name, other_name)
            values (:s, :me, :other)
            on conflict (user_id) do update set space_id = excluded.space_id, updated_at = now()
        """),
            {"s": request.space_id, "me": t("person.me"), "other": t("person.other")},
        )
        await books.bump(connection)
    return {"space_id": str(request.space_id) if request.space_id else None}


@router.post("/import")
async def import_bundle(request: importer.Bundle) -> dict:
    async with as_app() as connection:
        try:
            counts = await importer.apply(connection, request)
        except importer.Refused as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        await books.bump(connection)
    return counts


@router.get("/export")
async def export_bundle() -> dict:
    async with as_app() as connection:
        return await importer.export(connection)


def kpi_out(k: kpis.Kpi) -> dict:
    return {
        "key": k.key,
        "label": k.label,
        "value": money(k.value) if k.value is not None else None,
        "previous": money(k.previous) if k.previous is not None else None,
        "target": money(k.target) if k.target is not None else None,
        "detail": k.detail,
        "carried": k.carried,
    }


@router.get("/summary")
async def summary() -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
    return {
        "kpis": [kpi_out(k) for k in kpis.compute(lo, texts.today())],
        "emergency_months": lo.settings.emergency_months,
    }


class SettingsIn(BaseModel):
    emergency_months: int = Field(ge=1, le=24)
    emergency_account: str | None = Field(default=None, max_length=40)


@router.put("/settings")
async def change_settings(request: SettingsIn) -> dict:
    async with as_app() as connection:
        if request.emergency_account is not None:
            found = (
                await connection.execute(
                    text("select 1 from money.money_v1_account where key = :k"),
                    {"k": request.emergency_account},
                )
            ).first()
            if not found:
                raise HTTPException(status_code=422, detail="no such account")
        await connection.execute(
            text("""
            insert into money.money_v1_setting (emergency_months, me_name, other_name)
            values (:m, :me, :other)
            on conflict (user_id) do update set emergency_months = excluded.emergency_months,
                updated_at = now()
        """),
            {"m": request.emergency_months, "me": t("person.me"), "other": t("person.other")},
        )
        await connection.execute(
            text("""
            update money.money_v1_account
            set role = case when key = :k then 'emergency_fund' else null end
            where role = 'emergency_fund' or key = :k
        """),
            {"k": request.emergency_account or ""},
        )
        await books.bump(connection)
    return {
        "emergency_months": request.emergency_months,
        "emergency_account": request.emergency_account,
    }


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: str = Field(min_length=1, max_length=40)
    ownership: Decimal = Field(gt=0, le=1)
    shared: bool


@router.put("/accounts/{key}")
async def change_account(key: str, request: AccountIn) -> dict:
    if request.type not in catalog.account_types():
        raise HTTPException(status_code=422, detail="no such account type")
    async with as_app() as connection:
        found = (
            await connection.execute(
                text("""
                update money.money_v1_account
                set name = :name, type = :type, ownership = :ownership, shared_space = :shared
                where key = :key
                returning key
            """),
                {"key": key, **request.model_dump()},
            )
        ).first()
        if not found:
            raise HTTPException(status_code=404, detail="no such account")
        await books.bump(connection)
    return {"key": key, **request.model_dump(mode="json")}


class NewAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: str = Field(min_length=1, max_length=40)
    institution: str = Field(min_length=1, max_length=80)
    ownership: Decimal = Field(default=Decimal(1), gt=0, le=1)
    shared: bool = False
    ibans: list[str] = Field(default_factory=list, max_length=10)
    source: str | None = Field(default=None, max_length=200)


def refused(error: configure.Refused) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


@router.post("/accounts", status_code=201)
async def add_account(request: NewAccountIn) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        try:
            key = await configure.create_account(
                connection,
                lo,
                name=request.name,
                kind=request.type,
                institution=request.institution,
                ownership=request.ownership,
                shared=request.shared,
                ibans=request.ibans,
                source_key=request.source,
            )
        except configure.Refused as error:
            raise refused(error) from error
        lo = await loaded(connection)
        return plain(products.detail(lo, lo.book.accounts[key], texts.today()))


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    type: str | None = Field(default=None, max_length=40)
    institution: str | None = Field(default=None, max_length=80)
    ownership: Decimal | None = None
    shared: bool | None = None
    ibans: list[str] | None = Field(default=None, max_length=10)
    value: str | None = Field(default=None, max_length=20)
    source: str | None = Field(default=None, max_length=200)


@router.patch("/accounts/{key}")
async def patch_account(key: str, request: AccountPatch) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        try:
            await configure.update_account(
                connection,
                lo,
                key,
                configure.Change(
                    name=request.name,
                    kind=request.type,
                    institution=request.institution,
                    ownership=request.ownership,
                    shared=request.shared,
                    ibans=request.ibans,
                    value_mode=request.value,
                    source_key=request.source,
                ),
            )
        except configure.Refused as error:
            raise refused(error) from error
        lo = await loaded(connection)
        return plain(products.detail(lo, lo.book.accounts[key], texts.today()))


@router.get("/products/{key}")
async def product(key: str) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
    account = lo.book.accounts.get(key)
    if account is None:
        raise HTTPException(status_code=404, detail="no such product")
    return plain(products.detail(lo, account, texts.today()))


class TypedFundIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: Decimal | None = Field(default=None, ge=0)
    weight: Decimal | None = Field(default=None, ge=0, le=100)
    symbol: str | None = Field(default=None, max_length=160)


class CompositionIn(BaseModel):
    on: date
    total: Decimal | None = Field(default=None, gt=0)
    funds: list[TypedFundIn] = Field(min_length=1, max_length=60)


@router.put("/accounts/{key}/composition")
async def set_composition(key: str, request: CompositionIn) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        try:
            await configure.set_composition(
                connection,
                lo,
                key,
                request.on,
                [configure.Typed(f.name, f.value, f.weight, f.symbol) for f in request.funds],
                request.total,
            )
        except configure.Refused as error:
            raise refused(error) from error
        lo = await loaded(connection)
        return plain(products.detail(lo, lo.book.accounts[key], texts.today()))


@router.delete("/accounts/{key}/composition")
async def remove_composition(key: str, on: Annotated[date, Query()]) -> dict:
    async with as_app() as connection:
        await configure.remove_composition(connection, key, on)
        lo = await loaded(connection)
    account = lo.book.accounts.get(key)
    if account is None:
        raise HTTPException(status_code=404, detail="no such product")
    return plain(products.detail(lo, account, texts.today()))


class ValueIn(BaseModel):
    on: date
    value: Decimal = Field(ge=0)


@router.put("/accounts/{key}/value")
async def set_value(key: str, request: ValueIn) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        try:
            await configure.set_value(connection, lo, key, request.on, request.value)
        except configure.Refused as error:
            raise refused(error) from error
        lo = await loaded(connection)
        return plain(products.detail(lo, lo.book.accounts[key], texts.today()))


@router.get("/funds")
async def funds() -> list[dict]:
    async with as_app() as connection:
        lo = await loaded(connection)
    dummy = next(iter(lo.book.accounts.values()), None)
    out = []
    for symbol, name in sorted(configure.known_funds(lo).items(), key=lambda kv: kv[1]):
        kind = (
            products.kind_of(lo, dummy, symbol)
            if dummy
            else products.Kind("other", {}, products.UNKNOWN)
        )
        out.append(
            {
                "symbol": symbol,
                "name": name,
                "asset": kind.asset,
                "classified": kind.source,
            }
        )
    return plain(out)


class FundKindIn(BaseModel):
    asset: str = Field(max_length=20)
    regions: dict[str, Decimal] = Field(default_factory=dict)


@router.put("/funds/{symbol}")
async def classify_fund(symbol: str, request: FundKindIn) -> dict:
    async with as_app() as connection:
        try:
            await configure.classify_fund(connection, symbol, request.asset, request.regions)
        except configure.Refused as error:
            raise refused(error) from error
    return {"symbol": symbol, "asset": request.asset}


@router.delete("/funds/{symbol}", status_code=204)
async def unclassify_fund(symbol: str) -> None:
    async with as_app() as connection:
        await configure.unclassify_fund(connection, symbol)


@router.get("/rules")
async def rules() -> list[dict]:
    async with as_app() as connection:
        lo = await loaded(connection)
    return products.describe_rules(lo)


@router.delete("/rules/{rule_id}")
async def remove_rule(rule_id: UUID, keep: bool = True) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        try:
            kept = await configure.delete_rule(connection, lo, str(rule_id), keep)
        except configure.Refused as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    return {"kept": kept}


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    split: Literal["fifty_fifty", "proportional"] | None = None
    not_living: bool = False
    not_basic: bool = False


class NewCategoryIn(CategoryIn):
    nature: Literal["income", "expense"]
    ownership: Literal["individual", "shared"]


def _category_problem(name: str, ownership: str, split: str | None) -> None:
    if name != name.strip():
        raise HTTPException(status_code=422, detail="the name cannot start or end with a space")
    if (ownership == "shared") != (split is not None):
        raise HTTPException(
            status_code=422, detail="a shared category says how it is split; one of yours does not"
        )


async def _name_taken(
    connection: AsyncConnection, nature: str, ownership: str, name: str, other_than: str | None
) -> bool:
    return (
        await connection.execute(
            text("""
            select 1 from money.money_v1_category
            where nature = :nature and ownership = :ownership and name = :name
              and (cast(:id as uuid) is null or id <> cast(:id as uuid))
        """),
            {"nature": nature, "ownership": ownership, "name": name, "id": other_than},
        )
    ).first() is not None


@router.put("/categories/{category_id}")
async def change_category(category_id: UUID, request: CategoryIn) -> dict:
    async with as_app() as connection:
        row = (
            await connection.execute(
                text("select name, nature, ownership from money.money_v1_category where id = :id"),
                {"id": category_id},
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="no such category")
        _category_problem(request.name, row.ownership, request.split)
        if await _name_taken(connection, row.nature, row.ownership, request.name, str(category_id)):
            raise HTTPException(
                status_code=422, detail="there is already a category with that name"
            )
        await connection.execute(
            text("""
            update money.money_v1_category
            set name = :name, split = :split, not_living = :not_living, not_basic = :not_basic
            where id = :id
        """),
            {"id": category_id, **request.model_dump()},
        )
        if request.name != row.name:
            if row.ownership == "shared":
                await connection.execute(
                    text("""
                    update money.money_v1_history set category = :new
                    where kind = 'expense' and category = :old
                """),
                    {"new": request.name, "old": row.name},
                )
            else:
                await connection.execute(
                    text("""
                    update money.money_v1_history_flow set category = :new
                    where kind = :nature and category = :old
                """),
                    {"new": request.name, "old": row.name, "nature": row.nature},
                )
        await books.bump(connection)
    return {"id": str(category_id), **request.model_dump()}


@router.post("/categories", status_code=201)
async def add_category(request: NewCategoryIn) -> dict:
    _category_problem(request.name, request.ownership, request.split)
    async with as_app() as connection:
        if await _name_taken(connection, request.nature, request.ownership, request.name, None):
            raise HTTPException(
                status_code=422, detail="there is already a category with that name"
            )
        new_id = (
            await connection.execute(
                text("""
                insert into money.money_v1_category
                    (nature, ownership, name, split, not_living, not_basic, position)
                values (:nature, :ownership, :name, :split, :not_living, :not_basic,
                    coalesce((select max(position) + 1 from money.money_v1_category), 0))
                returning id
            """),
                request.model_dump(),
            )
        ).scalar_one()
        await books.bump(connection)
    return {"id": str(new_id), **request.model_dump()}


KPI_WIDGETS = {
    "networth": ("kpi-delta", "up"),
    "liquid": ("kpi-delta", "up"),
    "cash": ("kpi", None),
    "emergency": ("progress", None),
    "expense": ("kpi-delta", "down"),
    "basic": ("kpi-delta", "down"),
}


def widget_of(k: kpis.Kpi) -> dict:
    kind, good = KPI_WIDGETS[k.key]
    uncertainty = (
        {"summary": t("widget.not_today", accounts=", ".join(k.carried[:3]))} if k.carried else None
    )
    if k.value is None:
        return envelope(kind, "empty", {"detail": k.detail or t("widget.no_data")})
    if kind == "progress":
        body = {
            "value": money(k.value),
            "target": money(k.target) if k.target else None,
            "unit": texts.symbol(),
            "label": t("widget.of_target"),
        }
    else:
        body = {"value": money(k.value), "unit": texts.symbol()}
        if kind == "kpi-delta":
            body |= {
                "previous": money(k.previous) if k.previous is not None else 0,
                "since": t("widget.year_ago"),
                "good_when": good,
            }
    if k.detail:
        body["detail"] = k.detail
    return envelope(kind, "ready", body, uncertainty)


async def pending_shared(
    connection: AsyncConnection, lo: books.Loaded, today: date
) -> tuple[Decimal, list[int], str]:
    total, open_years, other = Decimal(0), [], lo.settings.other_name
    for year in await common.years(connection, lo, today):
        if year > today.year:
            continue
        view = await common.year_view(connection, lo, year, today)
        other = view.other_name
        if view.settled:
            continue
        yb = year_balance(view.months, view.ratio_me, year)
        if yb.total or yb.balance_me:
            total += yb.balance_me
            open_years.append(year)
    return total, open_years, other


@router.get("/panel")
async def home_panel() -> dict:
    today = texts.today()
    async with as_app() as connection:
        lo = await loaded(connection)
        if not lo.book.accounts and common.role_of(lo) != common.MEMBER:
            raise HTTPException(status_code=404, detail=t("widget.no_accounts"))
        owed, years, other = await pending_shared(connection, lo, today)
    cutoff = lo.settings.cutoff
    waiting = sum(
        1
        for fid, status in lo.statuses.items()
        if status in ("ask", "pending") and not (cutoff and lo.book.fact(fid).on < cutoff)
    )
    return home_panel_of(lo, today, owed, other or t("person.other_lower"), years, waiting)


@router.get("/widgets/shared")
async def shared_widget() -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
        if not lo.book.accounts and common.role_of(lo) != common.MEMBER:
            return envelope("kpi", "empty", {"detail": t("widget.no_accounts")})
        owed, years, other = await pending_shared(connection, lo, texts.today())
    if not years:
        return envelope(
            "kpi", "ready", {"value": 0, "unit": texts.symbol(), "detail": t("widget.settled")}
        )
    when = ", ".join(str(y) for y in years)
    if abs(owed) < Decimal("0.005"):
        detail = t("widget.even", years=when)
    elif owed > 0:
        detail = t("widget.owes_you", other=other, years=when)
    else:
        detail = t("widget.you_owe", other=other, years=when)
    return envelope(
        "kpi", "ready", {"value": money(owed), "unit": texts.symbol(), "detail": detail}
    )


@router.get("/widgets/{key}")
async def kpi_widget(key: str) -> dict:
    if key == "account":
        raise HTTPException(status_code=422, detail="the account is missing")
    if key not in KPI_WIDGETS:
        raise HTTPException(status_code=404, detail="no such widget")
    async with as_app() as connection:
        lo = await loaded(connection)
    if not lo.book.accounts:
        kind = KPI_WIDGETS[key][0]
        return envelope(kind, "empty", {"detail": t("widget.no_accounts")})
    found = next(k for k in kpis.compute(lo, texts.today()) if k.key == key)
    return widget_of(found)


@router.get("/widgets/account/options")
async def account_options() -> list[dict]:
    async with as_app() as connection:
        lo = await loaded(connection)
    return [
        {"value": a.id, "label": f"{a.name} · {a.institution}"} for a in lo.book.accounts.values()
    ]


@router.get("/widgets/account/value")
async def account_widget(option: Annotated[str | None, Query(max_length=40)] = None) -> dict:
    async with as_app() as connection:
        lo = await loaded(connection)
    account = lo.book.accounts.get(option or "")
    if account is None:
        return envelope("kpi", "empty", {"detail": t("widget.pick_account")})
    v = value_at(lo.book, account, texts.today(), lo.valuations)
    if not v.known:
        return envelope("kpi", "empty", {"detail": t("widget.no_balance", account=account.name)})
    detail = account.name
    if v.estimated:
        detail += " · " + t("widget.estimated", day=f"{v.estimated.day}/{v.estimated.month}")
    elif v.since and (texts.today() - v.since).days > 7:
        detail += " · " + t("widget.as_of", day=f"{v.since.day}/{v.since.month}")
    return envelope(
        "kpi", "ready", {"value": money(v.amount), "unit": texts.symbol(), "detail": detail}
    )


FINE = {"share", "simple", "period_return", "rate", "ownership", "change"}


def plain(value, key: str | None = None):
    if isinstance(value, Decimal):
        return float(round(value, 4 if key in FINE else 2))
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: plain(v, k if isinstance(k, str) else None) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [plain(v, key) for v in value]
    return value


Start = Annotated[date, Query(alias="from")]
End = Annotated[date, Query(alias="to")]


def checked(start: date, end: date) -> None:
    if end < start or (end - start).days > 366 * 25:
        raise HTTPException(status_code=422, detail="the period goes from one date to a later one")


Groups = Annotated[list[str], Query(alias="group", max_length=50)]
Accounts = Annotated[list[str], Query(alias="account", max_length=200)]


@router.get("/analysis/worth")
async def analysis_worth(
    start: Start,
    end: End,
    home: bool = True,
    whole: bool = False,
    groups: Groups = [],  # noqa: B006
    accounts: Accounts = [],  # noqa: B006
) -> dict:
    checked(start, end)
    async with as_app() as connection:
        lo = await loaded(connection)
    return plain(
        analysis.worth(lo, start, end, home, whole, texts.today(), set(groups), set(accounts))
    )


@router.get("/analysis/investments")
async def analysis_investments(
    start: Start,
    end: End,
    home: bool = True,
    whole: bool = False,
    groups: Groups = [],  # noqa: B006
    accounts: Accounts = [],  # noqa: B006
) -> dict:
    checked(start, end)
    async with as_app() as connection:
        lo = await loaded(connection)
    return plain(
        analysis.investments(lo, start, end, home, whole, texts.today(), set(groups), set(accounts))
    )


@router.get("/analysis/composition")
async def analysis_composition(
    start: Start,
    end: End,
    home: bool = True,
    whole: bool = False,
    groups: Groups = [],  # noqa: B006
    accounts: Accounts = [],  # noqa: B006
) -> dict:
    checked(start, end)
    async with as_app() as connection:
        lo = await loaded(connection)
    return plain(
        products.composition(lo, start, end, home, whole, texts.today(), set(groups), set(accounts))
    )


Scope = Literal["all", "individual", "shared"]
Kind = Literal["all", "basic", "other"]


@router.get("/analysis/spending")
async def analysis_spending(
    start: Start, end: End, scope: Scope = "all", whole: bool = False, kind: Kind = "all"
) -> dict:
    checked(start, end)
    async with as_app() as connection:
        lo = await loaded(connection)
    return plain(analysis.spending(lo, start, end, scope, whole, kind, texts.today()))


@router.get("/analysis/spending/category")
async def analysis_category(
    start: Start,
    end: End,
    name: Annotated[str, Query(min_length=1, max_length=60)],
    ownership: Literal["individual", "shared"],
    whole: bool = False,
) -> dict:
    checked(start, end)
    async with as_app() as connection:
        lo = await loaded(connection)
    return plain(analysis.category_detail(lo, start, end, name, ownership, whole))


@router.get("/analysis/flow")
async def analysis_flow(
    start: Start, end: End, cycle: bool = True, whole: bool = False, rent: bool = True
) -> dict:
    checked(start, end)
    async with as_app() as connection:
        lo = await loaded(connection)
    return plain(analysis.flow(lo, start, end, cycle, whole, texts.today(), rent_invested=rent))


@router.get("/analysis/circuit")
async def analysis_circuit(start: Start, end: End) -> dict:
    checked(start, end)
    async with as_app() as connection:
        lo = await loaded(connection)
    return plain(analysis.circuit(lo, start, end, texts.today()))
