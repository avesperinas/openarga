from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import current_spaces
from money import catalog, common, source
from money.history import Flow, Valuation
from money.interpret import Interpreter, Label, Rule, fold
from money.model import OTHER, Account, Book, Category, Fact, Holding, Imputation
from money.shared import HistoryRow, Income, ratio
from money.texts import t


@dataclass(frozen=True)
class Settings:
    cutoff: date | None
    me_name: str
    other_name: str
    holders: tuple[str, ...]
    window_days: int
    revision: int
    emergency_months: int = 3
    space_id: UUID | None = None


@dataclass
class Loaded:
    settings: Settings
    book: Book
    statuses: dict[str, str]
    merchant_of: dict[str, str]
    unmapped: list[source.SourceAccount]
    entries: dict[str, dict]
    incomes: list[Income]
    history: list[HistoryRow]
    settled: dict[int, bool]
    labels: dict[str, dict]
    rules: list[dict]
    flows: list[Flow]
    valuations: list[Valuation]
    source_accounts: list[source.SourceAccount] = field(default_factory=list)
    source_of: dict[str, str] = field(default_factory=dict)
    funds: dict[str, dict] = field(default_factory=dict)
    typed_shots: set[tuple[str, date]] = field(default_factory=set)


async def settings(connection: AsyncConnection) -> Settings:
    row = (
        await connection.execute(
            text(
                "select cutoff, me_name, other_name, holders, window_days, revision, "
                "emergency_months, space_id from money.money_v1_setting"
            )
        )
    ).first()
    if row is None:
        return Settings(None, t("person.me"), t("person.other"), (), 4, 0)
    return Settings(
        row.cutoff,
        row.me_name,
        row.other_name,
        tuple(row.holders),
        row.window_days,
        row.revision,
        row.emergency_months,
        row.space_id if row.space_id in current_spaces.get() else None,
    )


async def bump(connection: AsyncConnection) -> None:
    await connection.execute(
        text("""
        insert into money.money_v1_setting (revision, me_name, other_name) values (1, :me, :other)
        on conflict (user_id) do update
        set revision = money.money_v1_setting.revision + 1, updated_at = now()
    """),
        {"me": t("person.me"), "other": t("person.other")},
    )


async def accounts(connection: AsyncConnection) -> dict[str, Account]:
    rows = (
        (
            await connection.execute(
                text("select * from money.money_v1_account order by position, name")
            )
        )
        .mappings()
        .all()
    )
    types = catalog.account_types()
    out = {}
    for a in rows:
        t = types.get(a["type"], {"asset_class": "cash", "value": "balance"})
        inst = catalog.institution(a["institution"])
        out[a["key"]] = Account(
            id=a["key"],
            name=a["name"],
            institution=a["institution"],
            type=a["type"],
            asset_class=t["asset_class"],
            movements=a["movements"],
            value=a["value"] or t.get("value", "balance"),
            spending=a["spending"] if a["spending"] is not None else t.get("spending", False),
            ownership=Decimal(str(a["ownership"])),
            counts_for_savings=(
                a["counts_for_savings"]
                if a["counts_for_savings"] is not None
                else t.get("counts_for_savings", False)
            ),
            shared_space=a["shared_space"],
            aliases=tuple(inst.get("aliases", ())) + tuple(a["aliases"]),
            internal=inst.get("internal"),
            ibans=tuple(i.replace(" ", "").upper() for i in a["ibans"]),
            cash=t.get("cash", False),
            liquid=t.get("liquid", True),
            role=a["role"],
        )
    return out


async def matches(connection: AsyncConnection) -> dict[tuple[str, str], tuple[str, str]]:
    rows = (
        await connection.execute(
            text(
                "select key, institution, match_bank, match_key from money.money_v1_account "
                "where match_bank is not null and match_key is not null"
            )
        )
    ).all()
    return {(fold(r.match_bank), fold(r.match_key)): (r.key, r.institution) for r in rows}


async def categories(connection: AsyncConnection) -> dict[str, Category]:
    rows = (
        await connection.execute(
            text(
                "select id, name, nature, ownership, split, extended, not_living, not_basic "
                "from money.money_v1_category "
                "order by nature desc, ownership, position, name"
            )
        )
    ).all()
    return {
        str(r.id): Category(
            str(r.id), r.name, r.nature, r.ownership, r.split, r.extended, r.not_living, r.not_basic
        )
        for r in rows
    }


def rule_of(spec: dict) -> Rule:
    fields = {k: v for k, v in spec.items() if k in Rule.__dataclass_fields__}
    for k in ("min_abs", "max_abs"):
        if fields.get(k) is not None:
            fields[k] = Decimal(str(fields[k]))
    if "parts" in fields:
        fields["parts"] = tuple(fields["parts"])
    return Rule(**fields)


def label_of(fact_id: str, spec: dict, cats: dict[str, Category]) -> Label:
    parts = []
    for p in spec.get("parts", ()):
        cat = cats.get(p.get("category"))
        if cat is None:
            continue
        parts.append(
            Imputation(
                fact=fact_id,
                amount=Decimal(str(p["amount"])),
                nature=cat.nature,
                ownership=cat.ownership,
                category=cat.id,
                payer=p.get("payer") if cat.ownership == "shared" else None,
                equity_in=p.get("equity_in"),
                basis="manual",
            )
        )
    return Label(
        fact_id,
        tuple(parts),
        bool(spec.get("settlement")),
        bool(spec.get("return")),
        spec.get("transfer_with"),
    )


_CACHE: OrderedDict[tuple, Loaded] = OrderedDict()


async def fingerprint(connection: AsyncConnection) -> tuple:
    row = (
        await connection.execute(
            text(
                "select count(*) as n, max(ts) as last from money.events where type = any(:types)"
            ),
            {"types": list(source.TYPES)},
        )
    ).first()
    return (row.n, row.last)


async def load(connection: AsyncConnection, user: UUID | None) -> Loaded:
    conf = await settings(connection)
    key = (
        user,
        conf.revision,
        await fingerprint(connection),
        await common.entries_fingerprint(connection, conf.space_id),
    )
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]

    accs = await accounts(connection)
    cats = await categories(connection)
    loaded = await source.load(connection, await matches(connection), conf.holders)
    for k, iban in loaded.own_iban.items():
        a = accs[k]
        if iban not in a.ibans:
            accs[k] = Account(**{**a.__dict__, "ibans": a.ibans + (iban,)})

    facts = list(loaded.facts)
    labels: list[Label] = []
    entries: dict[str, dict] = {}
    keeps = conf.space_id is not None and any(a.shared_space for a in accs.values())
    rows = list(
        (
            await connection.execute(
                text(
                    "select id, payer, on_date, amount, description, category_id "
                    "from money.money_v1_entry"
                )
            )
        ).all()
    )
    if keeps:
        rows = await common.entries_for_keeper(connection, conf.space_id, user, rows, cats)
    for e in rows:
        cat = cats.get(str(e.category_id))
        if cat is None:
            continue
        fid = f"entry:{e.id}"
        facts.append(
            Fact(
                fid,
                OTHER,
                e.on_date,
                -Decimal(str(e.amount)),
                e.description,
                "manual",
                by_other=e.payer == "other",
            )
        )
        labels.append(
            Label(
                fid,
                (
                    Imputation(
                        fid,
                        -Decimal(str(e.amount)),
                        cat.nature,
                        cat.ownership,
                        cat.id,
                        payer=(e.payer if cat.ownership == "shared" else None),
                        basis="manual",
                    ),
                ),
            )
        )
        entries[fid] = {"id": str(e.id), "payer": e.payer, "by": getattr(e, "by", None)}
        loaded.merchant_of[fid] = e.description

    label_rows = {
        r.fact_id: r.spec
        for r in (
            await connection.execute(text("select fact_id, spec from money.money_v1_label"))
        ).all()
    }
    labels += [label_of(fid, spec, cats) for fid, spec in label_rows.items()]
    rule_rows = [
        dict(r._mapping)
        for r in (
            await connection.execute(
                text(
                    "select id, position, spec, origin from money.money_v1_rule "
                    "order by position, created_at"
                )
            )
        ).all()
    ]

    typed = (
        await connection.execute(
            text("select account, on_date, symbol, name, value from money.money_v1_holding")
        )
    ).all()
    typed_shots = {(r.account, r.on_date) for r in typed}
    holdings = [h for h in loaded.holdings if (h.account, h.on) not in typed_shots] + [
        Holding(r.account, r.on_date, r.symbol, Decimal(str(r.value)), name=r.name) for r in typed
    ]
    funds = {
        r.symbol: {"asset": r.asset, "regions": r.regions}
        for r in (
            await connection.execute(text("select symbol, asset, regions from money.money_v1_fund"))
        ).all()
    }

    interp = Interpreter(
        rules=[rule_of(r["spec"]) for r in rule_rows],
        labels=labels,
        window_days=conf.window_days,
        holders=conf.holders,
        merchant_of=loaded.merchant_of,
    )
    book = interp.run(
        Book(
            accs,
            cats,
            facts,
            loaded.balances,
            holdings=holdings,
            prices=loaded.prices,
        )
    )

    from money.ledger import statuses

    incomes = [
        Income(r.person, r.from_on, r.to_on, Decimal(str(r.salary)), Decimal(str(r.extra)))
        for r in (
            await connection.execute(
                text("select person, from_on, to_on, salary, extra from money.money_v1_income")
            )
        ).all()
    ]
    history = [
        HistoryRow(r.year, r.month, r.kind, Decimal(str(r.amount)), r.category, r.split, r.payer)
        for r in (
            await connection.execute(
                text(
                    "select year, month, kind, amount, category, split, payer "
                    "from money.money_v1_history"
                )
            )
        ).all()
    ]
    settled = {
        r.year: r.settled
        for r in (
            await connection.execute(text("select year, settled from money.money_v1_year"))
        ).all()
    }

    flows = [
        Flow(r.year, r.month, r.kind, Decimal(str(r.amount)), r.category, r.account, r.mine)
        for r in (
            await connection.execute(
                text(
                    "select year, month, kind, amount, category, account, mine "
                    "from money.money_v1_history_flow"
                )
            )
        ).all()
    ]
    valuations = [
        Valuation(r.account, r.on_date, Decimal(str(r.value)), r.source)
        for r in (
            await connection.execute(
                text("select account, on_date, value, source from money.money_v1_valuation")
            )
        ).all()
    ]

    result = Loaded(
        settings=conf,
        book=book,
        statuses=statuses(book),
        merchant_of=loaded.merchant_of,
        unmapped=loaded.unmapped,
        entries=entries,
        incomes=incomes,
        history=history,
        settled=settled,
        labels=label_rows,
        rules=rule_rows,
        flows=flows,
        valuations=valuations,
        source_accounts=loaded.sources,
        source_of=loaded.matched,
        funds=funds,
        typed_shots=typed_shots,
    )
    _CACHE[key] = result
    while len(_CACHE) > 16:
        _CACHE.popitem(last=False)
    return result


def ratio_of(lo: Loaded, year: int) -> Decimal:
    return ratio(lo.incomes, year)


def dumps(value) -> str:
    return json.dumps(value, default=str)
