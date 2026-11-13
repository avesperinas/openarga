import pytest

from arga_contracts import sources

MOVEMENT = {
    "account": "acc-1",
    "reference": "ref-1",
    "booked_on": "2026-10-01",
    "amount": "-12.30",
    "currency": "EUR",
}


def test_a_movement_with_what_an_app_needs_passes() -> None:
    sources.check("finance.movement", MOVEMENT)


def test_a_source_may_add_fields_an_app_does_not_read() -> None:
    sources.check("finance.movement", {**MOVEMENT, "raw_descriptor": {"x": 1}, "extra": True})


@pytest.mark.parametrize(
    ("missing", "field"),
    [("amount", "amount"), ("booked_on", "booked_on"), ("account", "account")],
)
def test_a_movement_without_what_an_app_needs_is_refused(missing: str, field: str) -> None:
    payload = {key: value for key, value in MOVEMENT.items() if key != missing}
    with pytest.raises(sources.BadSource, match=field):
        sources.check("finance.movement", payload)


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("finance.movement", {**MOVEMENT, "amount": "doce"}),
        ("finance.movement", {**MOVEMENT, "booked_on": "ayer"}),
        ("economy.cpi", {"month": "2026-1", "index": 1.0, "series": "IPC"}),
        ("health.steps", {"date": "2026-10-01", "steps": -1}),
        ("calendar.event", {"connection": "c", "uid": "u", "title": "x", "all_day": True}),
        (
            "calendar.holidays",
            {
                "connection": "c",
                "country": "ES",
                "from": "2026-01-01",
                "to": "2027-12-31",
                "days": {"1 de enero": "Año Nuevo"},
            },
        ),
    ],
)
def test_what_does_not_fit_says_why(event_type: str, payload: dict) -> None:
    with pytest.raises(sources.BadSource, match=event_type):
        sources.check(event_type, payload)


def test_a_type_that_is_not_a_source_contract_is_refused() -> None:
    with pytest.raises(sources.BadSource, match="is not a source contract"):
        sources.check("money.movement", MOVEMENT)


def test_checking_does_not_change_the_payload() -> None:
    payload = {**MOVEMENT, "amount": "-12.300"}
    sources.check("finance.movement", payload)
    assert payload["amount"] == "-12.300"


def test_a_feed_keeps_its_from() -> None:
    sources.check(
        "calendar.feed",
        {"connection": "c", "label": "F1", "events": {"u": "f"}, "from": "2025-01-01"},
    )


LEISURE = {
    "connection": "c",
    "key": "k",
    "fingerprint": "f",
    "title": "Euskadiko Orkestra",
    "starts_on": "2026-10-03",
    "ends_on": "2026-10-03",
    "category": "stage",
    "link": "https://agenda.example/evento/1",
}


def test_an_agenda_event_fits_with_a_closed_category() -> None:
    sources.check("leisure.event", LEISURE)
    with pytest.raises(sources.BadSource, match="category"):
        sources.check("leisure.event", {**LEISURE, "category": "concierto"})
    with pytest.raises(sources.BadSource, match="link"):
        sources.check("leisure.event", {key: v for key, v in LEISURE.items() if key != "link"})


def test_a_holding_says_how_much_or_what_it_is_worth() -> None:
    base = {"account": "plan", "symbol": "FUND", "on": "2026-10-01"}
    sources.check("finance.holding", {**base, "quantity": "2.5"})
    sources.check("finance.holding", {**base, "value": "1200.50"})
    with pytest.raises(sources.BadSource, match="how much is held or what it is worth"):
        sources.check("finance.holding", base)


def test_a_price_is_of_a_symbol_on_a_day() -> None:
    price = {"symbol": "FUND", "on": "2026-10-01", "price": "600.78", "currency": "EUR"}
    sources.check("finance.price", price)
    with pytest.raises(sources.BadSource, match="price"):
        sources.check("finance.price", {**price, "price": "mucho"})


def test_a_trade_says_what_moved_and_a_sale_says_at_how_much() -> None:
    sale = {
        "account": "bitvavo",
        "id": "t-1",
        "at": "2026-10-05T10:00:00+00:00",
        "side": "sell",
        "symbol": "BTC",
        "quantity": "0.1",
        "price": "55000",
        "fee": "13.75",
    }
    sources.check("finance.trade", sale)
    arrived = {**sale, "side": "in", "price": None, "fee": None}
    sources.check("finance.trade", arrived)
    with pytest.raises(sources.BadSource, match="price"):
        sources.check("finance.trade", {**sale, "price": None})
    with pytest.raises(sources.BadSource, match="quantity"):
        sources.check("finance.trade", {**sale, "quantity": "0"})
    with pytest.raises(sources.BadSource, match="side"):
        sources.check("finance.trade", {**sale, "side": "swap"})


def test_an_exercise_may_carry_its_heart_every_few_seconds() -> None:
    exercise = {
        "id": "x1",
        "kind": "STATIONARY_BIKE",
        "name": "Bici estática",
        "start": "2026-10-13T12:00:00+02:00",
        "end": "2026-10-13T12:30:00+02:00",
        "heart": [{"s": 0, "bpm": 92}, {"s": 5, "bpm": 95.5}],
    }
    sources.check("health.exercise", exercise)
    with pytest.raises(sources.BadSource, match="heart"):
        sources.check("health.exercise", {**exercise, "heart": [{"s": -1, "bpm": 90}]})


HEART = {"date": "2026-10-14", "step": 1, "buckets": []}


def test_the_pulse_of_a_day_goes_at_noon_utc_of_that_day() -> None:
    sources.check_ts("health.heart", HEART, "2026-10-14T12:00:00+00:00")
    sources.check_ts("health.heart", HEART, "2026-10-14T14:00:00+02:00")
    with pytest.raises(sources.BadSource, match="noon UTC"):
        sources.check_ts("health.heart", HEART, "2026-10-14T07:00:00+00:00")
    sources.check_ts("health.steps", {"date": "2026-10-14", "steps": 1}, "2026-10-14T07:00:00Z")
    with pytest.raises(sources.BadSource):
        sources.check_ts("health.heart", {**HEART, "date": "2026-10-14T00:00"}, "2026-10-14T12:00")
    with pytest.raises(sources.BadSource):
        sources.check_ts("health.heart", HEART, "2026-10-14T12:00:00")
