from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal

from money.model import OTHER, Book, Fact, Imputation, Transfer


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.upper().split())


def merchant_key(name: str) -> str:
    return " ".join(re.sub(r"[^A-Z ]+", " ", fold(name)).split())


@dataclass(frozen=True)
class Rule:
    merchant: str | None = None
    text: str | None = None
    account: str | None = None
    sign: int | None = None
    min_abs: Decimal | None = None
    max_abs: Decimal | None = None
    counterparty: str | None = None
    counterparty_iban: str | None = None
    bank_category: str | None = None
    transfer_to: str | None = None
    from_other_member: bool = False
    category: str | None = None
    equity_in: str | None = None
    parts: tuple[dict, ...] = ()
    ask: bool = False
    is_return: bool = False
    basis: str = "rule"

    def matches(self, fact: Fact, merchant: str) -> bool:
        if self.merchant and merchant_key(self.merchant) != merchant:
            return False
        if self.text and not re.search(
            self.text, f"{fact.text} // {fact.counterparty or ''}", re.IGNORECASE
        ):
            return False
        if self.counterparty and not re.search(
            self.counterparty, fact.counterparty or "", re.IGNORECASE
        ):
            return False
        if self.counterparty_iban and (fact.counterparty_iban or "").replace(" ", "").upper() != (
            self.counterparty_iban.replace(" ", "").upper()
        ):
            return False
        if self.bank_category and not re.search(
            self.bank_category, fact.bank_category or "", re.IGNORECASE
        ):
            return False
        if self.account and self.account != fact.account:
            return False
        if self.sign and (fact.amount > 0) != (self.sign > 0):
            return False
        if self.min_abs is not None and abs(fact.amount) < self.min_abs:
            return False
        return self.max_abs is None or abs(fact.amount) <= self.max_abs


@dataclass(frozen=True)
class Label:
    fact: str
    parts: tuple[Imputation, ...] = ()
    settlement: bool = False
    is_return: bool = False
    transfer_with: str | None = None


@dataclass
class Interpreter:
    rules: list[Rule] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    window_days: int = 4
    holders: tuple[str, ...] = ()
    merchant_of: dict[str, str] = field(default_factory=dict)
    """El comercio de cada hecho, ya limpio, si la fuente lo sabe sacar; si no, su texto."""

    def merchant(self, fact: Fact) -> str:
        return merchant_key(self.merchant_of.get(fact.id) or fact.counterparty or fact.text)

    def run(self, book: Book) -> Book:
        book.transfers, book.imputations = [], []
        book.returns, book.settlements, book.asking = set(), set(), set()
        book.ruled = {}
        known = {f.id for f in book.facts}
        labelled = {lb.fact for lb in self.labels if lb.fact in known}
        for lb in self.labels:
            if lb.fact not in known:
                continue
            if lb.settlement:
                book.settlements.add(lb.fact)
            elif lb.is_return:
                book.returns.add(lb.fact)
            book.imputations.extend(replace(p, fact=lb.fact, basis="manual") for p in lb.parts)

        self._labelled_transfers(book)
        self._external_contributions(book, labelled)
        self._match_transfers(book, labelled)
        self._by_iban(book, labelled)

        done = labelled | book.transferred()
        for fact in [f for f in book.facts if f.id not in done and f.source != "inferred"]:
            merchant = self.merchant(fact)
            index, rule = next(
                ((i, r) for i, r in enumerate(self.rules) if r.matches(fact, merchant)),
                (None, None),
            )
            if rule is None:
                continue
            book.ruled[fact.id] = index
            if rule.is_return:
                book.returns.add(fact.id)
            elif rule.ask:
                book.asking.add(fact.id)
            elif rule.transfer_to and rule.transfer_to in book.accounts:
                book.transfers.append(self._infer_leg(book, fact, rule.transfer_to))
            elif rule.from_other_member:
                book.transfers.append(Transfer(None, fact.id, basis="other_member"))
            elif rule.parts:
                book.imputations.extend(self._template(book, fact, rule))
            elif rule.category and rule.category in book.categories:
                book.imputations.append(replace(self._impute(book, fact, rule), basis=rule.basis))
        return book

    def _external_contributions(self, book: Book, skip: set[str]) -> None:
        for f in book.facts:
            account = book.accounts.get(f.account)
            if f.id in skip or not f.by_other or account is None or f.amount <= 0:
                continue
            if account.asset_class != "cash" or account.shared_space:
                book.transfers.append(Transfer(None, f.id, basis="other_member"))

    def _compatible(self, book: Book, fact: Fact, other: Fact) -> bool:
        if not fact.counterparty or not self.holders:
            return True
        cp = fold(fact.counterparty)
        institution = fold(book.accounts[other.account].institution)
        return any(fold(h) in cp for h in self.holders) or institution in cp

    def _labelled_transfers(self, book: Book) -> None:
        known = {f.id: f for f in book.facts}
        window = 2 * timedelta(days=self.window_days)
        for lb in self.labels:
            fact = known.get(lb.fact)
            if fact is None or not lb.transfer_with or lb.transfer_with not in book.accounts:
                continue
            if lb.transfer_with == fact.account:
                continue
            used = book.transferred() | {x.fact for x in self.labels}
            twins = sorted(
                (
                    f
                    for f in book.facts
                    if f.account == lb.transfer_with
                    and f.amount == -fact.amount
                    and f.id not in used
                    and f.source != "inferred"
                    and abs(f.on - fact.on) <= window
                ),
                key=lambda f: (abs(f.on - fact.on), f.id),
            )
            if twins:
                twin = twins[0]
                out, inn = (fact, twin) if fact.amount < 0 else (twin, fact)
                book.transfers.append(Transfer(out.id, inn.id, basis="manual"))
            else:
                book.transfers.append(self._infer_leg(book, fact, lb.transfer_with))

    def _match_transfers(self, book: Book, skip: set[str]) -> None:
        used = skip | book.transferred()
        own = [f for f in book.facts if f.account in book.accounts and f.id not in used]
        ins_by_amount: dict[Decimal, list[Fact]] = defaultdict(list)
        for f in own:
            if f.amount > 0:
                ins_by_amount[f.amount].append(f)
        window = timedelta(days=self.window_days)
        pairs = []
        for out in (f for f in own if f.amount < 0):
            for i in ins_by_amount.get(-out.amount, ()):
                gap = abs(i.on - out.on)
                if gap > 2 * window:
                    continue
                if i.account == out.account and book.accounts[i.account].asset_class == "cash":
                    continue
                if not (self._compatible(book, out, i) and self._compatible(book, i, out)):
                    continue
                ev = self._evidence(book, out, i)
                if ev is not None and (gap <= window or ev >= 2):
                    pairs.append((ev, gap, out, i))
        by_out: dict[str, list] = defaultdict(list)
        for p in pairs:
            by_out[p[2].id].append(p)
        pairs.sort(key=lambda p: (-p[0], p[1], p[2].on, p[2].id, p[3].id))
        for ev, gap, out, i in pairs:
            if out.id in used or i.id in used:
                continue
            rivals = [
                q
                for q in by_out[out.id]
                if q[3].id not in used and q[3].id != i.id and q[0] == ev and q[1] == gap
            ]
            institutions = {book.accounts[q[3].account].institution for q in rivals}
            if ev == 0 and rivals and institutions - {book.accounts[i.account].institution}:
                continue
            book.transfers.append(Transfer(out.id, i.id))
            used |= {out.id, i.id}

    def _evidence(self, book: Book, out: Fact, inn: Fact) -> int | None:
        score = 0
        for a, b in ((out, inn), (inn, out)):
            target = book.account_of_iban(a.counterparty_iban)
            if target:
                if target != b.account:
                    return None
                score += 5
            mine = book.accounts[a.account]
            other = book.accounts[b.account].institution
            said = mine.internal and re.search(mine.internal, a.text, re.IGNORECASE)
            if a.own_transfer or said:
                if other != mine.institution:
                    return None
                score += 1
            named = self._named_institutions(book, a)
            if named:
                if other not in named:
                    return None
                score += 2
        return score

    def _named_institutions(self, book: Book, fact: Fact) -> set[str]:
        hay = fold(f"{fact.text} {fact.counterparty or ''}")
        own_inst = book.accounts[fact.account].institution
        named = set()
        for acc in book.accounts.values():
            if acc.movements == "manual" or acc.institution == own_inst:
                continue
            if any(fold(name) in hay for name in (acc.institution, *acc.aliases)):
                named.add(acc.institution)
        return named

    def _by_iban(self, book: Book, skip: set[str]) -> None:
        used = skip | book.transferred()
        for fact in [f for f in book.facts if f.id not in used and f.account in book.accounts]:
            target = book.account_of_iban(fact.counterparty_iban)
            if target and target != fact.account:
                book.transfers.append(self._infer_leg(book, fact, target))

    def _infer_leg(self, book: Book, fact: Fact, target: str) -> Transfer:
        leg = Fact(
            id=f"{fact.id}~{target}",
            account=target,
            on=fact.on,
            amount=-fact.amount,
            text=fact.text,
            source="inferred",
            by_other=fact.by_other,
        )
        book.facts.append(leg)
        if fact.amount < 0:
            return Transfer(fact.id, leg.id, basis="inferred")
        return Transfer(leg.id, fact.id, basis="inferred")

    def _template(self, book: Book, fact: Fact, rule: Rule) -> list[Imputation]:
        out, left = [], fact.amount
        for part in rule.parts:
            if part.get("rest") or part.get("category") not in book.categories:
                continue
            amount = Decimal(str(part["amount"])).copy_abs()
            amount = -amount if fact.amount < 0 else amount
            out.append(
                self._impute(
                    book,
                    fact,
                    Rule(category=part["category"], equity_in=part.get("equity_in")),
                    amount,
                )
            )
            left -= amount
        rest = next((p for p in rule.parts if p.get("rest")), None)
        if rest and left and rest.get("category") in book.categories:
            out.append(self._impute(book, fact, Rule(category=rest["category"]), left))
        return [replace(i, basis=rule.basis) for i in out]

    def _impute(
        self, book: Book, fact: Fact, rule: Rule, amount: Decimal | None = None
    ) -> Imputation:
        category = book.categories[rule.category]
        payer = None
        if category.ownership == "shared":
            account = book.accounts.get(fact.account)
            if fact.account == OTHER or fact.by_other:
                payer = "other"
            elif account and account.shared_space:
                payer = "account"
            else:
                payer = "me"
        return Imputation(
            fact=fact.id,
            amount=fact.amount if amount is None else amount,
            nature=category.nature,
            ownership=category.ownership,
            category=category.id,
            payer=payer,
            equity_in=rule.equity_in,
        )
