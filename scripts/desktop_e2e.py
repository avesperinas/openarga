from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from playwright.sync_api import sync_playwright

URL = os.environ["E2E_URL"]
COOKIE_NAME = os.environ["E2E_COOKIE_NAME"]
COOKIE = os.environ["E2E_COOKIE"].strip()
OUT = Path(os.environ["E2E_OUT"])
TZ = "Europe/Madrid"
SESSION = {"cookie": f"{COOKIE_NAME}={COOKIE}"}


def fail(message: str) -> None:
    print(f"FALLA: {message}", file=sys.stderr)
    sys.exit(1)


def api() -> httpx.Client:
    return httpx.Client(
        base_url=URL,
        cookies={COOKIE_NAME: COOKIE},
        headers={"accept": "application/json"},
        timeout=20,
    )


def seed(client: httpx.Client) -> str:
    today = date.today()
    categories = client.get("/api/goals/categories")
    if categories.status_code != 200:
        fail(f"goals por el gateway: {categories.status_code} {categories.text[:200]}")
    by_name = {one["name"]: one["id"] for one in categories.json()}
    home = by_name.get("Casa") or next(iter(by_name.values()))
    work = by_name.get("Trabajo") or home
    tasks = [
        (work, "Enviar la factura del taller", today - timedelta(days=2), None),
        (home, "Llamar al fontanero", today, "18:00"),
        (home, "Regar las plantas", today, None),
        (home, "Renovar el seguro", today + timedelta(days=3), None),
    ]
    first = None
    for category, title, due, at in tasks:
        created = client.post(
            "/api/goals/tasks",
            json={"category_id": category, "title": title, "due_on": str(due), "due_time": at},
        )
        if created.status_code != 201:
            fail(f"crear tarea: {created.status_code} {created.text[:200]}")
        first = first or created.json()["id"]

    calendars = client.get("/api/planner/calendars")
    if calendars.status_code != 200:
        fail(f"planner por el gateway: {calendars.status_code}")
    now = datetime.now()
    events = [
        (0, now.hour + 1, 1, "Dentista"),
        (0, min(now.hour + 3, 21), 1, "Pádel"),
        (1, 9, 1, "Reunión de equipo"),
        (2, 13, 1, "Comida con amigos"),
        (4, 19, 2, "Cine"),
    ]
    for days, hour, length, title in events:
        start = datetime.combine(
            today + timedelta(days=days), datetime.min.time(), ZoneInfo(TZ)
        ).replace(hour=max(0, min(hour, 22)))
        created = client.post(
            "/api/planner/events",
            json={
                "title": title,
                "start": start.isoformat(),
                "end": (start + timedelta(hours=length)).isoformat(),
                "tz": TZ,
            },
        )
        if created.status_code != 201:
            fail(f"crear evento: {created.status_code} {created.text[:200]}")

    added = client.post(
        "/api/shopping/list/items",
        json={"items": [{"name": "Leche", "quantity": "2"}, {"name": "Pan"}, {"name": "Tomates"}]},
    )
    if added.status_code != 201:
        fail(f"la compra: {added.status_code} {added.text[:200]}")
    assert first is not None
    return first


def shoot(browser, name: str, **context) -> None:
    page = browser.new_context(extra_http_headers=SESSION, **context)
    tab = page.new_page()
    tab.goto(URL + "/", wait_until="networkidle")
    tab.wait_for_timeout(1500)
    tab.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    titles = tab.locator(".widget-title").all_inner_texts()
    print(f"  {name}: {len(titles)} tarjetas · {', '.join(titles[:8])}")
    if "Para hoy" not in titles:
        fail(f"{name}: el escritorio de partida no trae Para hoy")
    page.close()


def tick(browser, client: httpx.Client, task_id: str) -> None:
    page = browser.new_context(extra_http_headers=SESSION, viewport={"width": 1440, "height": 900})
    tab = page.new_page()
    tab.goto(URL + "/", wait_until="networkidle")
    card = tab.locator(".widget", has=tab.locator(".widget-title", has_text="Para hoy")).first
    box = card.locator("button.task-check", has_text="").first
    label = box.get_attribute("aria-label")
    with tab.expect_response(lambda r: r.url.endswith("/widgets/today/act")) as answered:
        box.click()
    if answered.value.status != 200:
        fail(f"tachar: {answered.value.status}")
    tab.wait_for_timeout(800)
    tab.screenshot(path=str(OUT / "tachada.png"))
    if "/goals" in tab.url:
        fail("el clic abrió la app en vez de tachar")
    print(f"  tachada desde la tarjeta: {label}")
    done = client.get("/api/goals/tasks", params={"state": "done"}).json()
    if not done:
        fail("Goals no da ninguna tarea por hecha")
    print(f"  Goals la da por hecha: {done[0]['title']}")
    page.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with api() as client:
        task_id = seed(client)
        print("  sembrado: 4 tareas, 5 eventos, 3 cosas en la compra")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            iphone = p.devices["iPhone 13"]
            shoot(browser, "movil", **iphone)
            shoot(browser, "tablet", viewport={"width": 820, "height": 1180}, has_touch=True)
            shoot(browser, "ordenador", viewport={"width": 1440, "height": 900})
            tick(browser, client, task_id)
            browser.close()


if __name__ == "__main__":
    main()
