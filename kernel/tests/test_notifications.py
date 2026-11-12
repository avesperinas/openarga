import json
from datetime import UTC, datetime, time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_tenancy import USER_HEADER, as_user
from kernel import notifications
from kernel.db import engine
from kernel.main import app

APP = "probe_avisa"
MUTE = "probe_calla"
SUBJECTS = ("5b0c7a52-1d2e-4b8a-9c61-7e5d4a3b2c10", "6a1e6d4c-2b3f-4c5d-8e7f-0a1b2c3d4e5f")
MANIFEST = {
    "name": "Avisa",
    "uses": ["notify.schedule", "notify.cancel", "notify.sync"],
    "notifications": [
        {"kind": "due", "label": "Algo que vence", "default": True},
        {"kind": "nudge", "label": "Un empujón", "default": False},
    ],
}
REGISTER = text("""
    insert into kernel.modules (id, version, enabled, manifest)
    values (:id, '0.1.0', true, cast(:manifest as jsonb))
    on conflict (id) do update set manifest = excluded.manifest, enabled = true
""")
TABLES = ("notification", "push_subscription", "notification_pref")


async def clean() -> None:
    async with engine().begin() as connection:
        for table in TABLES:
            await connection.execute(text(f"delete from kernel.{table}"))
        await connection.execute(
            text("delete from kernel.modules where id in (:a, :b)"), {"a": APP, "b": MUTE}
        )
        await connection.execute(
            text("delete from kernel.users where subject = any(:s)"), {"s": list(SUBJECTS)}
        )


@pytest.fixture
async def kernel(database_url: str, monkeypatch):
    monkeypatch.setenv("ARGA_VAPID_SEED", "semilla-sintetica")
    monkeypatch.setenv("ARGA_VAPID_SUBJECT", "https://arga.ejemplo.com")
    await clean()
    async with engine().begin() as connection:
        await connection.execute(REGISTER, {"id": APP, "manifest": json.dumps(MANIFEST)})
        await connection.execute(REGISTER, {"id": MUTE, "manifest": json.dumps({"name": "Calla"})})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await clean()
    await engine().dispose()


@pytest.fixture
async def people(kernel) -> list[dict[str, str]]:
    found = []
    for subject in SUBJECTS:
        person = (await kernel.post("/internal/users", json={"subject": subject})).json()
        found.append({USER_HEADER: person["id"]})
    return found


class Pushed(list):
    def __init__(self) -> None:
        super().__init__()
        self.refuse: dict[str, int | None] = {}


@pytest.fixture
def pushed(monkeypatch) -> Pushed:
    sent = Pushed()

    def push(subscription, message, _keys):
        if subscription.endpoint not in sent.refuse:
            sent.append((subscription.endpoint, message))
            return None
        status = sent.refuse[subscription.endpoint]
        return notifications.Refused(status, "BadJwtToken" if status == 403 else "")

    monkeypatch.setattr(notifications, "_push", push)
    return sent


def device(n: int) -> dict:
    return {
        "endpoint": f"https://push.ejemplo.com/{n}",
        "keys": {"p256dh": f"clave-{n}", "auth": f"auth-{n}"},
        "name": f"Dispositivo {n}",
    }


async def ask(kernel, who, capability: str, body: dict, module: str = APP):
    return await kernel.post(
        f"/internal/capabilities/{capability}",
        json=body,
        headers={"x-arga-module": module, **who},
    )


def due(key: str = "seguro", at: str = "2026-10-06T07:00:00+00:00", kind: str = "due") -> dict:
    return {"kind": kind, "key": key, "title": "Vence el seguro", "href": "/arca/1", "at": at}


async def send(now: str) -> dict:
    return await notifications.send_once(datetime.fromisoformat(now))


async def test_a_scheduled_notification_reaches_every_device_of_its_person_once(
    kernel, people, pushed
) -> None:
    ana, luis = people
    for n in (1, 2):
        assert (
            await kernel.post("/notifications/devices", json=device(n), headers=ana)
        ).status_code == 201
    await kernel.post("/notifications/devices", json=device(3), headers=luis)
    assert (await ask(kernel, ana, "notify.schedule", due())).status_code == 200

    assert await send("2026-10-06T06:59:00+00:00") == {
        "sent": 0,
        "skipped": 0,
        "waiting": 0,
        "retrying": 0,
    }
    assert (await send("2026-10-06T07:00:00+00:00"))["sent"] == 1
    assert sorted(endpoint for endpoint, _ in pushed) == [
        "https://push.ejemplo.com/1",
        "https://push.ejemplo.com/2",
    ]
    assert pushed[0][1] == {"title": "Vence el seguro", "body": "", "href": "/arca/1"}
    assert (await send("2026-10-06T08:00:00+00:00"))["sent"] == 0


async def test_the_same_key_moves_it_and_cancel_takes_it_away(kernel, people, pushed) -> None:
    ana, _ = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    await ask(kernel, ana, "notify.schedule", due())
    await ask(kernel, ana, "notify.schedule", due(at="2026-10-07T07:00:00+00:00"))
    assert (await send("2026-10-06T07:00:00+00:00"))["sent"] == 0

    cancelled = await ask(kernel, ana, "notify.cancel", {"key": "seguro"})
    assert cancelled.json() == {"cancelled": 1}
    assert (await send("2026-10-08T07:00:00+00:00"))["sent"] == 0 and pushed == []


async def test_only_what_the_app_declares_and_uses(kernel, people) -> None:
    ana, _ = people
    assert (await ask(kernel, ana, "notify.schedule", due(kind="otro"))).status_code == 422
    assert (await ask(kernel, ana, "notify.schedule", due(), module=MUTE)).status_code == 403


async def test_what_is_off_does_not_go_and_quiet_hours_wait(kernel, people, pushed) -> None:
    ana, _ = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    await ask(kernel, ana, "notify.schedule", due("off", kind="nudge"))
    await ask(kernel, ana, "notify.schedule", due("night", at="2026-10-06T21:30:00+00:00"))

    found = await send("2026-10-06T21:30:00+00:00")
    assert found == {"sent": 0, "skipped": 1, "waiting": 1, "retrying": 0}
    assert (await send("2026-10-07T06:00:00+00:00"))["sent"] == 1

    await kernel.put(
        "/notifications/prefs", json={"app": APP, "kind": "nudge", "enabled": True}, headers=ana
    )
    await ask(
        kernel, ana, "notify.schedule", due("on", kind="nudge", at="2026-10-07T10:00:00+00:00")
    )
    assert (await send("2026-10-07T10:00:00+00:00"))["sent"] == 1


async def test_a_dead_device_is_forgotten(kernel, people, pushed) -> None:
    ana, _ = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    pushed.refuse["https://push.ejemplo.com/1"] = 410
    await ask(kernel, ana, "notify.schedule", due())
    await send("2026-10-06T07:00:00+00:00")
    settings = (await kernel.get("/notifications", headers=ana)).json()
    assert settings["devices"] == []


async def test_settings_say_what_there_is_and_only_yours(kernel, people) -> None:
    ana, luis = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    mine = (await kernel.get("/notifications", headers=ana)).json()
    theirs = (await kernel.get("/notifications", headers=luis)).json()

    assert mine["configured"]
    assert len(mine["public_key"]) == 87 and mine["public_key"].startswith("B")
    assert [one["name"] for one in mine["devices"]] == ["Dispositivo 1"]
    assert theirs["devices"] == []
    kinds = {(one["app"], one["kind"]): one["enabled"] for one in mine["kinds"]}
    assert kinds == {(APP, "due"): True, (APP, "nudge"): False}
    assert (mine["quiet_from"], mine["quiet_to"]) == ("23:00:00", "08:00:00")

    await kernel.put(
        "/notifications/quiet", json={"quiet_from": None, "quiet_to": None}, headers=ana
    )
    assert (await kernel.get("/notifications", headers=ana)).json()["quiet_from"] is None


def test_quiet_hours_cross_midnight() -> None:
    late = datetime(2026, 10, 6, 22, 30, tzinfo=UTC)
    assert notifications.quiet_until(late, time(23), time(8)) == datetime(
        2026, 10, 7, 6, 0, tzinfo=UTC
    )
    noon = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
    assert notifications.quiet_until(noon, time(23), time(8)) is None


async def test_without_the_key_nothing_is_sent(kernel, people, pushed, monkeypatch) -> None:
    monkeypatch.delenv("ARGA_VAPID_SEED")
    ana, _ = people
    assert (await kernel.post("/notifications/test", headers=ana)).status_code == 503
    assert (await kernel.get("/notifications", headers=ana)).json()["configured"] is False


async def test_the_rows_are_separated_by_postgres(kernel, people) -> None:
    ana, luis = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    from uuid import UUID

    like = "kernel_como_en_produccion"
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "do $$ begin if not exists (select 1 from pg_roles where rolname = "
                f"'{like}') then create role {like} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {like}"))
        await connection.execute(text(f"grant select on kernel.push_subscription to {like}"))
    with as_user(UUID(luis[USER_HEADER])):
        async with engine().begin() as connection:
            await connection.execute(text(f"set local role {like}"))
            seen = await connection.scalar(text("select count(*) from kernel.push_subscription"))
    assert seen == 0


def test_the_same_seed_is_the_same_key_and_signs() -> None:
    signer, public = notifications.keypair("semilla-sintetica")
    again, same = notifications.keypair("semilla-sintetica")
    assert public == same
    assert notifications.keypair("otra")[1] != public
    headers = signer.sign({"aud": "https://push.ejemplo.com", "sub": "https://arga.ejemplo.com"})
    assert headers["Authorization"].startswith("vapid t=")


async def test_sync_schedules_the_new_moves_the_changed_and_drops_what_is_gone(
    kernel, people, pushed
) -> None:
    ana, _ = people
    soon = "2099-10-06T07:00:00+00:00"
    items = [due("a", at=soon), due("b", at=soon)]
    first = await ask(kernel, ana, "notify.sync", {"items": items})
    assert first.json() == {"scheduled": 2, "cancelled": 0, "stale": 0}

    later = due("a", at="2099-10-08T07:00:00+00:00")
    again = await ask(kernel, ana, "notify.sync", {"items": [later]})
    assert again.json() == {"scheduled": 1, "cancelled": 1, "stale": 0}
    async with engine().begin() as connection:
        rows = (
            await connection.execute(
                text("select key, due_at from kernel.notification order by key")
            )
        ).all()
    assert [(row.key, row.due_at.isoformat()) for row in rows] == [
        ("a", "2099-10-08T07:00:00+00:00")
    ]


async def test_sync_does_not_bring_back_what_passed_long_ago(kernel, people) -> None:
    ana, _ = people
    old = due("old", at="2020-01-01T07:00:00+00:00")
    found = await ask(kernel, ana, "notify.sync", {"items": [old]})
    assert found.json()["stale"] == 1


async def outcome_of(key: str) -> tuple[str | None, bool, int]:
    async with engine().begin() as connection:
        row = (
            await connection.execute(
                text("select outcome, sent_at, attempts from kernel.notification where key = :k"),
                {"k": key},
            )
        ).one()
    return row.outcome, row.sent_at is not None, row.attempts


async def test_quiet_hours_do_not_send_it_twice_when_the_app_says_it_again(
    kernel, people, pushed
) -> None:
    ana, _ = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    night = due("night", at="2099-10-06T21:30:00+00:00")
    await ask(kernel, ana, "notify.sync", {"items": [night]})
    assert (await send("2099-10-06T21:30:00+00:00"))["waiting"] == 1
    await ask(kernel, ana, "notify.sync", {"items": [night]})
    assert (await send("2099-10-07T06:00:00+00:00"))["sent"] == 1
    await ask(kernel, ana, "notify.sync", {"items": [night]})
    assert (await send("2099-10-07T06:01:00+00:00"))["sent"] == 0
    assert len(pushed) == 1


async def test_what_went_out_does_not_go_again_when_the_app_says_it_with_another_time(
    kernel, people, pushed
) -> None:
    ana, _ = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    await ask(kernel, ana, "notify.sync", {"items": [due("week", at="2099-10-06T07:00:00+00:00")]})
    assert (await send("2099-10-06T07:00:00+00:00"))["sent"] == 1
    for minute in ("05", "10"):
        later = due("week", at=f"2099-10-06T07:{minute}:00+00:00")
        await ask(kernel, ana, "notify.sync", {"items": [later]})
        assert (await send(f"2099-10-06T07:{minute}:00+00:00"))["sent"] == 0
    again = await ask(kernel, ana, "notify.schedule", due("week", at="2099-10-07T07:00:00+00:00"))
    assert again.json()["sent"] is True
    assert (await send("2099-10-07T07:00:00+00:00"))["sent"] == 0
    assert len(pushed) == 1


async def test_a_push_service_that_does_not_answer_is_tried_again_and_stops_no_one(
    kernel, people, pushed
) -> None:
    ana, luis = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    await kernel.post("/notifications/devices", json=device(2), headers=luis)
    pushed.refuse["https://push.ejemplo.com/1"] = None
    await ask(kernel, ana, "notify.schedule", due("de-ana"))
    await ask(kernel, luis, "notify.schedule", due("de-luis"))

    found = await send("2026-10-06T07:00:00+00:00")
    assert found["sent"] == 1 and found["retrying"] == 1
    assert [endpoint for endpoint, _ in pushed] == ["https://push.ejemplo.com/2"]
    why, gone, attempts = await outcome_of("de-ana")
    assert not gone and attempts == 1 and "sin respuesta" in why

    assert (await send("2026-10-06T07:04:00+00:00"))["retrying"] == 0
    del pushed.refuse["https://push.ejemplo.com/1"]
    assert (await send("2026-10-06T07:05:00+00:00"))["sent"] == 1
    why, gone, _ = await outcome_of("de-ana")
    assert gone and why == "enviado a 1 de 1"


async def test_what_keeps_failing_ends_and_says_why(kernel, people, pushed) -> None:
    ana, _ = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    pushed.refuse["https://push.ejemplo.com/1"] = 503
    await ask(kernel, ana, "notify.schedule", due())
    for minute in ("07:00", "07:05", "07:20", "08:00"):
        await send(f"2026-10-06T{minute}:00+00:00")
    why, gone, attempts = await outcome_of("seguro")
    assert gone and attempts == 3 and why.startswith("no salió tras 4 intentos")


async def test_a_refusal_is_not_retried_and_the_device_says_it(kernel, people, pushed) -> None:
    ana, _ = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    pushed.refuse["https://push.ejemplo.com/1"] = 403
    await ask(kernel, ana, "notify.schedule", due())
    found = await send("2026-10-06T07:00:00+00:00")
    assert found["sent"] == 1 and found["retrying"] == 0
    why, gone, _ = await outcome_of("seguro")
    assert gone and why == "enviado a 0 de 1; Dispositivo 1: 403 BadJwtToken"

    settings = (await kernel.get("/notifications", headers=ana)).json()
    assert settings["devices"][0]["last_error"] == "403 BadJwtToken"
    assert settings["devices"][0]["last_error_at"] is not None
    assert settings["recent"][0]["outcome"] == why


async def test_settings_count_what_is_late(kernel, people) -> None:
    ana, _ = people
    await ask(kernel, ana, "notify.schedule", due(at="2020-01-01T07:00:00+00:00"))
    settings = (await kernel.get("/notifications", headers=ana)).json()
    assert settings["late"] == 1


def test_each_push_has_a_time_limit_and_a_network_error_is_said(monkeypatch) -> None:
    import pywebpush
    import requests

    asked: dict = {}

    def hanging(**kwargs):
        asked.update(kwargs)
        raise requests.exceptions.ConnectTimeout("no contesta")

    monkeypatch.setattr(pywebpush, "webpush", hanging)

    class Subscription:
        endpoint, p256dh, auth = "https://push.ejemplo.com/1", "clave", "auth"

    keys = (notifications.keypair("semilla-sintetica")[0], "", "https://arga.ejemplo.com")
    refused = notifications._push(Subscription(), {"title": "t"}, keys)
    assert asked["timeout"] == notifications.PUSH_TIMEOUT
    assert refused == notifications.Refused(None, "ConnectTimeout") and refused.passing


def protein(missing: int, at: str = "2099-10-06T17:00:00+00:00") -> dict:
    return {
        "kind": "due",
        "key": "protein:2099-10-06",
        "title": f"Te faltan {missing} g de proteína",
        "body": f"Llevas {120 - missing} g de 120 g hoy.",
        "href": "/macros/",
        "at": at,
    }


async def test_the_text_of_what_went_out_is_what_stays_after_two_passes_the_same_day(
    kernel, people, pushed
) -> None:
    ana, _ = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    await ask(kernel, ana, "notify.sync", {"items": [protein(60)]})
    await ask(kernel, ana, "notify.sync", {"items": [protein(40)]})
    assert (await send("2099-10-06T17:00:00+00:00"))["sent"] == 1
    assert pushed[0][1]["title"] == "Te faltan 40 g de proteína"

    await ask(kernel, ana, "notify.sync", {"items": [protein(15)]})
    await ask(kernel, ana, "notify.sync", {"items": []})
    assert (await send("2099-10-06T18:00:00+00:00"))["sent"] == 0

    [notice] = (await kernel.get("/notifications/inbox", headers=ana)).json()
    assert (notice["title"], notice["body"]) == (
        "Te faltan 40 g de proteína",
        "Llevas 80 g de 120 g hoy.",
    )
    assert len(pushed) == 1


async def test_the_inbox_has_what_went_out_newest_first_and_only_yours(
    kernel, people, pushed
) -> None:
    ana, luis = people
    await kernel.post("/notifications/devices", json=device(1), headers=ana)
    await ask(kernel, ana, "notify.schedule", due("first", at="2026-10-06T07:00:00+00:00"))
    await send("2026-10-06T07:00:00+00:00")
    await ask(kernel, ana, "notify.schedule", due("second", at="2026-10-06T08:00:00+00:00"))
    await ask(kernel, ana, "notify.schedule", due("off", kind="nudge"))
    await ask(kernel, ana, "notify.schedule", due("later", at="2099-01-01T07:00:00+00:00"))
    await ask(kernel, luis, "notify.schedule", due("luis", at="2026-10-06T07:00:00+00:00"))
    await send("2026-10-06T08:00:00+00:00")

    mine = (await kernel.get("/notifications/inbox", headers=ana)).json()
    theirs = (await kernel.get("/notifications/inbox", headers=luis)).json()

    assert len(mine) == 2
    assert mine[0]["sent_at"] >= mine[1]["sent_at"]
    assert {n["app_name"] for n in mine} == {"Avisa"}
    assert all(n["href"] == "/arca/1" and n["read"] is False for n in mine)
    assert len(theirs) == 1


async def test_touching_a_notice_marks_it_read_and_only_yours(kernel, people, pushed) -> None:
    ana, luis = people
    await ask(kernel, ana, "notify.schedule", due())
    await send("2026-10-06T07:00:00+00:00")
    [notice] = (await kernel.get("/notifications/inbox", headers=ana)).json()
    read = f"/notifications/inbox/{notice['id']}/read"

    assert (await kernel.post(read, headers=luis)).status_code == 404
    assert (await kernel.post(read, headers=ana)).status_code == 204
    assert (await kernel.post(read, headers=ana)).status_code == 204
    [again] = (await kernel.get("/notifications/inbox", headers=ana)).json()
    assert again["read"] is True
