from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from travel.travel.common import CATEGORIES, Category, Mode, Phase, Status
from travel.travel.places import Place


class TripIn(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    starts_on: date
    ends_on: date
    travellers: Annotated[int, Field(ge=1, le=50)] = 1
    companions: Annotated[list[Annotated[str, Field(max_length=60)]], Field(max_length=30)] = []
    tags: Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=20)] = []
    notes: Annotated[str | None, Field(max_length=4000)] = None
    summary: Annotated[str | None, Field(max_length=1000)] = None
    status: Status | None = None
    budget_eur: Annotated[Decimal | None, Field(ge=0, le=Decimal("99999999"), decimal_places=2)] = (
        None
    )

    @model_validator(mode="after")
    def in_order(self) -> TripIn:
        if self.ends_on < self.starts_on:
            raise ValueError("el viaje no puede acabar antes de empezar")
        return self


class BookingIn(BaseModel):
    confirmation: Annotated[str | None, Field(max_length=60)] = None
    provider: Annotated[str | None, Field(max_length=80)] = None
    booking_url: Annotated[str | None, Field(max_length=500, pattern=r"^https?://")] = None
    cost_eur: Annotated[Decimal | None, Field(ge=0, le=Decimal("99999999"), decimal_places=2)] = (
        None
    )
    paid_by: Annotated[str | None, Field(max_length=60)] = None


class StayIn(BookingIn):
    place_id: str
    arrives_on: date
    leaves_on: date
    accommodation: Annotated[str | None, Field(max_length=200)] = None
    check_in_at: time | None = None
    check_out_at: time | None = None
    address: Annotated[str | None, Field(max_length=300)] = None

    @model_validator(mode="after")
    def in_order(self) -> StayIn:
        if self.leaves_on < self.arrives_on:
            raise ValueError("no se puede salir de un sitio antes de llegar")
        return self


class VisitIn(BaseModel):
    place_id: str
    stay_id: str | None = None
    visited_on: date | None = None
    note: Annotated[str | None, Field(max_length=500)] = None


class LegIn(BookingIn):
    from_place_id: str
    to_place_id: str
    mode: Mode
    travelled_on: date | None = None
    note: Annotated[str | None, Field(max_length=500)] = None
    on_map: bool | None = None
    departs_at: time | None = None
    arrives_on: date | None = None
    arrives_at: time | None = None
    carrier: Annotated[str | None, Field(max_length=80)] = None
    number: Annotated[str | None, Field(max_length=40)] = None
    from_code: Annotated[str | None, Field(max_length=40)] = None
    to_code: Annotated[str | None, Field(max_length=40)] = None
    terminal: Annotated[str | None, Field(max_length=40)] = None
    seat: Annotated[str | None, Field(max_length=80)] = None
    ticket_leg_id: str | None = None

    @model_validator(mode="after")
    def somewhere(self) -> LegIn:
        if self.from_place_id == self.to_place_id:
            raise ValueError("un trayecto va de un sitio a otro distinto")
        if self.arrives_on and self.travelled_on and self.arrives_on < self.travelled_on:
            raise ValueError("un trayecto no llega antes de salir")
        return self


class ShareIn(BaseModel):
    traveller_id: str
    amount: Annotated[Decimal, Field(ge=0, le=Decimal("9999999999"), decimal_places=2)]


class ExpenseIn(BaseModel):
    id: UUID | None = None
    category: Category
    concept: Annotated[str, Field(min_length=1, max_length=60)]
    amount_eur: Annotated[Decimal | None, Field(ge=0, le=Decimal("99999999"), decimal_places=2)] = (
        None
    )
    amount: Annotated[Decimal | None, Field(ge=0, le=Decimal("9999999999"), decimal_places=2)] = (
        None
    )
    currency: Annotated[str | None, Field(pattern=r"^[A-Za-z]{3}$")] = None
    fx_rate: Annotated[Decimal | None, Field(gt=0, le=Decimal("100000"))] = None
    spent_on: date | None = None
    paid_by: str | None = None
    shares: list[ShareIn] | None = None
    note: Annotated[str | None, Field(max_length=300)] = None

    @model_validator(mode="after")
    def some_amount(self) -> ExpenseIn:
        if self.amount is None and self.amount_eur is None:
            raise ValueError(
                "hace falta el importe: por persona en euros, o lo pagado en su moneda"
            )
        if self.amount is not None and self.currency is None:
            raise ValueError("lo pagado va con su moneda: EUR, JPY, USD…")
        return self

    @field_validator("concept")
    @classmethod
    def tidy(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("el concepto no puede estar vacío")
        return cleaned


class Booking(BaseModel):
    confirmation: str | None = None
    provider: str | None = None
    booking_url: str | None = None
    cost_eur: float | None = None
    paid_by: str | None = None


class Stay(Booking):
    id: str
    place: Place
    arrives_on: date
    leaves_on: date
    nights: int
    accommodation: str | None
    check_in_at: time | None = None
    check_out_at: time | None = None
    address: str | None = None


class Visit(BaseModel):
    id: str
    place: Place
    stay_id: str | None
    visited_on: date | None
    note: str | None


class Leg(Booking):
    id: str
    from_place: Place
    to_place: Place
    from_stay_id: str | None = None
    to_stay_id: str | None = None
    mode: Mode
    travelled_on: date | None
    km: float | None
    note: str | None
    on_map: bool | None = None
    departs_at: time | None = None
    arrives_on: date | None = None
    arrives_at: time | None = None
    carrier: str | None = None
    number: str | None = None
    from_code: str | None = None
    to_code: str | None = None
    terminal: str | None = None
    seat: str | None = None
    ticket_leg_id: str | None = None


class Expense(BaseModel):
    id: str
    category: Category
    concept: str
    amount_eur: float
    note: str | None
    amount: float | None = None
    currency: str = "EUR"
    fx_rate: float | None = None
    fx_on: date | None = None
    total_eur: float | None = None
    spent_on: date | None = None
    paid_by: str | None = None
    paid_by_name: str | None = None
    mine: bool = True
    stay_id: str | None = None
    leg_id: str | None = None
    block_id: str | None = None


class Spend(BaseModel):
    per_person: float
    group: float
    per_day: float | None
    by_category: dict[str, float]


class Cover(BaseModel):
    version: int
    author: str | None = None
    license: str | None = None
    page: str | None = None


class TripSummary(BaseModel):
    id: str
    title: str
    starts_on: date
    ends_on: date
    days: int
    nights: int
    travellers: int
    companions: list[str]
    tags: list[str]
    countries: list[str]
    km: float
    spend: Spend
    source: str
    archived: bool
    status: Status = "confirmed"
    phase: Phase = "done"
    idea_id: str | None = None
    budget_eur: float | None = None
    space_id: str | None = None
    mine: bool = True
    summary: str | None = None
    cover: Cover | None = None


class Trip(TripSummary):
    notes: str | None
    stays: list[Stay]
    visits: list[Visit]
    legs: list[Leg]
    expenses: list[Expense]


def days_of(starts_on: date, ends_on: date) -> int:
    return (ends_on - starts_on).days + 1


def spend_of(expenses: list[Expense], travellers: int, days: int) -> Spend:
    by_category = {category: 0.0 for category in CATEGORIES}
    for one in expenses:
        by_category[one.category] = round(by_category[one.category] + one.amount_eur, 2)
    per_person = round(sum(by_category.values()), 2)
    return Spend(
        per_person=per_person,
        group=round(per_person * travellers, 2),
        per_day=round(per_person / days, 2) if expenses and days else None,
        by_category=by_category,
    )
