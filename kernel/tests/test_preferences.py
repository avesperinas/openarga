from httpx import ASGITransport, AsyncClient


async def test_preferences_start_from_the_instance_defaults(monkeypatch) -> None:
    from kernel.main import app

    monkeypatch.setenv("OPENARGA_LOCALE", "es")
    monkeypatch.setenv("OPENARGA_TIMEZONE", "Europe/Madrid")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        found = (await client.get("/me/preferences")).json()

    assert found["locale"] == "es"
    assert found["timezone"] == "Europe/Madrid"
    assert set(found) == {"locale", "timezone", "currency", "country", "region", "area"}
