from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import arga_contracts as contracts
from arga_contracts import sources
from kernel import manifests


def test_the_kernel_validates_the_same_contracts_and_services() -> None:
    assert manifests.CONTRACTS == contracts.CONTRACTS
    assert manifests.SERVICES == contracts.SERVICES
    assert manifests.ADDRESSED == contracts.ADDRESSED
    assert manifests.SOURCE_CONTRACTS == sources.SOURCE_CONTRACTS


def test_a_move_carries_its_zone_or_whole_days() -> None:
    timed = contracts.agenda_move(
        uid="training:activity:1",
        start="2026-10-01T19:00:00+02:00",
        end="2026-10-01T20:00:00+02:00",
    )
    assert timed["start"] == "2026-10-01T19:00:00+02:00"
    whole = contracts.agenda_move(
        uid="study:assessment:1", start="2026-10-01", end="2026-10-02", all_day=True
    )
    assert whole["start"] == "2026-10-01"


@pytest.mark.parametrize(
    "fields",
    [
        {"uid": "x:y:1", "start": "2026-10-01T19:00:00", "end": "2026-10-01T20:00:00+02:00"},
        {"uid": "x:y:1", "start": "2026-10-01T20:00:00+02:00", "end": "2026-10-01T19:00:00+02:00"},
        {"uid": "x:y:1", "start": "2026-10-01", "end": "2026-10-01", "all_day": True},
        {
            "uid": "x:y:1",
            "start": "2026-10-01T19:00:00+02:00",
            "end": "2026-10-02",
            "all_day": True,
        },
    ],
)
def test_a_move_that_does_not_fit_fails_where_it_is_written(fields) -> None:
    with pytest.raises(contracts.BadContract, match="AgendaMove"):
        contracts.agenda_move(**fields)


def test_a_body_weight_is_a_day_and_kilos() -> None:
    assert contracts.body_weight(id="w1", day=date(2026, 9, 28), kg=81.4) == {
        "id": "w1",
        "day": "2026-09-28",
        "kg": 81.4,
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"id": "w1", "day": "2026-09-28", "kg": 0},
        {"id": "w1", "day": "ayer", "kg": 80},
        {"id": "", "day": "2026-09-28", "kg": 80},
        {"id": "w1", "day": "2026-09-28", "kg": 80, "fat": 20},
    ],
)
def test_a_body_weight_that_does_not_fit_fails_where_it_is_written(fields) -> None:
    with pytest.raises(contracts.BadContract, match="BodyWeight"):
        contracts.body_weight(**fields)


def test_an_activity_is_a_name_a_start_with_its_zone_and_minutes() -> None:
    start = datetime(2026, 9, 29, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    assert contracts.activity(
        id="i1:2026-09-29", name="Natación", start=start, minutes=60, tz="Europe/Madrid"
    ) == {
        "id": "i1:2026-09-29",
        "name": "Natación",
        "start": "2026-09-29T19:00:00+02:00",
        "minutes": 60,
        "tz": "Europe/Madrid",
        "removed": False,
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"id": "a", "name": "Natación", "start": "2026-09-29T19:00:00", "tz": "Europe/Madrid"},
        {"id": "a", "name": "", "start": "2026-09-29T19:00:00+02:00", "tz": "Europe/Madrid"},
        {"id": "a", "name": "N", "start": "2026-09-29T19:00:00+02:00", "tz": "X", "minutes": -1},
    ],
)
def test_an_activity_that_does_not_fit_fails_where_it_is_written(fields) -> None:
    with pytest.raises(contracts.BadContract, match="Activity"):
        contracts.activity(**fields)


def test_a_workout_is_a_kind_a_name_and_its_exact_hours() -> None:
    madrid = ZoneInfo("Europe/Madrid")
    found = contracts.workout(
        id="training:activity:a1",
        kind="activity",
        name="Pádel",
        start=datetime(2026, 10, 13, 19, 4, tzinfo=madrid),
        end=datetime(2026, 10, 13, 20, 31, tzinfo=madrid),
        tz="Europe/Madrid",
        band_id="users/me/dataTypes/exercise/dataPoints/9",
        marks=[{"at": datetime(2026, 10, 13, 19, 10, tzinfo=madrid), "label": "8 × 60 kg"}],
    )

    assert found["start"] == "2026-10-13T19:04:00+02:00"
    assert found["end"] == "2026-10-13T20:31:00+02:00"
    assert found["marks"] == [{"at": "2026-10-13T19:10:00+02:00", "label": "8 × 60 kg"}]
    assert found["removed"] is False
    assert found["href"] is None


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "padel"},
        {"name": ""},
        {"start": "2026-10-13T19:00:00"},
        {"end": "2026-10-13T18:00:00+02:00"},
        {"heart": []},
    ],
)
def test_a_workout_that_does_not_fit_fails_where_it_is_written(fields) -> None:
    base = {
        "id": "w",
        "kind": "strength",
        "name": "Pull",
        "start": "2026-10-13T19:00:00+02:00",
        "end": "2026-10-13T20:00:00+02:00",
        "tz": "Europe/Madrid",
    }
    with pytest.raises(contracts.BadContract, match="Workout"):
        contracts.workout(**{**base, **fields})


def test_a_shopping_request_carries_names_and_optional_quantities() -> None:
    request = contracts.shopping_add(items=[{"name": "cebolla", "quantity": "2 ud"}])

    assert request == {"items": [{"name": "cebolla", "quantity": "2 ud", "note": None}]}


@pytest.mark.parametrize("items", [[], [{"name": ""}], [{"name": "x"}] * 41])
def test_a_shopping_request_is_between_one_and_forty_things(items) -> None:
    with pytest.raises(contracts.BadContract):
        contracts.shopping_add(items=items)


def test_the_answer_says_what_was_already_there() -> None:
    answer = contracts.shopping_added(added=[{"name": "leche", "already_on_list": True}], pending=3)

    assert answer["added"][0]["already_on_list"] is True


def test_a_metric_is_the_value_of_a_figure_on_a_day() -> None:
    point = contracts.metric(
        "money",
        key="money.net_worth",
        label="Patrimonio",
        unit="EUR",
        kind="level",
        day=date(2026, 9, 29),
        value=54300,
    )
    assert point == {
        "key": "money.net_worth",
        "label": "Patrimonio",
        "unit": "EUR",
        "kind": "level",
        "day": "2026-09-29",
        "value": 54300.0,
    }
    assert contracts.metric_identity(point) == "money.net_worth@2026-09-29"


def test_a_metric_can_carry_a_parameter_after_a_colon() -> None:
    point = contracts.metric(
        "training",
        key="training.e1rm:sentadilla",
        label="Sentadilla, marca estimada",
        unit="kg",
        kind="level",
        day="2026-09-29",
        value=120.5,
    )
    assert point["key"] == "training.e1rm:sentadilla"


def test_a_metric_with_another_apps_key_fails_in_whoever_publishes_it() -> None:
    with pytest.raises(contracts.BadContract, match="empezar por 'macros.'"):
        contracts.metric(
            "macros",
            key="vitals.steps",
            label="Pasos",
            unit="steps",
            kind="amount",
            day="2026-09-29",
            value=8000,
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"unit": "gr"},
        {"kind": "sum"},
        {"key": "Macros.protein"},
        {"key": "protein"},
        {"label": ""},
        {"value": float("nan")},
        {"day": "29/09/2026"},
    ],
)
def test_a_metric_that_does_not_fit_fails_where_it_is_written(fields) -> None:
    good = {
        "key": "macros.protein",
        "label": "Proteína",
        "unit": "g",
        "kind": "amount",
        "day": "2026-09-29",
        "value": 140,
    }
    with pytest.raises(contracts.BadContract, match="Metric"):
        contracts.metric("macros", **{**good, **fields})


def test_asking_to_log_a_weight_is_kilos_and_maybe_a_day() -> None:
    assert contracts.weight_log(kg=81.4) == {"kg": 81.4, "day": None}
    assert contracts.weight_log(kg=81.4, day="2026-09-28")["day"] == "2026-09-28"
    with pytest.raises(contracts.BadContract, match="WeightLog"):
        contracts.weight_log(kg=4)
    with pytest.raises(contracts.BadContract, match="WeightLog"):
        contracts.weight_log(kg=80, note="no cabe")


def test_the_weight_of_each_day_is_read_from_an_app_view_only() -> None:
    assert "from training.events" in contracts.body_weight_days("training.events")
    with pytest.raises(ValueError, match="vista de eventos"):
        contracts.body_weight_days("vitals.vitals_weight; drop table x")


def test_something_in_custody_names_its_class_and_where_it_opens() -> None:
    found = contracts.custody(
        id="job:1",
        title="Contrato Acme",
        kind="Contrato de trabajo",
        category="contract",
        href="/study/#/empleo/1",
        since="2024-01-08",
    )
    assert found["until"] is None and found["removed"] is False
    with pytest.raises(contracts.BadContract, match="category"):
        contracts.custody(id="x", title="X", kind="Cosa", category="pets", href="/study/")
    with pytest.raises(contracts.BadContract, match="href"):
        contracts.custody(
            id="x", title="X", kind="Cosa", category="other", href="https://fuera.example"
        )


def test_a_trip_says_its_phase_where_it_opens_and_maybe_its_days() -> None:
    idea = contracts.trip(id="i1", title="Japón en sakura", phase="idea", href="/travel/ideas/i1")
    plan = contracts.trip(
        id="t1",
        title="Budapest",
        phase="plan",
        href="/travel/viajes/t1",
        starts_on="2027-11-11",
        ends_on="2027-11-14",
        image="/api/travel/trips/t1/cover?size=thumb&v=1",
        detail="4 días · 2 viajeros",
    )

    assert idea["starts_on"] is None and idea["removed"] is False
    assert plan["ends_on"] == "2027-11-14"


@pytest.mark.parametrize(
    "fields",
    [
        {"phase": "someday"},
        {"href": "https://otra.web/viaje"},
        {"starts_on": "2027-11-11"},
        {"starts_on": "2027-11-14", "ends_on": "2027-11-11"},
    ],
)
def test_a_trip_that_does_not_fit_fails_where_it_is_written(fields) -> None:
    base = {"id": "t1", "title": "Budapest", "phase": "plan", "href": "/travel/viajes/t1"}
    with pytest.raises(contracts.BadContract):
        contracts.trip(**(base | fields))


def test_asking_for_a_trip_idea_is_a_name_and_maybe_where() -> None:
    asked = contracts.trip_idea(title="Escocia", place="Edimburgo", lat=55.95, lon=-3.19)
    made = contracts.trip_idea_made(id="i1", href="/travel/ideas/i1", already=False)

    assert asked["place"] == "Edimburgo"
    assert made["already"] is False
    with pytest.raises(contracts.BadContract):
        contracts.trip_idea(title="Escocia", lat=55.95)
