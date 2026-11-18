from __future__ import annotations

import base64
import re
from datetime import date, timedelta
from functools import cache
from typing import Any

import httpx

from hub.fakes import world
from hub.fakes.bank import FakeEnableBanking
from hub.fakes.google import FakeGoogle
from hub.fakes.markets import markets

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
FOODS = [
    ("8400000000017", "Example oat drink", "Sample Brand", 46, 1.0, 1.5, 6.6, 1000, 250),
    ("8400000000024", "Example natural yoghurt", "Sample Brand", 61, 3.5, 3.2, 4.7, 500, 125),
    ("8400000000031", "Example wholemeal bread", "Sample Bakery", 247, 13.0, 3.4, 41.0, 600, 40),
]
PODCASTS = [("Example Science Hour", "Sample Network", 120), ("The Sample Show", "Example FM", 48)]
PLACES = [
    ("Example Town", 42.8125, -1.6458, "ES", "ES-NC", "city"),
    ("Sample Village", 42.95, -1.45, "ES", "ES-NC", "village"),
]


def json(body: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


def nominatim(request: httpx.Request) -> httpx.Response:
    wanted = (request.url.params.get("q") or "").casefold()
    found = [one for one in PLACES if wanted in one[0].casefold()] or PLACES[:1]
    return json(
        [
            {
                "osm_id": 1000 + index,
                "osm_type": "relation",
                "lat": str(lat),
                "lon": str(lon),
                "name": name,
                "display_name": f"{name}, Example Region, Example Country",
                "addresstype": kind,
                "address": {
                    "city": name,
                    "country": "Example Country",
                    "country_code": country.lower(),
                    "ISO3166-2-lvl4": region,
                },
            }
            for index, (name, lat, lon, country, region, kind) in enumerate(found)
        ]
    )


def osrm(request: httpx.Request) -> httpx.Response:
    points = request.url.path.rsplit("/", 1)[-1].split(";")
    coordinates = [[float(x) for x in one.split(",")[:2]] for one in points]
    legs = [{"distance": 12000.0, "duration": 900.0} for _ in coordinates[1:]]
    return json(
        {
            "code": "Ok",
            "routes": [
                {
                    "distance": sum(leg["distance"] for leg in legs),
                    "duration": sum(leg["duration"] for leg in legs),
                    "legs": legs,
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                }
            ],
        }
    )


def overpass(request: httpx.Request) -> httpx.Response:
    query = request.content.decode()
    around = re.search(r"around:\d+,(-?[\d.]+),(-?[\d.]+)", query)
    lat, lon = (float(around.group(1)), float(around.group(2))) if around else (42.81, -1.64)
    names = ["Example Cafe", "Sample Bistro", "Example Museum"]
    return json(
        {
            "elements": [
                {
                    "type": "node",
                    "id": 5000 + index,
                    "lat": lat + 0.001 * (index + 1),
                    "lon": lon + 0.001 * (index + 1),
                    "tags": {
                        "name": name,
                        "amenity": "restaurant",
                        "opening_hours": "Mo-Su 09:00-22:00",
                    },
                }
                for index, name in enumerate(names)
            ]
        }
    )


def open_meteo(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    first, last = params.get("start_date"), params.get("end_date")
    start = date.fromisoformat(first) if first else world.today()
    count = int(params.get("forecast_days") or 7)
    end = date.fromisoformat(last) if last else start + timedelta(days=count - 1)
    days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    swing = [(d.toordinal() % 7) - 3 for d in days]
    return json(
        {
            "timezone": params.get("timezone") or "UTC",
            "daily": {
                "time": [d.isoformat() for d in days],
                "weather_code": [(0, 1, 2, 3, 61, 2, 1)[d.toordinal() % 7] for d in days],
                "temperature_2m_max": [18.0 + s for s in swing],
                "temperature_2m_min": [8.0 + s for s in swing],
                "precipitation_probability_max": [(d.toordinal() * 13) % 80 for d in days],
                "precipitation_sum": [((d.toordinal() * 7) % 5) * 0.8 for d in days],
            },
        }
    )


def openlibrary(request: httpx.Request) -> httpx.Response:
    if request.url.host == "covers.openlibrary.org":
        return httpx.Response(200, content=PNG * 40, headers={"content-type": "image/png"})
    return json(
        {
            "docs": [
                {
                    "key": "/works/OL1W",
                    "title": "An Example Novel",
                    "author_name": ["Sample Author"],
                    "first_publish_year": 2001,
                    "number_of_pages_median": 320,
                    "cover_i": 1,
                    "subject": ["Fiction"],
                    "editions": {
                        "docs": [
                            {
                                "key": "/books/OL1M",
                                "title": "An Example Novel",
                                "isbn": ["9780000000002"],
                                "language": ["eng"],
                                "publish_year": [2001],
                                "cover_i": 1,
                            }
                        ]
                    },
                }
            ]
        }
    )


def google_books(_request: httpx.Request) -> httpx.Response:
    return json({"items": []})


def product(food: tuple) -> dict[str, Any]:
    code, name, brand, kcal, protein, fat, carbs, package, serving = food
    return {
        "code": code,
        "product_name": name,
        "brands": [brand],
        "categories": "Example",
        "nutriments": {
            "energy-kcal_100g": kcal,
            "proteins_100g": protein,
            "fat_100g": fat,
            "carbohydrates_100g": carbs,
        },
        "product_quantity": package,
        "product_quantity_unit": "g",
        "serving_quantity": serving,
        "serving_quantity_unit": "g",
    }


def openfoodfacts(request: httpx.Request) -> httpx.Response:
    if request.url.host == "search.openfoodfacts.org":
        wanted = (request.url.params.get("q") or "").casefold()
        found = [f for f in FOODS if any(w in f[1].casefold() for w in wanted.split())] or FOODS
        return json({"hits": [product(one) for one in found]})
    code = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
    known = next((one for one in FOODS if one[0] == code), None)
    return json({"product": product(known)} if known else {"status": 0}, 200 if known else 404)


def usda(request: httpx.Request) -> httpx.Response:
    foods = [
        {
            "fdcId": 100 + index,
            "description": name.removeprefix("Example ").capitalize(),
            "foodCategory": "Example",
            "foodNutrients": [
                {"nutrientId": 1008, "value": kcal},
                {"nutrientId": 1003, "value": protein},
                {"nutrientId": 1004, "value": fat},
                {"nutrientId": 1005, "value": carbs},
            ],
        }
        for index, (_, name, _, kcal, protein, fat, carbs, _, _) in enumerate(FOODS)
    ]
    if request.url.path.endswith("/search"):
        return json({"foods": foods})
    return json(foods)


def wikidata(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    action = params.get("action")
    if action == "wbsearchentities":
        return json({"search": [{"id": "Q900001"}]})
    if action == "wbgetclaims":
        return json(
            {"claims": {"P18": [{"mainsnak": {"datavalue": {"value": "Example view.png"}}}]}}
        )
    if action == "wbgetentities":
        entities = {}
        for ident in (params.get("ids") or "").split("|"):
            if ident == "Q900001":
                entities[ident] = {
                    "id": ident,
                    "labels": {"en": {"value": "An Example Film"}},
                    "sitelinks": {"enwiki": {"title": "An Example Film"}},
                    "claims": {
                        "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
                        "P577": [
                            {
                                "mainsnak": {
                                    "datavalue": {"value": {"time": "+2004-05-01T00:00:00Z"}}
                                }
                            }
                        ],
                        "P57": [{"mainsnak": {"datavalue": {"value": {"id": "Q900002"}}}}],
                        "P2047": [{"mainsnak": {"datavalue": {"value": {"amount": "+104"}}}}],
                    },
                }
            elif ident:
                entities[ident] = {"id": ident, "labels": {"en": {"value": "Sample Director"}}}
        return json({"entities": entities})
    return json({"query": {"search": []}})


def commons(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    if params.get("prop") == "imageinfo":
        title = params.get("titles") or "File:Example view.png"
        return json(
            {
                "query": {
                    "pages": {
                        "1": {
                            "title": title,
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/example/view.png",
                                    "extmetadata": {
                                        "Artist": {"value": "Sample Photographer"},
                                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    },
                                }
                            ],
                        }
                    }
                }
            }
        )
    hit = {"title": "File:Example view.png"}
    return json({"query": {"search": [hit], "geosearch": [hit]}})


def upload(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})


def osm(_request: httpx.Request) -> httpx.Response:
    return json({"elements": [{"tags": {"wikidata": "Q900003"}}]})


def itunes(request: httpx.Request) -> httpx.Response:
    episode = request.url.params.get("entity") == "podcastEpisode"
    return json(
        {
            "results": [
                {
                    "collectionId": 700 + index,
                    "trackId": 800 + index,
                    "collectionName": name,
                    "trackName": f"{name}: episode 1" if episode else name,
                    "artistName": artist,
                    "trackCount": count,
                    "releaseDate": "2024-03-01T00:00:00Z",
                    "trackTimeMillis": 1_800_000 if episode else None,
                    "collectionViewUrl": f"https://podcasts.example.org/{700 + index}",
                    "trackViewUrl": f"https://podcasts.example.org/{800 + index}",
                }
                for index, (name, artist, count) in enumerate(PODCASTS)
            ]
        }
    )


def github(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.method == "GET" and "/git/ref/heads/" in path:
        return json({"object": {"sha": "0" * 40}})
    if request.method == "GET" and "/git/commits/" in path:
        return json({"sha": "0" * 40, "tree": {"sha": "1" * 40}})
    if path.endswith("/git/blobs"):
        return json({"sha": "2" * 40}, 201)
    if path.endswith("/git/trees"):
        return json({"sha": "3" * 40}, 201)
    if path.endswith("/git/commits"):
        return json({"sha": "4" * 40, "html_url": "https://github.com/example/notes"}, 201)
    if "/git/refs/heads/" in path:
        return json({"object": {"sha": "4" * 40}})
    if path.endswith("/contents/README.md"):
        return json({"commit": {"sha": "5" * 40}}, 201)
    return json(
        {"full_name": "example/notes", "permissions": {"push": True}, "default_branch": "main"}
    )


def agenda_page(_request: httpx.Request) -> httpx.Response:
    day = world.today()
    rows = "".join(
        f"<li><a href='/event/{n}'>Example concert {n}</a> Main hall | "
        f"{(day + timedelta(days=3 * n)).isoformat()} | 20:00</li>"
        for n in range(1, 5)
    )
    return httpx.Response(
        200,
        text=f"<html><head><title>Example agenda</title></head><body><ul>{rows}</ul></body></html>",
        headers={"content-type": "text/html"},
    )


def brave(_request: httpx.Request) -> httpx.Response:
    return json(
        {
            "web": {
                "results": [
                    {
                        "title": "Example result",
                        "url": "https://example.org/",
                        "description": "A sample page.",
                    }
                ]
            }
        }
    )


@cache
def stateful() -> dict[str, Any]:
    return {"bank": FakeEnableBanking(), "google": FakeGoogle(), "markets": markets()}


def answer_for(request: httpx.Request) -> world.Answer | None:
    host = request.url.host
    shared = stateful()
    table: dict[str, world.Answer] = {
        **{one: answer for one, _, answer in world.ROUTES},
        "api.enablebanking.com": shared["bank"],
        "oauth2.googleapis.com": shared["google"],
        "health.googleapis.com": shared["google"],
        "www.googleapis.com": google_books
        if request.url.path.startswith("/books")
        else shared["google"],
        "accounts.google.com": shared["google"],
        "api.onvista.de": shared["markets"],
        "api.openfigi.com": shared["markets"],
        "nominatim.openstreetmap.org": nominatim,
        "routing.openstreetmap.de": osrm,
        "overpass-api.de": overpass,
        "api.open-meteo.com": open_meteo,
        "archive-api.open-meteo.com": open_meteo,
        "openlibrary.org": openlibrary,
        "covers.openlibrary.org": openlibrary,
        "search.openfoodfacts.org": openfoodfacts,
        "world.openfoodfacts.org": openfoodfacts,
        "api.nal.usda.gov": usda,
        "www.wikidata.org": wikidata,
        "commons.wikimedia.org": commons,
        "upload.wikimedia.org": upload,
        "www.openstreetmap.org": osm,
        "itunes.apple.com": itunes,
        "api.github.com": github,
        "api.search.brave.com": brave,
    }
    if host in table:
        return table[host]
    if world.ICAL.search(str(request.url)):
        return world.ical
    if host.endswith(".example.org") or host.endswith(".example.com"):
        return agenda_page
    return None
