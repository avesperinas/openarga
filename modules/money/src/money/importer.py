from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from money import catalog
from money.book import dumps


class Refused(Exception):
    pass


class SettingsIn(BaseModel):
    cutoff: date | None = None
    me_name: str = Field(default="Me", min_length=1, max_length=40)
    other_name: str = Field(default="The other person", min_length=1, max_length=40)
    holders: list[str] = Field(default_factory=list, max_length=10)
    window_days: int = Field(default=4, ge=1, le=15)
    emergency_months: int = Field(default=3, ge=1, le=24)


class AccountIn(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    name: str = Field(min_length=1, max_length=80)
    institution: str = Field(min_length=1, max_length=80)
    type: str
    movements: Literal["api", "statement", "matched", "manual"] = "matched"
    value: Literal["balance", "computed", "snapshot", "manual"] | None = None
    ownership: Decimal = Field(default=Decimal(1), gt=0, le=1)
    counts_for_savings: bool | None = None
    spending: bool | None = None
    shared_space: bool = False
    aliases: list[str] = Field(default_factory=list, max_length=10)
    ibans: list[str] = Field(default_factory=list, max_length=10)
    match: dict[str, str] | None = None
    role: Literal["emergency_fund"] | None = None


class CategoryIn(BaseModel):
    nature: Literal["income", "expense"]
    ownership: Literal["individual", "shared"]
    name: str = Field(min_length=1, max_length=60)
    split: Literal["fifty_fifty", "proportional"] | None = None
    extended: bool = False
    not_living: bool = False
    not_basic: bool = False

    @property
    def key(self) -> str:
        return f"{self.nature}/{self.ownership}/{self.name}"


class EntryIn(BaseModel):
    payer: Literal["me", "other"]
    on: date
    amount: Decimal = Field(gt=0)
    description: str = Field(min_length=1, max_length=120)
    category: str


class IncomeIn(BaseModel):
    person: Literal["me", "other"]
    from_on: date = Field(alias="from")
    to_on: date = Field(alias="to")
    salary: Decimal = Field(ge=0)
    extra: Decimal = Field(default=Decimal(0), ge=0)


class HistoryIn(BaseModel):
    year: int
    month: int = Field(ge=1, le=12)
    kind: Literal["expense", "deposit"]
    amount: Decimal
    category: str | None = None
    split: Literal["fifty_fifty", "proportional"] | None = None
    payer: Literal["account", "me", "other"] | None = None


class HistoryFlowIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    kind: Literal["income", "expense", "contribution"]
    amount: Decimal
    category: str | None = None
    account: str | None = None
    mine: bool = True
    note: str | None = Field(default=None, max_length=200)


class ValuationIn(BaseModel):
    account: str
    on: date
    value: Decimal
    source: Literal["history", "manual"] = "history"


class HoldingIn(BaseModel):
    account: str
    on: date
    symbol: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    value: Decimal = Field(ge=0)


class FundIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=160)
    asset: Literal["equity", "bond", "real_estate", "cash", "crypto", "other"]
    regions: dict[str, Decimal] = Field(default_factory=dict)


class Bundle(BaseModel):
    settings: SettingsIn = Field(default_factory=SettingsIn)
    accounts: list[AccountIn] = Field(default_factory=list, max_length=100)
    categories: list[CategoryIn] = Field(default_factory=list, max_length=200)
    rules: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    labels: dict[str, dict[str, Any]] = Field(default_factory=dict)
    entries: list[EntryIn] = Field(default_factory=list, max_length=5000)
    incomes: list[IncomeIn] = Field(default_factory=list, max_length=200)
    years: dict[int, bool] = Field(default_factory=dict)
    history: list[HistoryIn] = Field(default_factory=list, max_length=20000)
    history_flow: list[HistoryFlowIn] = Field(default_factory=list, max_length=20000)
    valuations: list[ValuationIn] = Field(default_factory=list, max_length=20000)
    holdings: list[HoldingIn] = Field(default_factory=list, max_length=20000)
    funds: list[FundIn] = Field(default_factory=list, max_length=2000)


TABLES = (
    "holding",
    "fund",
    "label",
    "rule",
    "entry",
    "income",
    "year",
    "history",
    "history_flow",
    "valuation",
    "account",
)


def _category(keys: dict[str, str], name: str | None, where: str) -> str:
    if name not in keys:
        raise Refused(f"{where}: there is no category '{name}'")
    return keys[name]


def _translate_rule(spec: dict, keys: dict[str, str], accounts: set[str]) -> dict:
    out = dict(spec)
    if out.get("category"):
        out["category"] = _category(keys, out["category"], "a rule")
    if out.get("parts"):
        out["parts"] = [
            {**p, "category": _category(keys, p.get("category"), "a rule")} for p in out["parts"]
        ]
    for field in ("account", "transfer_to", "equity_in"):
        if out.get(field) and out[field] not in accounts and out[field] != "@other":
            raise Refused(f"a rule names the account '{out[field]}', which is not there")
    return out


async def apply(connection: AsyncConnection, bundle: Bundle) -> dict[str, int]:
    types = catalog.account_types()
    for a in bundle.accounts:
        if a.type not in types:
            raise Refused(f"account '{a.key}' has a type that does not exist: {a.type}")
    accounts = {a.key for a in bundle.accounts}
    for f in bundle.history_flow:
        if f.kind == "contribution" and f.account not in accounts:
            raise Refused(
                f"a contribution of {f.year}-{f.month:02d} goes to '{f.account}', which is missing"
            )
        if f.kind != "contribution" and f.account:
            raise Refused(f"an {f.kind} of {f.year}-{f.month:02d} goes to no account")
    for v in bundle.valuations:
        if v.account not in accounts:
            raise Refused(f"a valuation of {v.on} is of '{v.account}', which is not there")
    for h in bundle.holdings:
        if h.account not in accounts:
            raise Refused(f"a snapshot of {h.on} is of '{h.account}', which is not there")
    for c in bundle.categories:
        if (c.ownership == "shared") != (c.split is not None):
            raise Refused(
                f"category '{c.key}': only the shared ones, and all of them, say how they are split"
            )

    for table in TABLES:
        await connection.execute(text(f"delete from money.money_v1_{table}"))
    await connection.execute(text("delete from money.money_v1_category"))

    await connection.execute(
        text("""
        insert into money.money_v1_setting
            (cutoff, me_name, other_name, holders, window_days, emergency_months)
        values (:c, :me, :other, :h, :w, :em)
        on conflict (user_id) do update set cutoff = excluded.cutoff, me_name = excluded.me_name,
            other_name = excluded.other_name, holders = excluded.holders,
            window_days = excluded.window_days, emergency_months = excluded.emergency_months,
            updated_at = now()
    """),
        {
            "c": bundle.settings.cutoff,
            "me": bundle.settings.me_name,
            "other": bundle.settings.other_name,
            "h": bundle.settings.holders,
            "w": bundle.settings.window_days,
            "em": bundle.settings.emergency_months,
        },
    )

    for position, a in enumerate(bundle.accounts):
        await connection.execute(
            text("""
            insert into money.money_v1_account
                (key, name, institution, type, movements, value, ownership, counts_for_savings,
                 spending, shared_space, aliases, ibans, match_bank, match_key, position, role)
            values (:key, :name, :inst, :type, :mov, :value, :own, :cfs, :spend, :shared, :aliases,
                    :ibans, :mb, :mk, :pos, :role)
        """),
            {
                "key": a.key,
                "name": a.name,
                "inst": a.institution,
                "type": a.type,
                "mov": a.movements,
                "value": a.value,
                "own": a.ownership,
                "cfs": a.counts_for_savings,
                "spend": a.spending,
                "shared": a.shared_space,
                "aliases": a.aliases,
                "ibans": [i.replace(" ", "").upper() for i in a.ibans],
                "mb": (a.match or {}).get("bank"),
                "mk": (a.match or {}).get("key"),
                "pos": position,
                "role": a.role,
            },
        )

    keys: dict[str, str] = {}
    for position, c in enumerate(bundle.categories):
        row = (
            await connection.execute(
                text("""
            insert into money.money_v1_category
                (nature, ownership, name, split, extended, position, not_living, not_basic)
            values (:n, :o, :name, :s, :e, :p, :nl, :nb) returning id
        """),
                {
                    "n": c.nature,
                    "o": c.ownership,
                    "name": c.name,
                    "s": c.split,
                    "e": c.extended,
                    "p": position,
                    "nl": c.not_living,
                    "nb": c.not_basic,
                },
            )
        ).first()
        keys[c.key] = str(row.id)

    for position, spec in enumerate(bundle.rules):
        await connection.execute(
            text("insert into money.money_v1_rule (position, spec) values (:p, cast(:s as jsonb))"),
            {"p": position, "s": dumps(_translate_rule(spec, keys, accounts))},
        )

    for fact_id, spec in bundle.labels.items():
        out = dict(spec)
        if out.get("parts"):
            out["parts"] = [
                {**p, "category": _category(keys, p.get("category"), f"the label of {fact_id}")}
                for p in out["parts"]
            ]
        await connection.execute(
            text("insert into money.money_v1_label (fact_id, spec) values (:f, cast(:s as jsonb))"),
            {"f": fact_id, "s": dumps(out)},
        )

    for e in bundle.entries:
        await connection.execute(
            text("""
            insert into money.money_v1_entry (payer, on_date, amount, description, category_id)
            values (:p, :d, :a, :t, :c)
        """),
            {
                "p": e.payer,
                "d": e.on,
                "a": e.amount,
                "t": e.description,
                "c": _category(keys, e.category, "a typed expense"),
            },
        )

    for i in bundle.incomes:
        await connection.execute(
            text("""
            insert into money.money_v1_income (person, from_on, to_on, salary, extra)
            values (:p, :f, :t, :s, :e)
        """),
            {"p": i.person, "f": i.from_on, "t": i.to_on, "s": i.salary, "e": i.extra},
        )

    for year, settled in bundle.years.items():
        await connection.execute(
            text("insert into money.money_v1_year (year, settled) values (:y, :s)"),
            {"y": year, "s": settled},
        )

    for h in bundle.history:
        await connection.execute(
            text("""
            insert into money.money_v1_history
                (year, month, kind, amount, category, split, payer)
            values (:y, :m, :k, :a, :c, :s, :p)
        """),
            {
                "y": h.year,
                "m": h.month,
                "k": h.kind,
                "a": h.amount,
                "c": h.category,
                "s": h.split,
                "p": h.payer,
            },
        )

    for f in bundle.history_flow:
        await connection.execute(
            text("""
            insert into money.money_v1_history_flow
                (year, month, kind, amount, category, account, mine, note)
            values (:y, :m, :k, :a, :c, :acc, :mine, :note)
        """),
            {
                "y": f.year,
                "m": f.month,
                "k": f.kind,
                "a": f.amount,
                "c": f.category,
                "acc": f.account,
                "mine": f.mine,
                "note": f.note,
            },
        )

    for v in bundle.valuations:
        await connection.execute(
            text("""
            insert into money.money_v1_valuation (account, on_date, value, source)
            values (:a, :d, :v, :s)
            on conflict (user_id, account, on_date) do update set value = excluded.value
        """),
            {"a": v.account, "d": v.on, "v": v.value, "s": v.source},
        )

    for h in bundle.holdings:
        await connection.execute(
            text("""
            insert into money.money_v1_holding (account, on_date, symbol, name, value)
            values (:a, :d, :s, :n, :v)
        """),
            {"a": h.account, "d": h.on, "s": h.symbol, "n": h.name, "v": h.value},
        )
    for f in bundle.funds:
        await connection.execute(
            text("""
            insert into money.money_v1_fund (symbol, asset, regions)
            values (:s, :a, cast(:r as jsonb))
        """),
            {
                "s": f.symbol,
                "a": f.asset,
                "r": json.dumps({k: float(v) for k, v in f.regions.items()}),
            },
        )

    return {
        "holdings": len(bundle.holdings),
        "funds": len(bundle.funds),
        "history_flow": len(bundle.history_flow),
        "valuations": len(bundle.valuations),
        "accounts": len(bundle.accounts),
        "categories": len(bundle.categories),
        "rules": len(bundle.rules),
        "labels": len(bundle.labels),
        "entries": len(bundle.entries),
        "incomes": len(bundle.incomes),
        "history": len(bundle.history),
    }


async def export(connection: AsyncConnection) -> dict:
    cats = {
        str(r.id): (f"{r.nature}/{r.ownership}/{r.name}", r)
        for r in (
            await connection.execute(
                text("select * from money.money_v1_category order by position")
            )
        ).all()
    }

    def key(cid):
        return cats[cid][0] if cid in cats else cid

    s = (await connection.execute(text("select * from money.money_v1_setting"))).mappings().first()
    rules = []
    for r in (
        await connection.execute(
            text("select spec from money.money_v1_rule order by position, created_at")
        )
    ).all():
        spec = dict(r.spec)
        if spec.get("category"):
            spec["category"] = key(spec["category"])
        if spec.get("parts"):
            spec["parts"] = [{**p, "category": key(p.get("category"))} for p in spec["parts"]]
        rules.append(spec)
    labels = {}
    for r in (
        await connection.execute(text("select fact_id, spec from money.money_v1_label"))
    ).all():
        spec = dict(r.spec)
        if spec.get("parts"):
            spec["parts"] = [{**p, "category": key(p.get("category"))} for p in spec["parts"]]
        labels[r.fact_id] = spec
    return {
        "settings": {
            "cutoff": s["cutoff"] if s else None,
            "me_name": s["me_name"] if s else "Me",
            "other_name": s["other_name"] if s else "The other person",
            "holders": list(s["holders"]) if s else [],
            "window_days": s["window_days"] if s else 4,
            "emergency_months": s["emergency_months"] if s else 3,
        },
        "accounts": [
            {
                "key": a["key"],
                "name": a["name"],
                "institution": a["institution"],
                "type": a["type"],
                "movements": a["movements"],
                "value": a["value"],
                "ownership": float(a["ownership"]),
                "counts_for_savings": a["counts_for_savings"],
                "spending": a["spending"],
                "shared_space": a["shared_space"],
                "aliases": list(a["aliases"]),
                "ibans": list(a["ibans"]),
                "match": (
                    {"bank": a["match_bank"], "key": a["match_key"]} if a["match_bank"] else None
                ),
                "role": a["role"],
            }
            for a in (
                await connection.execute(
                    text("select * from money.money_v1_account order by position")
                )
            )
            .mappings()
            .all()
        ],
        "categories": [
            {
                "nature": r.nature,
                "ownership": r.ownership,
                "name": r.name,
                "split": r.split,
                "extended": r.extended,
                "not_living": r.not_living,
                "not_basic": r.not_basic,
            }
            for _, r in cats.values()
        ],
        "rules": rules,
        "labels": labels,
        "entries": [
            {
                "payer": e.payer,
                "on": e.on_date,
                "amount": float(e.amount),
                "description": e.description,
                "category": key(str(e.category_id)),
            }
            for e in (await connection.execute(text("select * from money.money_v1_entry"))).all()
        ],
        "incomes": [
            {
                "person": i.person,
                "from": i.from_on,
                "to": i.to_on,
                "salary": float(i.salary),
                "extra": float(i.extra),
            }
            for i in (await connection.execute(text("select * from money.money_v1_income"))).all()
        ],
        "years": {
            r.year: r.settled
            for r in (await connection.execute(text("select * from money.money_v1_year"))).all()
        },
        "history": [
            {
                "year": h.year,
                "month": h.month,
                "kind": h.kind,
                "amount": float(h.amount),
                "category": h.category,
                "split": h.split,
                "payer": h.payer,
            }
            for h in (await connection.execute(text("select * from money.money_v1_history"))).all()
        ],
        "history_flow": [
            {
                "year": f.year,
                "month": f.month,
                "kind": f.kind,
                "amount": float(f.amount),
                "category": f.category,
                "account": f.account,
                "mine": f.mine,
                "note": f.note,
            }
            for f in (
                await connection.execute(
                    text("select * from money.money_v1_history_flow order by year, month")
                )
            ).all()
        ],
        "valuations": [
            {"account": v.account, "on": v.on_date, "value": float(v.value), "source": v.source}
            for v in (
                await connection.execute(
                    text("select * from money.money_v1_valuation order by account, on_date")
                )
            ).all()
        ],
        "holdings": [
            {
                "account": h.account,
                "on": h.on_date,
                "symbol": h.symbol,
                "name": h.name,
                "value": float(h.value),
            }
            for h in (
                await connection.execute(
                    text("select * from money.money_v1_holding order by account, on_date, symbol")
                )
            ).all()
        ],
        "funds": [
            {"symbol": f.symbol, "asset": f.asset, "regions": f.regions}
            for f in (
                await connection.execute(text("select * from money.money_v1_fund order by symbol"))
            ).all()
        ],
    }
