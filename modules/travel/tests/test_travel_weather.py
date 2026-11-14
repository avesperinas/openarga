from __future__ import annotations

from travel_kit import place

READ = {"x-arga-scopes": "travel:read"}
KYOTO = {"name": "Kioto", "lat": 35.0116, "lon": 135.7681, "osm_type": "relation", "osm_id": 42}


async def test_claude_asks_the_forecast_and_the_climate_of_a_place(api, hub) -> None:
    kyoto = await place(api, KYOTO)

    forecast = await api.post("/tools/get_weather", json={"place_id": kyoto["id"]}, headers=READ)
    climate = await api.post(
        "/tools/get_weather", json={"place_id": kyoto["id"], "kind": "climate"}, headers=READ
    )

    told = forecast.json()["content"]
    assert (told["place"], told["failed"]) == ("Kioto", None)
    first = told["weather"]["days"][0]
    assert first["code"] == 2 and first["sky"]
    [november] = climate.json()["content"]["weather"]["months"]
    assert (november["month"], november["max_c"]) == (11, 17.0)


async def test_the_app_asks_by_a_point(api, hub) -> None:
    answer = await api.get("/weather/forecast", params={"lat": 35.01, "lon": 135.77})

    assert answer.status_code == 200, answer.text
    assert answer.json()["weather"]["timezone"] == "Asia/Tokyo"
