from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from money import catalog, history
from money.book import Loaded, ratio_of
from money.model import OTHER, Account
from money.shared import from_history
from money.value import Value, value_at

ZERO = Decimal(0)
HALF = Decimal("0.5")
INVESTED = ("investment", "real_estate")
MIN_CYCLE_DAYS = 20
PAYROLL_FROM_DAY = 25


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def shift_months(day: date, count: int) -> date:
    index = day.year * 12 + day.month - 1 + count
    y, m = divmod(index, 12)
    return date(y, m + 1, min(day.day, calendar.monthrange(y, m + 1)[1]))


def previous_period(start: date, end: date) -> tuple[date, date]:
    if start.day == 1 and end == month_end(end.year, end.month):
        count = len(months_between(start, end))
        first = shift_months(start, -count)
        last = shift_months(start, -1)
        return first, month_end(last.year, last.month)
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def series_months(start: date, end: date) -> tuple[list[tuple[int, int]], bool]:
    months = months_between(start, end)
    if len(months) >= 3:
        return months, False
    first = shift_months(date(end.year, end.month, 1), -11)
    return months_between(first, end), True


def before_cutoff(lo: Loaded, year: int, month: int) -> bool:
    cutoff = lo.settings.cutoff
    return cutoff is not None and date(year, month, 1) < cutoff


def group_of(account: Account) -> str:
    return catalog.account_types().get(account.type, {}).get("group") or account.type


def part(account: Account, whole: bool) -> Decimal:
    return Decimal(1) if whole else account.ownership


def valued(lo: Loaded, account: Account, on: date) -> Value:
    memo = lo.__dict__.setdefault("_values", {})
    key = (account.id, on)
    if key not in memo:
        memo[key] = value_at(lo.book, account, on, lo.valuations)
    return memo[key]


def share_of(lo: Loaded, split: str | None, year: int) -> Decimal:
    return HALF if split == "fifty_fifty" else ratio_of(lo, year)


@dataclass(frozen=True)
class Contribution:
    on: date
    account: str
    amount: Decimal
    mine: bool
    equity: bool = False
    """Pagado a un inmueble como gasto común (`equity_in`): ya está en el gasto del periodo."""


def equity_links(lo: Loaded) -> dict[str, str]:
    memo = lo.__dict__.get("_equity_links")
    if memo is not None:
        return memo
    seen: dict[str, Counter] = defaultdict(Counter)
    for imp in lo.book.imputations:
        if imp.equity_in and imp.equity_in in lo.book.accounts:
            seen[imp.category][imp.equity_in] += 1
    out = {cat: count.most_common(1)[0][0] for cat, count in seen.items()}
    lo.__dict__["_equity_links"] = out
    return out


def equity_of(lo: Loaded, imp) -> str | None:
    if imp.nature != "expense":
        return None
    if imp.equity_in and imp.equity_in in lo.book.accounts:
        return imp.equity_in
    return equity_links(lo).get(imp.category)


def contributions(lo: Loaded) -> list[Contribution]:
    memo = lo.__dict__.get("_contributions")
    if memo is not None:
        return memo
    b = lo.book
    cutoff = lo.settings.cutoff
    out: list[Contribution] = [
        Contribution(date(f.year, f.month, 15), f.account, f.amount, f.mine)
        for f in lo.flows
        if f.kind == "contribution" and f.account and before_cutoff(lo, f.year, f.month)
    ]

    def counts(on: date) -> bool:
        return cutoff is None or on >= cutoff

    for t in b.transfers:
        inn = b.fact(t.in_fact)
        out_fact = b.fact(t.out_fact) if t.out_fact else None
        to = b.accounts.get(inn.account)
        src = b.accounts.get(out_fact.account) if out_fact else None
        if src is not None and to is not None and src.id == to.id:
            continue
        on = out_fact.on if out_fact else inn.on
        if not counts(on):
            continue
        if to is not None and to.asset_class in INVESTED:
            if src is None:
                out.append(Contribution(on, to.id, inn.amount, False))
            elif src.shared_space:
                mine = inn.amount * src.ownership
                out.append(Contribution(on, to.id, mine, True))
                out.append(Contribution(on, to.id, inn.amount - mine, False))
            else:
                out.append(Contribution(on, to.id, inn.amount, True))
        if src is not None and src.asset_class in INVESTED and out_fact is not None:
            out.append(Contribution(on, src.id, out_fact.amount, True))
    for imp in b.imputations:
        home = equity_of(lo, imp)
        if home is None:
            continue
        f = b.fact(imp.fact)
        if not counts(f.on):
            continue
        paid = -imp.amount
        if imp.ownership == "shared":
            mine = paid * share_of(lo, b.categories[imp.category].split, f.on.year)
            out.append(Contribution(f.on, home, mine, True, True))
            out.append(Contribution(f.on, home, paid - mine, False, True))
        else:
            out.append(Contribution(f.on, home, paid, True, True))
    out.sort(key=lambda c: c.on)
    lo.__dict__["_contributions"] = out
    return out


def capital(lo: Loaded, account: str, on: date, whole: bool) -> Decimal:
    return sum(
        (
            c.amount
            for c in contributions(lo)
            if c.account == account and c.on <= on and (whole or c.mine)
        ),
        ZERO,
    )


def has_capital(lo: Loaded, account: str) -> bool:
    return any(c.account == account for c in contributions(lo))


def xirr(flows: list[tuple[date, float]]) -> float | None:
    flows = [(d, a) for d, a in flows if a]
    if not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    first = min(d for d, _ in flows)
    if (max(d for d, _ in flows) - first).days < 30:
        return None

    def npv(rate: float) -> float:
        return sum(a / (1 + rate) ** ((d - first).days / 365) for d, a in flows)

    low, high = -0.99, 10.0
    f_low, f_high = npv(low), npv(high)
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            break
        if f_low * f_mid < 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


def dietz(
    start_value: Decimal,
    end_value: Decimal,
    moved: list[tuple[date, Decimal]],
    start: date,
    end: date,
) -> Decimal | None:
    days = (end - start).days + 1
    if days <= 0:
        return None
    net = sum((a for _, a in moved), ZERO)
    weighted = sum((a * Decimal((end - d).days + 1) / Decimal(days) for d, a in moved), ZERO)
    base = start_value + weighted
    if base <= 0:
        return None
    return (end_value - start_value - net) / base


def accounts_for(
    lo: Loaded, home: bool, groups: Collection[str] = (), only: Collection[str] = ()
) -> list[Account]:
    return [
        a
        for a in lo.book.accounts.values()
        if (home or a.asset_class != "real_estate")
        and (not groups or group_of(a) in groups)
        and (not only or a.id in only)
    ]


def contributed(lo: Loaded, account: Account, on: date, whole: bool) -> Decimal:
    v = valued(lo, account, on).amount * part(account, whole)
    if account.asset_class in INVESTED and has_capital(lo, account.id):
        return capital(lo, account.id, on, whole)
    return v


def worth(
    lo: Loaded,
    start: date,
    end: date,
    home: bool,
    whole: bool,
    today: date,
    groups: Collection[str] = (),
    only: Collection[str] = (),
) -> dict:
    accounts = accounts_for(lo, home, groups, only)
    months, widened = series_months(start, end)
    last = min(end, today)
    points = []
    groups: list[str] = []
    for a in accounts:
        g = group_of(a)
        if g not in groups:
            groups.append(g)
    for y, m in months:
        on = min(month_end(y, m), last)
        if on < date(y, m, 1):
            break
        by_group: dict[str, Decimal] = defaultdict(lambda: ZERO)
        total = put = ZERO
        known = False
        for a in accounts:
            v = valued(lo, a, on)
            if not v.known:
                continue
            known = True
            amount = v.amount * part(a, whole)
            by_group[group_of(a)] += amount
            total += amount
            put += contributed(lo, a, on, whole)
        if not known:
            continue
        points.append(
            {
                "on": on,
                "label": f"{y}-{m:02d}",
                "total": total,
                "contributed": put,
                "by_group": {g: by_group.get(g, ZERO) for g in groups},
            }
        )

    before = start - timedelta(days=1)
    rows = []
    total_now = total_then = ZERO
    for a in accounts:
        now, then = valued(lo, a, last), valued(lo, a, before)
        if not now.known and not then.known:
            continue
        value = now.amount * part(a, whole) if now.known else ZERO
        previous = then.amount * part(a, whole) if then.known else None
        total_now += value
        total_then += previous or ZERO
        rows.append(
            {
                "key": a.id,
                "name": a.name,
                "institution": a.institution,
                "group": group_of(a),
                "value": value,
                "previous": previous,
                "since": now.since,
                "estimated": now.estimated,
                "carried": not now.estimated
                and bool(
                    now.since and (last - now.since).days > 7 and a.asset_class != "real_estate"
                ),
                "ownership": a.ownership,
            }
        )
    rows.sort(key=lambda r: -r["value"])
    return {
        "on": last,
        "before": before,
        "widened": widened,
        "groups": [g for g in groups if any(p["by_group"].get(g) for p in points)],
        "points": points,
        "rows": rows,
        "total": total_now,
        "previous": total_then if any(r["previous"] is not None for r in rows) else None,
        "contributed": points[-1]["contributed"] if points else None,
    }


def investments(
    lo: Loaded,
    start: date,
    end: date,
    home: bool,
    whole: bool,
    today: date,
    groups: Collection[str] = (),
    only: Collection[str] = (),
) -> dict:
    last = min(end, today)
    before = start - timedelta(days=1)
    months, widened = series_months(start, end)
    products = [
        a
        for a in accounts_for(lo, home, groups, only)
        if a.asset_class in INVESTED and (has_capital(lo, a.id) or valued(lo, a, last).known)
    ]
    all_flows: list[tuple[date, float]] = []
    period_flows: list[tuple[date, Decimal]] = []
    rows = []
    totals = defaultdict(lambda: ZERO)
    contributions_by_month: dict[str, dict[str, Decimal]] = {}
    for a in products:
        own = [c for c in contributions(lo) if c.account == a.id and (whole or c.mine)]
        now = valued(lo, a, last)
        then = valued(lo, a, before)
        value = now.amount * part(a, whole) if now.known else ZERO
        value_before = then.amount * part(a, whole) if then.known else ZERO
        cap = sum((c.amount for c in own if c.on <= last), ZERO)
        cap_other = sum(
            (
                c.amount
                for c in contributions(lo)
                if c.account == a.id and not c.mine and c.on <= last
            ),
            ZERO,
        )
        moved = [(c.on, c.amount) for c in own if start <= c.on <= last]
        net_in = sum((m for _, m in moved), ZERO)
        gain = value - cap
        flows = [(c.on, -float(c.amount)) for c in own if c.on <= last] + [(last, float(value))]
        rate = xirr(flows)
        all_flows += flows[:-1]
        period_flows += moved
        for d, amount in moved:
            label = f"{d.year}-{d.month:02d}"
            contributions_by_month.setdefault(a.id, {})
            contributions_by_month[a.id][label] = (
                contributions_by_month[a.id].get(label, ZERO) + amount
            )
        series = []
        for y, m in months:
            on = min(month_end(y, m), last)
            if on < date(y, m, 1):
                break
            v = valued(lo, a, on)
            series.append(
                {
                    "label": f"{y}-{m:02d}",
                    "value": v.amount * part(a, whole) if v.known else None,
                    "capital": sum((c.amount for c in own if c.on <= on), ZERO),
                }
            )
        rows.append(
            {
                "key": a.id,
                "name": a.name,
                "institution": a.institution,
                "group": group_of(a),
                "value": value,
                "value_before": value_before,
                "capital": cap,
                "capital_other": cap_other if not whole and cap_other else None,
                "gain": gain,
                "simple": gain / cap if cap > 0 else None,
                "xirr": rate,
                "contributed_in_period": net_in,
                "period_gain": value - value_before - net_in,
                "period_return": dietz(value_before, value, moved, start, last),
                "since": now.since,
                "estimated": now.estimated,
                "carried": not now.estimated and bool(now.since and (last - now.since).days > 7),
                "first": own[0].on if own else None,
                "series": series,
            }
        )
        totals["value"] += value
        totals["value_before"] += value_before
        totals["capital"] += cap
        totals["contributed_in_period"] += net_in
    totals["gain"] = totals["value"] - totals["capital"]
    rows.sort(key=lambda r: -r["value"])
    labels = [f"{y}-{m:02d}" for y, m in months_between(start, last)] if start <= last else []
    return {
        "on": last,
        "widened": widened,
        "rows": rows,
        "total": {
            **totals,
            "simple": totals["gain"] / totals["capital"] if totals["capital"] > 0 else None,
            "xirr": xirr(all_flows + [(last, float(totals["value"]))]),
            "period_gain": totals["value"]
            - totals["value_before"]
            - totals["contributed_in_period"],
            "period_return": dietz(
                totals["value_before"], totals["value"], period_flows, start, last
            ),
        },
        "contributions": {
            "labels": labels,
            "series": [
                {
                    "key": a,
                    "name": lo.book.accounts[a].name,
                    "values": [by.get(label, ZERO) for label in labels],
                }
                for a, by in contributions_by_month.items()
            ],
        },
    }


@dataclass
class Flows:
    income: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    expense: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    shared: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    shared_mine: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    contributions: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    equity: dict[tuple[str, str], Decimal] = field(
        default_factory=lambda: defaultdict(lambda: ZERO)
    )
    """(categoría común, inmueble) → lo tuyo pagado a él."""
    equity_whole: dict[tuple[str, str], Decimal] = field(
        default_factory=lambda: defaultdict(lambda: ZERO)
    )
    months_history: int = 0
    days_book: int = 0


def flows(lo: Loaded, start: date, end: date) -> Flows:
    b = lo.book
    out = Flows()
    cutoff = lo.settings.cutoff
    homes = {
        account: b.categories[cat].name
        for cat, account in equity_links(lo).items()
        if b.categories[cat].ownership == "shared"
    }
    for y, m in months_between(start, end):
        if not before_cutoff(lo, y, m) or date(y, m, 1) < start:
            continue
        out.months_history += 1
        hm = history.month(lo.flows, y, m)
        for name, amount in hm.income.items():
            out.income[name] += amount
        for name, amount in hm.expense.items():
            out.expense[name] += amount
        sh = from_history(lo.history, y, m)
        mine_of: dict[str, Decimal] = {}
        for name, amount in sh.by_category.items():
            mine_of[name] = amount * share_of(lo, sh.split_of.get(name), y)
            out.shared[name] += amount
            out.shared_mine[name] += mine_of[name]
        for account, amount in hm.contributions.items():
            name = homes.get(account)
            moved = min(amount, mine_of.get(name, ZERO)) if name else ZERO
            whole = min(amount + hm.others.get(account, ZERO), sh.by_category.get(name, ZERO))
            if moved > 0:
                out.equity[(name, account)] += moved
                out.equity_whole[(name, account)] += max(whole, moved)
            out.contributions[account] += amount - moved

    first = max(start, cutoff) if cutoff else start
    if first > end:
        return out
    out.days_book = (end - first).days + 1
    for imp in b.imputations:
        f = b.fact(imp.fact)
        if not first <= f.on <= end:
            continue
        cat = b.categories[imp.category]
        if imp.nature == "income":
            out.income[cat.name] += imp.amount
        elif imp.ownership == "individual":
            out.expense[cat.name] -= imp.amount
        else:
            spent = -imp.amount
            mine = spent * share_of(lo, cat.split, f.on.year)
            out.shared[cat.name] += spent
            out.shared_mine[cat.name] += mine
            home = equity_of(lo, imp)
            if home is not None:
                out.equity[(cat.name, home)] += mine
                out.equity_whole[(cat.name, home)] += spent
    for c in contributions(lo):
        if c.mine and not c.equity and first <= c.on <= end:
            out.contributions[c.account] += c.amount
    return out


def category_flags(lo: Loaded) -> dict[tuple[str, str], tuple[bool, bool]]:
    return {
        (c.ownership, c.name): (c.not_living, c.not_basic)
        for c in lo.book.categories.values()
        if c.nature == "expense"
    }


def spent_by_category(fl: Flows, scope: str, whole: bool) -> dict[tuple[str, str], Decimal]:
    out: dict[tuple[str, str], Decimal] = {}
    if scope in ("all", "individual"):
        for name, amount in fl.expense.items():
            if amount:
                out[("individual", name)] = amount
    if scope in ("all", "shared"):
        for name, amount in (fl.shared if whole else fl.shared_mine).items():
            if amount:
                out[("shared", name)] = amount
    return out


def spending(
    lo: Loaded, start: date, end: date, scope: str, whole: bool, kind: str, today: date
) -> dict:
    flags = category_flags(lo)

    def keep(key: tuple[str, str]) -> bool:
        not_living, not_basic = flags.get(key, (False, False))
        if kind == "basic":
            return not not_living and not not_basic
        if kind == "other":
            return not_living or not_basic
        return True

    def period(a: date, z: date) -> dict[tuple[str, str], Decimal]:
        return {
            k: v for k, v in spent_by_category(flows(lo, a, z), scope, whole).items() if keep(k)
        }

    last = min(end, today)
    now = period(start, last)
    p_start, p_end = previous_period(start, end)
    ongoing = end > today
    if ongoing:
        p_end = min(p_end, p_start + (last - start))
    then = period(p_start, p_end)
    months_count = max(1, len(months_between(start, last)))
    closed_last = min(last, date(today.year, today.month, 1) - timedelta(days=1))
    closed_count = len(months_between(start, closed_last)) if closed_last >= start else 0
    closed = period(start, closed_last) if closed_count else {}
    total = sum(now.values(), ZERO)
    total_then = sum(then.values(), ZERO)
    groups = {"basic": ZERO, "not_basic": ZERO, "not_living": ZERO}
    for key, amount in now.items():
        not_living, not_basic = flags.get(key, (False, False))
        groups["not_living" if not_living else "not_basic" if not_basic else "basic"] += amount
    rows = [
        {
            "key": f"{own}:{name}",
            "name": name,
            "ownership": own,
            "total": amount,
            "previous": then.get((own, name), ZERO),
            "average": closed.get((own, name), ZERO) / closed_count if closed_count else None,
            "share": amount / total if total else ZERO,
            "basic": not any(flags.get((own, name), (False, False))),
        }
        for (own, name), amount in now.items()
    ]
    for (own, name), amount in then.items():
        if (own, name) not in now:
            rows.append(
                {
                    "key": f"{own}:{name}",
                    "name": name,
                    "ownership": own,
                    "total": ZERO,
                    "previous": amount,
                    "average": ZERO if closed_count else None,
                    "share": ZERO,
                    "basic": not any(flags.get((own, name), (False, False))),
                }
            )
    rows.sort(key=lambda r: (-r["total"], -r["previous"]))

    months, widened = series_months(start, last)
    per_month = [period(date(y, m, 1), min(month_end(y, m), last)) for y, m in months]
    usual_end = min(month_end(last.year, last.month), closed_last)
    usual_months = months_between(
        shift_months(date(usual_end.year, usual_end.month, 1), -11), usual_end
    )
    usual_per = [pm for y, m in usual_months if (pm := period(date(y, m, 1), month_end(y, m)))]
    usual = {
        k: sum((pm.get(k, ZERO) for pm in usual_per), ZERO) / len(usual_per)
        for k in {k for pm in usual_per for k in pm}
    }
    for row in rows:
        row["usual"] = usual.get((row["ownership"], row["name"]), ZERO)
    keys = sorted(
        {k for pm in per_month for k in pm}, key=lambda k: -sum(pm.get(k, ZERO) for pm in per_month)
    )
    return {
        "on": last,
        "previous_period": {"from": p_start, "to": p_end},
        "ongoing": ongoing,
        "total": total,
        "previous": total_then,
        "months": months_count,
        "closed_months": closed_count,
        "monthly": sum(closed.values(), ZERO) / closed_count if closed_count else None,
        "usual_months": len(usual_per),
        "individual_months": {
            "now": individual_months(lo, start, last),
            "previous": individual_months(lo, p_start, p_end),
            "of": months_count,
        },
        "groups": groups,
        "rows": rows,
        "series": {
            "widened": widened,
            "labels": [f"{y}-{m:02d}" for y, m in months],
            "series": [
                {
                    "key": f"{own}:{name}",
                    "name": name if own == "individual" else f"{name} (común)",
                    "values": [pm.get((own, name), ZERO) for pm in per_month],
                }
                for own, name in keys
            ],
        },
    }


def individual_months(lo: Loaded, start: date, end: date) -> int:
    count = 0
    for y, m in months_between(start, end):
        if not before_cutoff(lo, y, m) or history.month(lo.flows, y, m).expense:
            count += 1
    return count


def category_detail(
    lo: Loaded, start: date, end: date, name: str, ownership: str, whole: bool
) -> dict:
    b = lo.book
    cutoff = lo.settings.cutoff
    first = max(start, cutoff) if cutoff else start
    rows = []
    merchants: dict[str, dict] = {}
    for imp in b.imputations:
        cat = b.categories[imp.category]
        if cat.name != name or cat.ownership != ownership or imp.nature != "expense":
            continue
        f = b.fact(imp.fact)
        if not first <= f.on <= end:
            continue
        spent = -imp.amount
        if ownership == "shared" and not whole:
            spent *= share_of(lo, cat.split, f.on.year)
        merchant = lo.merchant_of.get(f.id) or f.text
        acc = b.accounts.get(f.account)
        rows.append(
            {
                "id": f.id,
                "on": f.on,
                "merchant": merchant,
                "amount": spent,
                "account": acc.name
                if acc
                else ("Fuera de cuenta" if f.account == OTHER else f.account),
            }
        )
        m = merchants.setdefault(merchant, {"name": merchant, "total": ZERO, "count": 0})
        m["total"] += spent
        m["count"] += 1
    in_history = ZERO
    for y, m in months_between(start, end):
        if not before_cutoff(lo, y, m) or date(y, m, 1) < start:
            continue
        if ownership == "individual":
            in_history += history.month(lo.flows, y, m).expense.get(name, ZERO)
        else:
            sh = from_history(lo.history, y, m)
            amount = sh.by_category.get(name, ZERO)
            in_history += amount if whole else amount * share_of(lo, sh.split_of.get(name), y)
    rows.sort(key=lambda r: (r["on"], r["id"]), reverse=True)
    return {
        "name": name,
        "ownership": ownership,
        "history": in_history,
        "merchants": sorted(merchants.values(), key=lambda m: -m["total"]),
        "movements": rows,
    }


@dataclass(frozen=True)
class Segment:
    start: date
    end: date
    month: tuple[int, int]
    """El mes al que pertenece: el suyo, o en un ciclo el que paga su nómina (`paid_month`)."""
    kind: str
    open: bool = False


def payroll_category(lo: Loaded) -> str | None:
    sums: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for imp in lo.book.imputations:
        if imp.nature == "income" and imp.ownership == "individual":
            sums[imp.category] += imp.amount
    return max(sums, key=lambda k: sums[k]) if sums else None


def payroll_days(lo: Loaded) -> list[date]:
    cat = payroll_category(lo)
    if cat is None:
        return []
    paid = [
        (lo.book.fact(i.fact).on, i.amount)
        for i in lo.book.imputations
        if i.category == cat and i.amount > 0
    ]
    if not paid:
        return []
    usual = median(a for _, a in paid)
    out: list[date] = []
    for on, amount in sorted(paid):
        if amount < usual / 2:
            continue
        if out and (on - out[-1]).days < MIN_CYCLE_DAYS:
            continue
        out.append(on)
    return out


def previous_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def payroll_late(lo: Loaded) -> dict[tuple[int, int], dict[str, Decimal]]:
    cat = payroll_category(lo)
    if cat is None:
        return {}
    b = lo.book
    late = {
        i.fact
        for i in b.imputations
        if i.category == cat and i.amount > 0 and b.fact(i.fact).on.day >= PAYROLL_FROM_DAY
    }
    out: dict[tuple[int, int], dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for i in b.imputations:
        if i.fact in late and i.nature == "income" and i.amount > 0:
            on = b.fact(i.fact).on
            out[(on.year, on.month)][b.categories[i.category].name] += i.amount
    return out


def payroll_moved(
    lo: Loaded, late: dict[tuple[int, int], dict[str, Decimal]], y: int, m: int
) -> dict[str, Decimal]:
    found = late.get((y, m), {})
    if not before_cutoff(lo, y, m):
        return dict(found)
    known = history.month(lo.flows, y, m).income
    return {name: min(amount, known.get(name, ZERO)) for name, amount in found.items()}


def paid_month(start: date) -> tuple[int, int]:
    if start.day >= PAYROLL_FROM_DAY:
        return (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    return (start.year, start.month)


def majority_month(start: date, end: date) -> tuple[int, int]:
    days: dict[tuple[int, int], int] = defaultdict(int)
    d = start
    while d <= end:
        days[(d.year, d.month)] += 1
        d += timedelta(days=1)
    return max(days, key=lambda k: (days[k], k))


def segments(lo: Loaded, cycle: bool, today: date) -> list[Segment]:
    cutoff = lo.settings.cutoff
    out: list[Segment] = []
    firsts = [f.on for f in lo.book.facts] + [date(f.year, f.month, 1) for f in lo.flows]
    if not firsts:
        return []
    begin = min(firsts)
    for y, m in months_between(begin, today):
        start, end = date(y, m, 1), month_end(y, m)
        if cutoff and start < cutoff:
            out.append(Segment(start, end, (y, m), "month"))
        elif not cycle:
            out.append(Segment(start, min(end, today), (y, m), "month", end > today))
    if not cycle:
        return out
    pays = [d for d in payroll_days(lo) if not cutoff or d >= cutoff]
    first = cutoff or begin
    if not pays:
        return out + [
            Segment(
                date(y, m, 1), min(month_end(y, m), today), (y, m), "month", month_end(y, m) > today
            )
            for y, m in months_between(first, today)
        ]
    starts = ([first] if pays[0] > first else []) + pays
    for index, start in enumerate(starts):
        if start > today:
            break
        nxt = starts[index + 1] if index + 1 < len(starts) else None
        end = (nxt - timedelta(days=1)) if nxt else None
        is_open = end is None or end >= today
        shown_end = end or shift_months(start, 1) - timedelta(days=1)
        out.append(
            Segment(
                start,
                min(shown_end, today) if is_open else shown_end,
                paid_month(start),
                "cycle",
                is_open,
            )
        )
    return out


UNLOGGED = "Sin etiquetar"
"""Lo que no se apuntó en los meses del histórico sin gasto individual: lo que quedó en ellos, como
gasto, o lo que faltó, como entrada."""


def unlogged_left(fl: Flows) -> Decimal:
    return (
        sum((v for v in fl.income.values() if v > 0), ZERO)
        - sum((v for v in fl.expense.values() if v > 0), ZERO)
        - sum(fl.shared_mine.values(), ZERO)
        - sum(fl.contributions.values(), ZERO)
    )


def flow(
    lo: Loaded,
    start: date,
    end: date,
    cycle: bool,
    whole: bool,
    today: date,
    compare: bool = True,
    rent_invested: bool = True,
) -> dict:
    wanted = set(months_between(start, end))
    parts = [s for s in segments(lo, cycle, today) if s.month in wanted]
    late = payroll_late(lo) if cycle else {}
    cutoff = lo.settings.cutoff
    moved_in, moved_out = ZERO, ZERO
    total = Flows()
    unlabelled = ZERO
    for s in parts:
        fl = flows(lo, s.start, s.end)
        if cycle and (s.kind == "month" or s.start == cutoff):
            for name, amount in payroll_moved(lo, late, *previous_month(*s.month)).items():
                fl.income[name] += amount
                moved_in += amount
        if cycle and s.kind == "month":
            for name, amount in payroll_moved(lo, late, *s.month).items():
                fl.income[name] -= amount
                moved_out += amount
        if before_cutoff(lo, *s.month) and not history.month(lo.flows, *s.month).expense:
            unlabelled += unlogged_left(fl)
        for name in (
            "income",
            "expense",
            "shared",
            "shared_mine",
            "contributions",
            "equity",
            "equity_whole",
        ):
            mine, theirs = getattr(total, name), getattr(fl, name)
            for k, v in theirs.items():
                mine[k] += v
    if unlabelled > 0:
        total.expense[UNLOGGED] += unlabelled
    elif unlabelled < 0:
        total.income[UNLOGGED] -= unlabelled
    me, other = lo.settings.me_name, lo.settings.other_name
    accounts = lo.book.accounts
    common = dict(total.shared if whole else total.shared_mine)
    invest: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for account, amount in total.contributions.items():
        if amount:
            invest[account] += amount
    for (cat, account), amount in (
        (total.equity_whole if whole else total.equity).items() if rent_invested else ()
    ):
        moved = amount
        common[cat] = common.get(cat, ZERO) - moved
        invest[account] += moved
    income = {k: v for k, v in total.income.items() if v > 0}
    member = (
        (sum(total.shared.values(), ZERO) - sum(total.shared_mine.values(), ZERO))
        if whole
        else ZERO
    )
    spent = {k: v for k, v in total.expense.items() if v > 0}
    common = {k: v for k, v in common.items() if v > 0}
    invest = {k: v for k, v in invest.items() if v}
    inflow = sum(income.values(), ZERO) + max(member, ZERO)
    outflow = (
        sum(spent.values(), ZERO)
        + sum(common.values(), ZERO)
        + sum((v for v in invest.values() if v > 0), ZERO)
    )
    withdrawn = -sum((v for v in invest.values() if v < 0), ZERO)
    inflow += withdrawn
    left = inflow - outflow

    nodes = [{"id": "you", "name": me, "column": 1, "kind": "you"}]
    links = []
    for name, amount in sorted(income.items(), key=lambda kv: -kv[1]):
        nodes.append({"id": f"in:{name}", "name": name, "column": 0, "kind": "income"})
        links.append({"source": f"in:{name}", "target": "you", "value": amount})
    if member > 0:
        nodes.append(
            {"id": "member", "name": f"{other}, a lo común", "column": 0, "kind": "member"}
        )
        links.append({"source": "member", "target": "you", "value": member})
    if withdrawn > 0:
        nodes.append(
            {"id": "withdrawn", "name": "Sacado de inversiones", "column": 0, "kind": "income"}
        )
        links.append({"source": "withdrawn", "target": "you", "value": withdrawn})
    if left < 0:
        nodes.append({"id": "deficit", "name": "De tus ahorros", "column": 0, "kind": "deficit"})
        links.append({"source": "deficit", "target": "you", "value": -left})

    def branch(node: str, name: str, kind: str, items: dict[str, Decimal], label) -> None:
        total_branch = sum(items.values(), ZERO)
        if total_branch <= 0:
            return
        nodes.append({"id": node, "name": name, "column": 2, "kind": kind})
        links.append({"source": "you", "target": node, "value": total_branch})
        for key, amount in sorted(items.items(), key=lambda kv: -kv[1]):
            leaf = f"{node}:{key}"
            nodes.append({"id": leaf, "name": label(key), "column": 3, "kind": kind})
            links.append({"source": node, "target": leaf, "value": amount})

    branch("spent", "Individual", "expense", spent, lambda k: k)
    branch("common", "Común", "common", common, lambda k: k)
    branch(
        "invest",
        "Inversión",
        "saving",
        {k: v for k, v in invest.items() if v > 0},
        lambda k: accounts[k].name if k in accounts else k,
    )
    if left > 0:
        nodes.append({"id": "left", "name": "Queda", "column": 2, "kind": "account"})
        links.append({"source": "you", "target": "left", "value": left})

    return {
        "segments": [{"from": s.start, "to": s.end, "kind": s.kind, "open": s.open} for s in parts],
        "nodes": nodes,
        "links": [link for link in links if link["value"] > 0],
        "totals": {
            "income": sum(income.values(), ZERO),
            "member": max(member, ZERO),
            "spent": sum(spent.values(), ZERO),
            "common": sum(common.values(), ZERO),
            "invested": sum((v for v in invest.values() if v > 0), ZERO) - withdrawn,
            "left": left,
            "rate": (left + sum((v for v in invest.values()), ZERO)) / sum(income.values(), ZERO)
            if sum(income.values(), ZERO) > 0
            else None,
        },
        "payroll": lo.book.categories[c].name if (c := payroll_category(lo)) else None,
        "payroll_moved": {"in": moved_in, "out": moved_out} if cycle else None,
        "unlogged": sum(
            1
            for y, m in wanted
            if before_cutoff(lo, y, m) and not history.month(lo.flows, y, m).expense
        ),
        "previous": (
            flow(
                lo,
                *previous_period(start, end),
                cycle,
                whole,
                today,
                compare=False,
                rent_invested=rent_invested,
            )["totals"]
            if compare
            else None
        ),
    }


OUTSIDE_NOT_INCOME = {"in:return", "in:refund", "in:refund:shared", "in:pending"}
"""Lo que entra de fuera sin ser un ingreso: no hace de una cuenta la puerta del dinero."""


def circuit(lo: Loaded, start: date, end: date, today: date) -> dict:
    b = lo.book
    other = lo.settings.other_name
    links: dict[tuple[str, str], dict] = {}
    nodes: dict[str, dict] = {}

    def node(key: str, name: str, kind: str, group: str, group_name: str) -> None:
        nodes.setdefault(
            key,
            {
                "id": key,
                "name": name,
                "kind": kind,
                "group": group,
                "group_name": group_name,
                "inflow": ZERO,
                "outflow": ZERO,
            },
        )

    def account_node(key: str) -> str:
        a = b.accounts[key]
        node(f"acc:{key}", a.name, "account", a.institution, a.institution)
        return f"acc:{key}"

    def add(src: str, dst: str, amount: Decimal, item: dict) -> None:
        if amount <= 0 or src == dst:
            return
        link = links.setdefault(
            (src, dst), {"source": src, "target": dst, "value": ZERO, "items": []}
        )
        link["value"] += amount
        link["items"].append(item)

    def item(f, amount: Decimal) -> dict:
        return {
            "id": f.id,
            "on": f.on,
            "amount": amount,
            "text": lo.merchant_of.get(f.id) or f.text,
        }

    first_fact = min((f.on for f in b.facts if f.source == "api"), default=None)
    moved = b.transferred()
    for t in b.transfers:
        inn = b.fact(t.in_fact)
        out = b.fact(t.out_fact) if t.out_fact else None
        on = out.on if out else inn.on
        if not start <= on <= end or inn.account not in b.accounts:
            continue
        if out is None:
            node("member", other, "income", "member", other)
            add("member", account_node(inn.account), inn.amount, item(inn, inn.amount))
        elif out.account in b.accounts:
            add(
                account_node(out.account),
                account_node(inn.account),
                inn.amount,
                item(out, inn.amount),
            )

    for imp in b.imputations:
        f = b.fact(imp.fact)
        if not start <= f.on <= end or f.id in moved:
            continue
        cat = b.categories[imp.category]
        if f.account not in b.accounts:
            if f.account != OTHER or imp.nature != "expense" or imp.amount >= 0:
                continue
            if f.by_other:
                node("member", other, "income", "member", other)
            else:
                node("cash", "Fuera de cuenta", "income", "income", "Ingresos")
            key = "out:shared" if imp.ownership == "shared" else "out:individual"
            node(
                key,
                "Gasto común" if imp.ownership == "shared" else "Gasto individual",
                "expense",
                "expense",
                "Gasto",
            )
            add("member" if f.by_other else "cash", key, -imp.amount, item(f, -imp.amount))
            continue
        acc = account_node(f.account)
        if imp.nature == "income":
            key = f"in:{cat.name}"
            node(key, cat.name, "income", "income", "Ingresos")
            add(key, acc, imp.amount, item(f, imp.amount))
        else:
            key = "out:shared" if imp.ownership == "shared" else "out:individual"
            node(
                key,
                "Gasto común" if imp.ownership == "shared" else "Gasto individual",
                "expense",
                "expense",
                "Gasto",
            )
            if imp.amount < 0:
                add(acc, key, -imp.amount, item(f, -imp.amount))
            else:
                refund = "in:refund:shared" if imp.ownership == "shared" else "in:refund"
                node(
                    refund,
                    "Devoluciones de lo común" if imp.ownership == "shared" else "Devoluciones",
                    "income",
                    "income",
                    "Ingresos",
                )
                add(refund, acc, imp.amount, item(f, imp.amount))

    for f in b.facts:
        if not start <= f.on <= end or f.account not in b.accounts or f.source == "inferred":
            continue
        status = lo.statuses.get(f.id)
        acc = None
        if f.id in b.returns:
            node("in:return", "Rentabilidad", "income", "income", "Ingresos")
            add("in:return", account_node(f.account), f.amount, item(f, f.amount))
        elif f.id in b.settlements:
            node("member", other, "income", "member", other)
            acc = account_node(f.account)
            if f.amount > 0:
                add("member", acc, f.amount, item(f, f.amount))
            else:
                node("settle", other, "elsewhere", "member", other)
                add(acc, "settle", -f.amount, item(f, -f.amount))
        elif status in ("pending", "ask"):
            imputed = sum((i.amount for i in b.imputations if i.fact == f.id), ZERO)
            rest = f.amount - imputed
            acc = account_node(f.account)
            if rest < 0:
                node("out:pending", "Sin etiquetar", "elsewhere", "pending", "Sin etiquetar")
                add(acc, "out:pending", -rest, item(f, -rest))
            elif rest > 0:
                node("in:pending", "Sin etiquetar", "elsewhere", "pending", "Sin etiquetar")
                add("in:pending", acc, rest, item(f, rest))

    for link in links.values():
        nodes[link["source"]]["outflow"] += link["value"]
        nodes[link["target"]]["inflow"] += link["value"]
        link["items"].sort(key=lambda i: i["on"], reverse=True)

    earned = {
        link["target"]
        for link in links.values()
        if link["source"].startswith("in:")
        and link["source"] not in OUTSIDE_NOT_INCOME
        or link["source"] == "member"
    }
    for key, n in nodes.items():
        if not key.startswith("acc:"):
            n["column"] = 0 if n["kind"] == "income" or key == "in:pending" else 4
            continue
        a = b.accounts[key[4:]]
        n["column"] = 1 if key in earned and a.asset_class == "cash" else 2
    used = sorted({n["column"] for n in nodes.values()})
    for n in nodes.values():
        n["column"] = used.index(n["column"])

    last = min(end, today)
    before = start - timedelta(days=1)
    balances = {}
    for key in nodes:
        if not key.startswith("acc:"):
            continue
        a = b.accounts[key[4:]]
        v0, v1 = valued(lo, a, before), valued(lo, a, last)
        balances[key] = {
            "start": v0.amount if v0.known else None,
            "end": v1.amount if v1.known else None,
            "type": catalog.account_types().get(a.type, {}).get("label", a.type),
        }
    return {
        "since": first_fact,
        "nodes": list(nodes.values()),
        "links": sorted(links.values(), key=lambda link: -link["value"]),
        "balances": balances,
        "on": last,
        "before": before,
    }
