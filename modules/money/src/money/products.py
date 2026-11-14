from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from money import analysis, catalog
from money.book import Loaded, rule_of
from money.model import Account, Holding
from money.texts import t
from money.value import price_on, start_price

ZERO = Decimal(0)
HUNDRED = Decimal(100)

ASSETS = ("equity", "bond", "real_estate", "cash", "crypto", "other")
REGIONS = ("us", "europe", "japan", "pacific", "other_developed", "emerging")
UNKNOWN = "unknown"
CASH_REGION = "cash"
VALUE_HOW = ("balance", "computed", "snapshot", "manual")


def asset_name(key: str) -> str:
    return t(f"asset.{key}") if key in ASSETS or key == UNKNOWN else key


def region_name(key: str) -> str:
    return t(f"region.{key}") if key in REGIONS or key in (UNKNOWN, CASH_REGION) else key


def assets() -> dict[str, str]:
    return {key: asset_name(key) for key in ASSETS}


def regions() -> dict[str, str]:
    return {key: region_name(key) for key in REGIONS}


@dataclass(frozen=True)
class Kind:
    asset: str
    regions: dict[str, Decimal]
    source: str


def kind_of(lo: Loaded, account: Account, symbol: str) -> Kind:
    own = lo.funds.get(symbol)
    if own is not None:
        return Kind(own["asset"], _regions(own.get("regions")), "yours")
    known = catalog.funds().get(symbol)
    if known is not None:
        return Kind(known["asset"], _regions(known.get("regions")), "catalog")
    if account.type == "crypto":
        return Kind("crypto", {}, "product")
    return Kind("other", {}, UNKNOWN)


def _regions(raw: dict | None) -> dict[str, Decimal]:
    return {k: Decimal(str(v)) for k, v in (raw or {}).items() if Decimal(str(v)) > 0}


@dataclass
class Fund:
    symbol: str
    name: str
    value: Decimal
    shot_value: Decimal
    change: Decimal | None
    """How much its price moved since the snapshot, as a fraction; without a price, nothing."""
    kind: Kind


@dataclass
class Photo:
    on: date
    source: str
    """`yours` (typed by hand) or `source` (brought by its source)."""
    funds: list[Fund] = field(default_factory=list)


def last_shot(lo: Loaded, account: str, on: date) -> date | None:
    return max(
        (h.on for h in lo.book.holdings if h.account == account and h.on <= on), default=None
    )


def photo_of(lo: Loaded, account: Account, on: date, scale: Decimal = Decimal(1)) -> Photo | None:
    shot = last_shot(lo, account.id, on)
    if shot is None:
        return None
    held: list[Holding] = [h for h in lo.book.holdings if h.account == account.id and h.on == shot]
    grown: list[tuple[Holding, Decimal, Decimal | None]] = []
    for h in held:
        factor: Decimal | None = None
        series = lo.book.prices.get(h.symbol)
        if series:
            start, end = start_price(series, h, shot), price_on(series, on)
            if start is not None and end is not None and start[1] > 0:
                factor = end[1] / start[1]
        grown.append((h, h.value * (factor or Decimal(1)), factor))
    total = sum((g for _, g, _ in grown), ZERO)
    now = analysis.valued(lo, account, on)
    target = now.amount if now.known and now.amount > 0 else total
    ratio = target / total if total > 0 else Decimal(1)
    photo = Photo(shot, "yours" if (account.id, shot) in lo.typed_shots else "source")
    for h, g, factor in sorted(grown, key=lambda x: -x[1]):
        photo.funds.append(
            Fund(
                h.symbol,
                h.name or h.symbol,
                (g * ratio * scale).quantize(Decimal("0.01")),
                h.value,
                factor - 1 if factor is not None else None,
                kind_of(lo, account, h.symbol),
            )
        )
    return photo


def _add(bucket: dict[str, Decimal], key: str, value: Decimal) -> None:
    bucket[key] = bucket.get(key, ZERO) + value


def _rows(bucket: dict[str, Decimal], names: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"key": k, "name": names.get(k, k), "value": v}
        for k, v in sorted(bucket.items(), key=lambda kv: -kv[1])
        if v > 0
    ]


def fund_out(f: Fund) -> dict[str, Any]:
    return {
        "symbol": f.symbol,
        "name": f.name,
        "value": f.value,
        "change": f.change,
        "asset": f.kind.asset,
        "asset_name": asset_name(f.kind.asset),
        "regions": [
            {"key": k, "name": region_name(k), "weight": w}
            for k, w in sorted(f.kind.regions.items(), key=lambda kv: -kv[1])
        ],
        "classified": f.kind.source,
    }


def composition(
    lo: Loaded,
    start: date,
    end: date,
    home: bool,
    whole: bool,
    today: date,
    groups: Collection[str] = (),
    only: Collection[str] = (),
) -> dict[str, Any]:
    last = min(end, today)
    by_asset: dict[str, Decimal] = {}
    by_region: dict[str, Decimal] = {}
    by_product: dict[str, Decimal] = {}
    funds: dict[str, dict[str, Any]] = {}
    products = []
    unknown_asset = unknown_region = ZERO
    names = {}
    for a in analysis.accounts_for(lo, home, groups, only):
        if a.asset_class not in analysis.INVESTED:
            continue
        now = analysis.valued(lo, a, last)
        value = now.amount * analysis.part(a, whole) if now.known else ZERO
        if value <= 0:
            continue
        names[a.id] = a.name
        _add(by_product, a.id, value)
        photo = photo_of(lo, a, last, analysis.part(a, whole))
        if photo is None:
            asset = {"real_estate": "real_estate", "crypto": "crypto"}.get(
                a.asset_class if a.asset_class == "real_estate" else a.type, UNKNOWN
            )
            _add(by_asset, asset, value)
            _add(by_region, UNKNOWN, value)
            unknown_region += value
            if asset == UNKNOWN:
                unknown_asset += value
            key = f"product:{a.id}"
            funds[key] = {"key": key, "name": a.name, "value": value, "products": [a.name]}
            products.append({"key": a.id, "name": a.name, "value": value, "on": None, "funds": []})
            continue
        for f in photo.funds:
            asset = f.kind.asset if f.kind.source != UNKNOWN else UNKNOWN
            _add(by_asset, asset, f.value)
            if asset == UNKNOWN:
                unknown_asset += f.value
            if f.kind.asset == "cash":
                _add(by_region, CASH_REGION, f.value)
            elif f.kind.regions:
                weight = sum(f.kind.regions.values(), ZERO)
                for region, w in f.kind.regions.items():
                    _add(by_region, region, f.value * w / weight)
            else:
                _add(by_region, UNKNOWN, f.value)
                unknown_region += f.value
            entry = funds.setdefault(
                f.symbol, {"key": f.symbol, "name": f.name, "value": ZERO, "products": []}
            )
            entry["value"] += f.value
            if a.name not in entry["products"]:
                entry["products"].append(a.name)
        products.append(
            {
                "key": a.id,
                "name": a.name,
                "value": value,
                "on": photo.on,
                "typed": photo.source == "yours",
                "funds": [fund_out(f) for f in photo.funds],
            }
        )
    total = sum(by_product.values(), ZERO)
    asset_names = {**assets(), UNKNOWN: asset_name(UNKNOWN)}
    region_names = {
        **regions(),
        CASH_REGION: region_name(CASH_REGION),
        UNKNOWN: region_name(UNKNOWN),
    }
    return {
        "on": last,
        "total": total,
        "by_asset": _rows(by_asset, asset_names),
        "by_region": _rows(by_region, region_names),
        "by_fund": sorted((f for f in funds.values() if f["value"] > 0), key=lambda f: -f["value"]),
        "by_product": _rows(by_product, names),
        "unknown_asset": unknown_asset,
        "unknown_region": unknown_region,
        "products": sorted(products, key=lambda p: -p["value"]),
    }


def detail(lo: Loaded, account: Account, today: date) -> dict[str, Any]:
    types = catalog.account_types()
    typed = types.get(account.type, {})
    now = analysis.valued(lo, account, today)
    photo = photo_of(lo, account, today) if account.asset_class != "cash" else None
    source = next(
        (
            {"bank": s.bank, "name": s.name, "iban_tail": s.iban_tail}
            for s in lo.source_accounts
            if lo.source_of.get(s.key) == account.id
        ),
        None,
    )
    invested = account.asset_class in analysis.INVESTED
    rules = [r for r in describe_rules(lo) if account.id in r["accounts"]]
    valuations = sorted(
        (v for v in lo.valuations if v.account == account.id), key=lambda v: v.on, reverse=True
    )
    return {
        "key": account.id,
        "name": account.name,
        "institution": account.institution,
        "type": account.type,
        "type_label": typed.get("label", account.type),
        "group": analysis.group_of(account),
        "asset_class": account.asset_class,
        "traits": traits(account),
        "ownership": account.ownership,
        "shared": account.shared_space,
        "role": account.role,
        "movements": account.movements,
        "movements_how": t(f"movements_how.{account.movements}"),
        "source": source,
        "value_mode": account.value,
        "value_how": t(f"value_how.{account.value}")
        if account.value in VALUE_HOW
        else account.value,
        "value": now.amount if now.known else None,
        "value_since": now.since,
        "estimated": now.estimated,
        "contributed": analysis.capital(lo, account.id, today, True) if invested else None,
        "ibans": list(account.ibans),
        "rules": rules,
        "valuations": [{"on": v.on, "value": v.value, "source": v.source} for v in valuations[:6]],
        "photo": (
            {
                "on": photo.on,
                "typed": photo.source == "yours",
                "funds": [fund_out(f) for f in photo.funds],
            }
            if photo
            else None
        ),
    }


def traits(account: Account) -> list[str]:
    out = []
    if account.cash:
        out.append(t("trait.cash"))
    if not account.liquid:
        out.append(t("trait.not_liquid"))
    if account.counts_for_savings:
        out.append(t("trait.savings"))
    if account.asset_class == "receivable":
        out.append(t("trait.receivable"))
    if account.asset_class == "real_estate":
        out.append(t("trait.real_estate"))
    if account.spending:
        out.append(t("trait.spending"))
    return out


def describe_rules(lo: Loaded) -> list[dict[str, Any]]:
    explained = rule_hits(lo)
    out = []
    for r in lo.rules:
        spec = r["spec"]
        when = []
        if spec.get("merchant"):
            when.append(t("rule.merchant", value=spec["merchant"]))
        if spec.get("text"):
            when.append(t("rule.text", value=spec["text"]))
        if spec.get("counterparty"):
            when.append(t("rule.counterparty", value=spec["counterparty"]))
        if spec.get("counterparty_iban"):
            when.append(t("rule.iban", value=spec["counterparty_iban"]))
        if spec.get("bank_category"):
            when.append(t("rule.bank_category", value=spec["bank_category"]))
        if spec.get("account"):
            when.append(t("rule.in", value=_name(lo, spec["account"])))
        if spec.get("sign"):
            when.append(t("rule.in_sign") if spec["sign"] > 0 else t("rule.out_sign"))
        rule = rule_of(spec)
        accounts = [k for k in (rule.transfer_to, rule.account, rule.equity_in) if k]
        out.append(
            {
                "id": str(r["id"]),
                "origin": r.get("origin"),
                "when": ", ".join(when) or t("rule.everything"),
                "then": _then(lo, rule),
                "accounts": accounts,
                "movements": explained.get(str(r["id"]), 0),
            }
        )
    return out


def _name(lo: Loaded, key: str) -> str:
    a = lo.book.accounts.get(key)
    return a.name if a else key


def _then(lo: Loaded, rule) -> str:
    if rule.transfer_to:
        return t("rule.transfer", value=_name(lo, rule.transfer_to))
    if rule.is_return:
        return t("rule.return")
    if rule.ask:
        return t("rule.ask")
    if rule.from_other_member:
        return t("rule.other_member")
    if rule.parts:
        return t("rule.parts")
    if rule.category:
        cat = lo.book.categories.get(rule.category)
        return cat.name if cat else t("rule.gone")
    return t("rule.nothing")


def rule_hits(lo: Loaded) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for index in lo.book.ruled.values():
        if index < len(lo.rules):
            counts[str(lo.rules[index]["id"])] += 1
    return counts


def ruled_by(lo: Loaded, rule_id: str) -> list[str]:
    index = next((i for i, r in enumerate(lo.rules) if str(r["id"]) == rule_id), None)
    return [f for f, i in lo.book.ruled.items() if i == index]
