from __future__ import annotations

from travel.main import TRIP_APP, trip_app_page

INDEX = """<head>
    <title>Travel</title>
    <link rel="manifest" href="/travel/manifest.webmanifest?v=65b603fcb5" />
    <link rel="apple-touch-icon" href="/travel/apple-touch-icon.png" sizes="180x180" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
</head>"""


def test_the_trip_page_has_no_manifest() -> None:
    page = trip_app_page(INDEX)
    assert "manifest" not in page
    assert 'rel="apple-touch-icon"' in page
    assert 'name="apple-mobile-web-app-capable"' in page


def test_only_the_trip_app_address_loses_it() -> None:
    trip = "viaje/3abfed4f-8cde-44ad-b81a-d0039f5a2ba6"
    assert TRIP_APP.fullmatch(trip)
    assert TRIP_APP.fullmatch(trip + "/")
    assert not TRIP_APP.fullmatch("viajes/3abfed4f-8cde-44ad-b81a-d0039f5a2ba6")
    assert not TRIP_APP.fullmatch("")
