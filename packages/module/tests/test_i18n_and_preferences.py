import json

from fastapi import Request
from httpx import ASGITransport, AsyncClient

from arga_module import i18n, preferences


def test_server_texts_fall_back_to_english_and_then_to_the_key(tmp_path) -> None:
    (tmp_path / "en.json").write_text(json.dumps({"due": "Due {when}", "only": "Only here"}))
    (tmp_path / "es.json").write_text(json.dumps({"due": "Vence {when}"}))

    assert i18n.t(tmp_path, "due", "es", when="today") == "Vence today"
    assert i18n.t(tmp_path, "only", "es") == "Only here"
    assert i18n.t(tmp_path, "nope", "es") == "nope"
    assert i18n.missing(tmp_path) == [("es", "only")]


def test_preferences_come_from_headers_over_instance_defaults(monkeypatch) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("OPENARGA_CURRENCY", "EUR")

    chosen = preferences.from_headers(
        {"x-arga-locale": "es", "x-arga-timezone": "America/New_York", "x-arga-currency": "USD"}
    )
    assert (chosen.locale, chosen.timezone, chosen.currency) == ("es", "America/New_York", "USD")

    ignored = preferences.from_headers({"x-arga-locale": "de", "x-arga-timezone": "Mars/Base"})
    assert (ignored.locale, ignored.timezone) == ("en", "Europe/Madrid")


async def test_a_request_sees_its_own_preferences() -> None:
    from arga_module.service import Service

    service = Service("probe", title="probe", ui=False)

    @service.app.get("/locale")
    async def locale(request: Request) -> dict:
        return {"locale": preferences.current().locale}

    async with AsyncClient(transport=ASGITransport(app=service.app), base_url="http://probe") as c:
        spanish = await c.get("/locale", headers={"x-arga-locale": "es"})
        plain = await c.get("/locale")

    assert spanish.json() == {"locale": "es"}
    assert plain.json() == {"locale": "en"}
