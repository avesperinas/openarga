from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)


class BadSource(ValueError):
    pass


def _decimal(value: str | int | float) -> str | int | float:
    try:
        Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"'{value}' is not an amount") from error
    return value


def _day(value: str) -> str:
    date.fromisoformat(value[:10])
    return value


def _instant(value: str) -> str:
    datetime.fromisoformat(value)
    return value


def _month(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError(f"'{value}' is not a month (YYYY-MM)")
    return value


Amount = Annotated[str | int | float, AfterValidator(_decimal)]
Day = Annotated[str, AfterValidator(_day)]
Instant = Annotated[str, AfterValidator(_instant)]
Month = Annotated[str, AfterValidator(_month)]
Text = Annotated[str, Field(min_length=1)]
Isin = Annotated[str, Field(pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")]
Mic = Annotated[str, Field(pattern=r"^[A-Z0-9]{4}$")]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")


class CalendarEvent(Source):
    connection: Text
    uid: Text
    title: str
    all_day: bool
    start: Text
    end: Text
    tz: str = "UTC"
    location: str | None = None
    description: str | None = None
    url: str | None = None
    status: str = "confirmed"
    fingerprint: Text


class CalendarFeed(Source):
    connection: Text
    label: str
    events: dict[str, str]
    provider: str | None = None
    from_: Day | None = Field(default=None, alias="from")
    to: Day | None = None


class CalendarHolidays(Source):
    connection: Text
    country: Text
    region: str | None = None
    from_: Day = Field(alias="from")
    to: Day
    days: dict[Day, Text]


class FinanceAccount(Source):
    bank: str
    account: Text
    name: str
    kind: str | None = None
    currency: str | None = None
    iban: str | None = None
    iban_tail: str | None = None
    connection: str | None = None


class FinanceMovement(Source):
    account: Text
    reference: Text
    booked_on: Day
    amount: Amount
    currency: str
    value_on: Day | None = None
    description: str | None = None
    counterparty: str | None = None
    counterparty_iban: str | None = None
    raw_descriptor: Any = None
    nature: str | None = None
    merchant: str | None = None
    bank_category: str | None = None
    own_transfer: bool | None = None


class FinanceMovementDetail(Source):
    account: Text
    reference: Text
    counterparty_iban: str | None = None
    counterparty_name: str | None = None
    creditor_name: str | None = None
    debtor_name: str | None = None
    bank_transaction_code: dict[str, Any] | None = None


class FinanceBalance(Source):
    account: Text
    on: Day
    amount: Amount
    currency: str
    name: str | None = None
    kind: str | None = None
    account_currency: str | None = None
    iban_tail: str | None = None
    balance_type: str | None = None


class FinanceHolding(Source):
    account: Text
    symbol: Text
    on: Day
    quantity: Amount | None = None
    price: Amount | None = None
    value: Amount | None = None
    name: str | None = None
    isin: Isin | None = None
    kind: Literal["fund", "listed"] | None = None
    mic: Mic | None = None
    quote_currency: Currency | None = None

    @model_validator(mode="after")
    def _quantity_or_value(self) -> FinanceHolding:
        if self.quantity is None and self.value is None:
            raise ValueError("a position says how much is held or what it is worth")
        return self


class FinancePrice(Source):
    symbol: Text
    on: Day
    price: Amount
    currency: Text
    name: str | None = None
    isin: Isin | None = None
    kind: Literal["fund", "listed"] | None = None
    mic: Mic | None = None
    quote_currency: Currency | None = None


class FinanceTrade(Source):
    account: Text
    id: Text
    at: Instant
    side: Literal["buy", "sell", "in", "out"]
    symbol: Text
    quantity: Amount
    price: Amount | None = None
    fee: Amount | None = None
    group: str | None = None

    @model_validator(mode="after")
    def _priced(self) -> FinanceTrade:
        if Decimal(str(self.quantity)) <= 0:
            raise ValueError("quantity: what moves is more than zero")
        if self.side in ("buy", "sell") and self.price is None:
            raise ValueError("price: a buy or a sell says at what price")
        return self


class HealthSteps(Source):
    date: Day
    steps: Annotated[int, Field(ge=0)]


class HealthDaily(Source):
    date: Day
    metrics: dict[str, float]


class HealthProfile(Source):
    blood_type: str | None = None
    sex: str | None = None
    birth_date: Day | None = None
    height_cm: float | None = None
    cardio_medications: str | None = None
    walking_stride_cm: Annotated[float, Field(ge=10, le=300)] | None = None
    running_stride_cm: Annotated[float, Field(ge=10, le=400)] | None = None
    irn_enrolled: bool | None = None


class SleepSegment(BaseModel):
    start: Instant
    end: Instant
    stage: Literal["awake", "light", "deep", "rem", "asleep", "restless"]


class HealthSleep(Source):
    id: Text
    date: Day
    start: Instant
    end: Instant
    minutes_asleep: Annotated[int, Field(ge=0, le=1440)]
    minutes_awake: Annotated[int, Field(ge=0, le=1440)] | None = None
    minutes_in_bed: Annotated[int, Field(ge=0, le=1440)] | None = None
    minutes_to_fall_asleep: Annotated[int, Field(ge=0, le=1440)] | None = None
    main: bool = True
    stages: dict[Literal["awake", "light", "deep", "rem"], int] | None = None
    segments: list[SleepSegment] = []
    awakenings: Annotated[int, Field(ge=0, le=500)] | None = None
    minutes_after_wake_up: Annotated[int, Field(ge=0, le=1440)] | None = None
    minutes_out_of_bed: Annotated[int, Field(ge=0, le=1440)] | None = None


class HeartBucket(BaseModel):
    minute: Annotated[int, Field(ge=0, lt=1440)]
    min: Annotated[float, Field(ge=20, le=250)]
    avg: Annotated[float, Field(ge=20, le=250)]
    max: Annotated[float, Field(ge=20, le=250)]
    steps: Annotated[int, Field(ge=0, le=1000)] | None = None


class HealthHeart(Source):
    date: Day
    step: Annotated[int, Field(ge=1, le=60)]
    buckets: list[HeartBucket]


class ExerciseBeat(BaseModel):
    s: Annotated[int, Field(ge=0, le=86400)]
    bpm: Annotated[float, Field(ge=20, le=250)]


class HealthExercise(Source):
    id: Text
    kind: Text
    name: Text
    start: Instant
    end: Instant
    minutes: Annotated[float, Field(ge=0, le=1440)] | None = None
    kcal: Annotated[float, Field(ge=0)] | None = None
    distance_km: Annotated[float, Field(ge=0)] | None = None
    steps: Annotated[int, Field(ge=0)] | None = None
    heart_rate_avg: Annotated[float, Field(ge=20, le=250)] | None = None
    active_zone_min: Annotated[float, Field(ge=0)] | None = None
    elevation_gain_m: Annotated[float, Field(ge=0)] | None = None
    avg_speed_kmh: Annotated[float, Field(ge=0)] | None = None
    hr_zone_min: dict[Literal["light", "moderate", "vigorous", "peak"], float] | None = None
    cadence_spm: Annotated[float, Field(ge=0, le=400)] | None = None
    stride_length_cm: Annotated[float, Field(ge=0, le=400)] | None = None
    run_vo2max: Annotated[float, Field(ge=0, le=100)] | None = None
    swim_lengths: Annotated[int, Field(ge=0)] | None = None
    has_gps: bool | None = None
    heart: Annotated[list[ExerciseBeat], Field(max_length=20000)] | None = None


EcgResult = Literal[
    "normal_sinus_rhythm",
    "atrial_fibrillation",
    "inconclusive",
    "inconclusive_high_heart_rate",
    "inconclusive_low_heart_rate",
    "unreadable",
    "not_analyzed",
]


class HealthEcg(Source):
    id: Text
    start: Instant
    end: Instant
    result: EcgResult | None = None
    heart_rate_avg: Annotated[float, Field(ge=20, le=250)] | None = None
    sampling_hz: Annotated[int, Field(ge=1, le=10_000)] | None = None
    millivolts_scale: Annotated[int, Field(ge=1)] | None = None
    leads: Annotated[int, Field(ge=1, le=12)] | None = None
    device: str | None = None
    samples: list[int] = []


class HealthIrn(Source):
    id: Text
    start: Instant
    end: Instant
    windows: Annotated[int, Field(ge=0)] = 0
    positive_windows: Annotated[int, Field(ge=0)] = 0
    device: str | None = None


class HealthDevice(Source):
    id: Text
    name: Text
    kind: Literal["tracker", "scale", "other"] = "other"
    battery_pct: Annotated[int, Field(ge=0, le=100)] | None = None
    battery: Literal["high", "medium", "low", "empty"] | None = None
    last_sync: Instant | None = None
    features: list[str] = []


class ClaudeWindow(Source):
    key: Text
    account_id: Text
    success: bool
    status_code: int | None = None
    window_resets_at: Instant | None = None
    window_utilization: float | None = None
    week_resets_at: Instant | None = None
    week_utilization: float | None = None


class ClaudePing(ClaudeWindow):
    trigger: str
    request_id: str | None = None
    duration_ms: int | None = None
    output: str | None = None


class ClaudeUsage(ClaudeWindow):
    detail: str | None = None


class EconomyCpi(Source):
    month: Month
    index: float
    series: str
    base_year: int | None = None
    area: str | None = None


LEISURE_CATEGORIES = ("eat", "stage", "culture", "festival", "outdoors")


def _leisure_category(value: str) -> str:
    if value not in LEISURE_CATEGORIES:
        raise ValueError(f"'{value}' is not one of {', '.join(LEISURE_CATEGORIES)}")
    return value


class LeisureEvent(Source):
    connection: Text
    key: Text
    fingerprint: Text
    title: Text
    starts_on: Day
    ends_on: Day
    time: str | None = None
    venue: str | None = None
    town: str | None = None
    category: Annotated[str, AfterValidator(_leisure_category)]
    summary: str | None = None
    link: Text
    source_name: str | None = None
    source_page: str | None = None
    recurring: bool = False


SHAPES: dict[str, type[Source]] = {
    "calendar.event": CalendarEvent,
    "calendar.feed": CalendarFeed,
    "calendar.holidays": CalendarHolidays,
    "finance.account": FinanceAccount,
    "finance.movement": FinanceMovement,
    "finance.movement_detail": FinanceMovementDetail,
    "finance.balance": FinanceBalance,
    "finance.holding": FinanceHolding,
    "finance.price": FinancePrice,
    "finance.trade": FinanceTrade,
    "health.steps": HealthSteps,
    "health.daily": HealthDaily,
    "health.profile": HealthProfile,
    "health.sleep": HealthSleep,
    "health.heart": HealthHeart,
    "health.exercise": HealthExercise,
    "health.ecg": HealthEcg,
    "health.irn": HealthIrn,
    "health.device": HealthDevice,
    "ai.claude.ping": ClaudePing,
    "ai.claude.usage": ClaudeUsage,
    "economy.cpi": EconomyCpi,
    "leisure.event": LeisureEvent,
}

SOURCE_CONTRACTS = frozenset(SHAPES)


AT_NOON = frozenset({"health.heart"})


def check_ts(event_type: str, payload: dict[str, Any], ts: str | datetime) -> None:
    if event_type not in AT_NOON:
        return
    try:
        when = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        expected = datetime.fromisoformat(f"{payload['date']}T12:00:00+00:00")
    except (KeyError, TypeError, ValueError) as error:
        raise BadSource(f"{event_type} without a readable ts and day: {error}") from error
    if when.tzinfo is None or when != expected:
        raise BadSource(f"{event_type} has ts {when.isoformat()}, not noon UTC of its day")


def check(event_type: str, payload: dict[str, Any]) -> None:
    shape = SHAPES.get(event_type)
    if shape is None:
        raise BadSource(f"'{event_type}' is not a source contract")
    try:
        shape.model_validate(payload)
    except ValidationError as error:
        where = "; ".join(
            f"{'.'.join(str(part) for part in detail['loc']) or '<root>'}: {detail['msg']}"
            for detail in error.errors()
        )
        raise BadSource(f"{event_type} does not meet its contract: {where}") from error
