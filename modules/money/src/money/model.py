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
"""La cuenta de lo que otro miembro paga con su dinero: no es tuya, pero el gasto es común."""


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
    """Cómo aparece la entidad en el texto de otros bancos, además de su nombre."""
    internal: str | None = None
    """Patrón del texto que la entidad usa para un traspaso entre sus propias cuentas."""
    ibans: tuple[str, ...] = ()
    """El suyo y los de ingreso: un apunte cuya contraparte tiene uno de estos IBAN es un traspaso
    a esta cuenta, sin más."""
    cash: bool = False
    """Cuenta como dinero a mano (lo dice su tipo)."""
    liquid: bool = True
    """Se puede sacar cuando se quiera (un plan de pensiones, no)."""
    role: str | None = None
    """Su papel: `emergency_fund`, el fondo de contingencia."""


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
    """La clasificación que pone el propio banco ("GASOLINERAS"), si la pone."""
    value_on: date | None = None
    """El día en que mueve el saldo; puede ir antes o después de `on` (el apunte)."""
    own_transfer: bool = False
    """La fuente dice que es un traspaso entre cuentas suyas de la misma entidad (ADR-0100 §7)."""


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    nature: Nature
    ownership: Ownership
    split: Split | None = None
    extended_savings: bool = False
    not_living: bool = False
    """No es gasto de vida (Trabajo): fuera de los gastos de los KPIs."""
    not_basic: bool = False
    """No es gasto básico (Viajes, Ocio): fuera del gasto básico."""


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
    """`manual` (etiqueta), `rule`, `bank` (clasificación de la entidad) o `default` (el defecto
    de la cuenta: etiqueta, pero queda marcado para la revisión periódica)."""


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
    """Como lo enseña su entidad, o como lo apuntó la persona."""


@dataclass
class Book:
    accounts: dict[str, Account]
    categories: dict[str, Category]
    facts: list[Fact] = field(default_factory=list)
    balances: list[Balance] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    imputations: list[Imputation] = field(default_factory=list)
    settlements: set[str] = field(default_factory=set)
    """Pagos entre miembros que saldan una parte: ni gasto ni ingreso."""
    returns: set[str] = field(default_factory=set)
    """Rentabilidad de su producto (intereses): ni flujo ni traspaso."""
    asking: set[str] = field(default_factory=set)
    """Lo que espera a que la persona lo etiquete (el efectivo)."""
    ruled: dict[str, int] = field(default_factory=dict)
    """La regla que decidió cada hecho, por su posición en las de la persona."""
    holdings: list[Holding] = field(default_factory=list)
    prices: dict[str, list[tuple[date, Decimal]]] = field(default_factory=dict)
    """El precio de cada día de cada símbolo, en euros y por fecha (ADR-0113)."""
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
