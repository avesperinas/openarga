from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from arga_agenda import KEY, BadDated, check_event, dated, uid, validate

MADRID_SUMMER = timezone(timedelta(hours=2))


def a_class(**changes: object) -> dict:
    fields = {
        "uid": "study:session:42",
        "title": "Estadística II",
        "start": "2026-10-06T18:00:00+02:00",
        "end": "2026-10-06T20:00:00+02:00",
        "tz": "Europe/Madrid",
        "location": "Study 2.3",
        "href": "/study/sessions/42",
    }
    return {**fields, **changes}


def test_a_timed_object_comes_back_normalised_for_json() -> None:
    payload = dated(**a_class())

    assert payload == {
        "uid": "study:session:42",
        "title": "Estadística II",
        "start": "2026-10-06T18:00:00+02:00",
        "end": "2026-10-06T20:00:00+02:00",
        "all_day": False,
        "tz": "Europe/Madrid",
        "location": "Study 2.3",
        "status": "confirmed",
        "href": "/study/sessions/42",
    }


def test_it_takes_python_datetimes_too() -> None:
    start = datetime(2026, 10, 6, 18, tzinfo=MADRID_SUMMER)
    payload = dated(**a_class(start=start, end=start + timedelta(hours=2)))

    assert payload["end"] == "2026-10-06T20:00:00+02:00"


def test_a_deadline_is_an_instant() -> None:
    payload = dated(**a_class(uid="study:assessment:7", end="2026-10-06T18:00:00+02:00"))

    assert payload["start"] == payload["end"]


def test_a_time_without_a_zone_is_rejected() -> None:
    with pytest.raises(BadDated, match="zona"):
        dated(**a_class(start="2026-10-06T18:00:00", end="2026-10-06T20:00:00"))


def test_the_end_cannot_go_before_the_start() -> None:
    with pytest.raises(BadDated, match="antes del inicio"):
        dated(**a_class(end="2026-10-06T17:00:00+02:00"))


def test_all_day_is_dates_with_an_exclusive_end() -> None:
    payload = dated(
        uid="planner:reminder:3",
        title="ITV del coche",
        start=date(2026, 11, 3),
        end=date(2026, 11, 4),
        all_day=True,
        tz="Europe/Madrid",
        href="/planner/items/9",
    )

    assert (payload["start"], payload["end"], payload["all_day"]) == (
        "2026-11-03",
        "2026-11-04",
        True,
    )


def test_a_one_day_event_ending_the_same_day_is_rejected() -> None:
    with pytest.raises(BadDated, match="exclusivo"):
        dated(**a_class(all_day=True, start="2026-11-03", end="2026-11-03"))


def test_all_day_does_not_take_a_time() -> None:
    with pytest.raises(BadDated, match="no es una fecha"):
        dated(**a_class(all_day=True))
    with pytest.raises(BadDated, match="sin hora"):
        dated(
            **a_class(
                all_day=True,
                start=datetime(2026, 11, 3, tzinfo=UTC),
                end=datetime(2026, 11, 4, tzinfo=UTC),
            )
        )


def test_a_timed_object_does_not_take_bare_dates() -> None:
    with pytest.raises(BadDated, match="lleva hora"):
        dated(**a_class(start=date(2026, 11, 3), end=date(2026, 11, 4)))


@pytest.mark.parametrize("zone", ["Madrid", "CET+1", "", "Europe/Atlantis"])
def test_the_zone_is_an_iana_name(zone: str) -> None:
    with pytest.raises(BadDated, match="tz"):
        dated(**a_class(tz=zone))


@pytest.mark.parametrize("value", ["session:42", "Study:session:42", "study:session:", "study:42"])
def test_the_uid_names_module_kind_and_id(value: str) -> None:
    with pytest.raises(BadDated, match="uid"):
        dated(**a_class(uid=value))


def test_uid_builds_it() -> None:
    assert uid("study", "session", 42) == "study:session:42"
    with pytest.raises(BadDated):
        uid("study", "session", "4 2")


@pytest.mark.parametrize(
    "href",
    [
        "https://arga.example/study/sessions/42",
        "/planner/items/9",
        "study/sessions/42",
        "//evil/study",
        "/aulario/x",
        "/study/ses sions",
    ],
)
def test_href_goes_back_to_the_same_app(href: str) -> None:
    with pytest.raises(BadDated, match="href"):
        dated(**a_class(href=href))


@pytest.mark.parametrize(
    "href", ["/study", "/study/", "/study/sessions/42?tab=notes", "/study#hoy"]
)
def test_href_may_be_the_app_itself_or_carry_a_query(href: str) -> None:
    assert dated(**a_class(href=href))["href"] == href


def test_removing_is_publishing_it_cancelled() -> None:
    assert dated(**a_class(status="cancelled"))["status"] == "cancelled"
    with pytest.raises(BadDated, match="status"):
        dated(**a_class(status="deleted"))


def test_a_field_of_its_own_does_not_go_inside() -> None:
    with pytest.raises(BadDated, match="course_id"):
        dated(**a_class(course_id=7))


def test_missing_fields_are_named() -> None:
    fields = a_class()
    del fields["href"], fields["tz"]
    with pytest.raises(BadDated) as error:
        validate(fields)

    assert "href" in str(error.value)
    assert "tz" in str(error.value)


def test_a_blank_title_is_rejected() -> None:
    with pytest.raises(BadDated, match="title"):
        dated(**a_class(title="   "))


def test_an_event_payload_carries_it_under_its_key() -> None:
    payload = {KEY: dated(**a_class()), "course_id": 7}

    assert check_event(payload)["uid"] == "study:session:42"
    with pytest.raises(BadDated, match="agenda"):
        check_event({"course_id": 7})
    with pytest.raises(BadDated):
        check_event({KEY: {**payload[KEY], "end": "2026-10-06T17:00:00+02:00"}})
