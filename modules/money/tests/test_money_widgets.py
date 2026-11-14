from __future__ import annotations

from pathlib import Path

import yaml

from arga_widgets import validate

MANIFEST = yaml.safe_load((Path(__file__).resolve().parents[1] / "manifest.yaml").read_text())
WIDGETS = MANIFEST["ui"]["widgets"]


def test_the_widgets_are_the_summary_and_a_balance() -> None:
    assert {w["id"]: w["kind"] for w in WIDGETS} == {
        "networth": "kpi-delta",
        "liquid": "kpi-delta",
        "cash": "kpi",
        "emergency": "progress",
        "expense": "kpi-delta",
        "basic": "kpi-delta",
        "shared": "kpi",
        "account": "kpi",
    }
    assert all(w["endpoint"].startswith("/api/money/widgets/") for w in WIDGETS)
    assert all(w["link"].startswith("/money") for w in WIDGETS)
    account = next(w for w in WIDGETS if w["id"] == "account")
    assert account["option"] == {
        "label": "Account",
        "endpoint": "/api/money/widgets/account/options",
    }


async def test_every_widget_is_served_with_the_body_of_its_kind(api) -> None:
    for widget in WIDGETS:
        path = widget["endpoint"].removeprefix("/api/money")
        response = await api.get(path)
        assert response.status_code == 200, (widget["id"], response.text)
        sealed = response.json()
        validate(widget["kind"], sealed["body"], sealed["state"])
    options = await api.get("/widgets/account/options")
    assert options.status_code == 200 and options.json() == []


async def test_the_app_lives_at_money_and_the_old_address_moves_there(api) -> None:
    moved = await api.get("/money/v1/compartido", follow_redirects=False)
    assert moved.status_code == 308 and moved.headers["location"] == "/money/compartido"
