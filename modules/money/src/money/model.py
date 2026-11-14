from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

AssetClass = Literal["cash", "investment", "real_estate", "receivable"]
Movements = Literal["api", "statement", "matched", "manual"]
ValueMode = Literal["balance", "computed", "snapshot", "manual"]
Nature = Literal["income", "expense"]
Ownership = Literal["individual", "shared"]
Payer = Literal["account", "me", "other"]
Split = Literal["fifty_fifty", "proportional"]
FactSource = Literal["api", "statement", "manual", "inferred"]

OTHER = "@other"
"""The account of what another member pays with their money: not yours, but shared spending."""


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    institution: str
    type: str
    asset_class: AssetClass
    movements: Movements
    value: ValueMode
    spending: bool = True
    ownership: Decimal = Decimal(1)
    counts_for_savings: bool = False
    shared_space: bool = False
    aliases: tuple[str, ...] = ()
    """How the institution appears in other banks' texts, besides its name."""
    internal: str | None = None
    """Text pattern the institution uses for a transfer between its own accounts."""
    ibans: tuple[str, ...] = ()
    """Its own and the paying-in ones: an entry whose counterparty has one of these IBANs is a
    transfer to this account, nothing more."""
    cash: bool = False
    """Counts as money at hand (its type says so)."""
    liquid: bool = True
    """Can be taken out at will (a pension plan cannot)."""
    role: str | None = None
    """Its role: `emergency_fund`."""


@dataclass(frozen=True)
class Fact:
    id: str
    account: str
    on: date
    amount: Decimal
    text: str
    source: FactSource = "api"
    by_other: bool = False
    counterparty: str | None = None
    counterparty_iban: str | None = None
    bank_category: str | None = None
    """The bank's own classification ("FUEL STATIONS"), if it gives one."""
    value_on: date | None = None
    """The day it moves the balance; it can be before or after `on` (the entry)."""
    own_transfer: bool = False
    """The source says it is a transfer between its own accounts at the same institution."""


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    nature: Nature
    ownership: Ownership
    split: Split | None = None
    extended_savings: bool = False
    not_living: bool = False
    """Not living expense (Work): left out of the KPI spending."""
    not_basic: bool = False
    """Not basic spending (Travel, Leisure): left out of basic spending."""


@dataclass(frozen=True)
class Imputation:
    fact: str
    amount: Decimal
    nature: Nature
    ownership: Ownership
    category: str
    payer: Payer | None = None
    equity_in: str | None = None
    basis: str = "rule"
    """`manual` (a label), `rule`, `bank` (the institution's classification) or `default` (the
    account's default: it labels, but stays marked for the periodic review)."""


@dataclass(frozen=True)
class Transfer:
    out_fact: str | None
    in_fact: str
    basis: str = "match"


@dataclass(frozen=True)
class Balance:
    account: str
    on: date
    amount: Decimal
    kind: str = "closing"


@dataclass(frozen=True)
class Holding:
    account: str
    on: date
    symbol: str
    value: Decimal
    price: Decimal | None = None
    name: str = ""
    """As its institution shows it, or as the person wrote it."""


@dataclass
class Book:
    accounts: dict[str, Account]
    categories: dict[str, Category]
    facts: list[Fact] = field(default_factory=list)
    balances: list[Balance] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    imputations: list[Imputation] = field(default_factory=list)
    settlements: set[str] = field(default_factory=set)
    """Payments between members that settle a part: neither expense nor income."""
    returns: set[str] = field(default_factory=set)
    """Return of its product (interest): neither flow nor transfer."""
    asking: set[str] = field(default_factory=set)
    """What waits for the person to label it (cash)."""
    ruled: dict[str, int] = field(default_factory=dict)
    """The rule that decided each fact, by its position among the person's rules."""
    holdings: list[Holding] = field(default_factory=list)
    prices: dict[str, list[tuple[date, Decimal]]] = field(default_factory=dict)
    """The price of each symbol on each day, in the base currency, by date."""
    _facts: dict[str, Fact] = field(default_factory=dict, repr=False)

    def fact(self, fact_id: str) -> Fact:
        if len(self._facts) != len(self.facts):
            self._facts = {f.id: f for f in self.facts}
        return self._facts[fact_id]

    def account_of_iban(self, iban: str | None) -> str | None:
        if not iban:
            return None
        iban = iban.replace(" ", "").upper()
        return next((a.id for a in self.accounts.values() if iban in a.ibans), None)

    def transferred(self) -> set[str]:
        return {f for t in self.transfers for f in (t.out_fact, t.in_fact) if f}

    def explained(self) -> set[str]:
        return self.transferred() | self.returns | self.settlements
