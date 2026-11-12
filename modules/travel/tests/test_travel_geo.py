from __future__ import annotations

import pytest

from travel import geo


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (51.2085, 3.2267, ("BE", "BE-VLG")),
        (37.389, -5.984, ("ES", "ES-AN")),
        (43.263, -2.935, ("ES", "ES-PV")),
        (45.76, 4.83, ("FR", "FR-ARA")),
        (55.95, -3.19, ("GB", "GB-SCT")),
        (38.12, 13.36, ("IT", "IT-82")),
        (48.14, 11.58, ("DE", "DE-BY")),
    ],
)
def test_a_point_falls_in_its_first_level_region(lat, lon, expected) -> None:
    assert geo.locate(lat, lon) == expected


def test_an_enclave_is_its_own_country() -> None:
    assert geo.locate(41.9029, 12.4534)[0] == "VA"
    assert geo.locate(43.9367, 12.4463)[0] == "SM"


def test_a_point_just_off_a_simplified_coast_is_still_on_land() -> None:
    assert geo.locate(42.6407, 18.1077)[0] == "HR"


def test_the_openstreetmap_hint_only_counts_when_the_map_knows_the_code() -> None:
    assert geo.locate(None, None, "be", "BE-VLG") == ("BE", "BE-VLG")
    assert geo.locate(None, None, "zz", "ZZ-1") == (None, None)
    assert geo.locate(None, None, "FR", "BE-VLG") == ("FR", None)


def test_europe_is_forty_four_countries_and_all_are_on_the_map() -> None:
    assert len(geo.EUROPE) == 44
    assert set(geo.names()) >= geo.EUROPE


def test_a_flight_goes_straight_and_a_car_does_not() -> None:
    madrid, seville = (40.4168, -3.7038), (37.389, -5.984)

    plane = geo.leg_km("plane", madrid, seville)
    car = geo.leg_km("car", madrid, seville)

    assert plane is not None and 385 < plane < 395
    assert car == round(plane * 1.25, 1) or abs(car - plane * 1.25) < 0.2
    assert geo.leg_km("car", madrid, (None, None)) is None
