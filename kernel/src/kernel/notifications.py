from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL, as_user, require_person
from kernel.db import engine
from kernel.manifests import NOTIFICATION_KIND_PATTERN

router = APIRouter(tags=["notifications"])

MADRID = ZoneInfo("Europe/Madrid")
QUIET_FROM, QUIET_TO = time(23, 0), time(8, 0)
SEND_EVERY = float(os.environ.get("NOTIFY_EVERY_SECONDS", "30"))
TTL_SECONDS = 24 * 3600
BATCH = 50
PUSH_TIMEOUT = 10.0
RETRY_MINUTES = (5, 15, 40)
PASSING = frozenset({408, 425, 429, 500, 502, 503, 504})
LATE = timedelta(hours=1)


P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


@lru_cache(maxsize=4)
def keypair(seed: str) -> tuple[Any, str]:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from py_vapid import Vapid02

    digest = hashlib.sha256(b"arga-vapid\n" + seed.encode()).digest()
    scalar = int.from_bytes(digest, "big") % (P256_ORDER - 1) + 1
    private = ec.derive_private_key(scalar, ec.SECP256R1())
    raw = private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return Vapid02(private_key=private), base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def vapid() -> tuple[Any, str, str] | None:
    seed = os.environ.get("ARGA_VAPID_SEED", "").strip()
    subject = os.environ.get("ARGA_VAPID_SUBJECT", "").strip()
    if not seed or not subject:
        return None
    signer, public = keypair(seed)
    return signer, public, subject


KINDS = text("""
    select m.id as app, coalesce(m.manifest->>'name', m.id) as app_name,
           n->>'kind' as kind, n->>'label' as label,
           coalesce((n->>'default')::boolean, false) as default_on
    from kernel.modules m,
         jsonb_array_elements(coalesce(m.manifest->'notifications', '[]'::jsonb)) as n
    where m.enabled
    order by m.id, n->>'kind'
""")


class Kind(BaseModel):
    app: str
    app_name: str
    kind: str
    label: str
    enabled: bool


async def kinds(connection: AsyncConnection) -> list[Kind]:
    prefs = await _prefs(connection)
    return [
        Kind(
            app=row.app,
            app_name=row.app_name,
            kind=row.kind,
            label=row.label,
            enabled=prefs.get((row.app, row.kind), row.default_on),
        )
        for row in (await connection.execute(KINDS)).all()
    ]


PREFS = text(f"""
    select app, kind, enabled, quiet_from, quiet_to from kernel.notification_pref
    where user_id = {CURRENT_USER_SQL}
""")


async def _prefs(connection: AsyncConnection) -> dict[tuple[str, str], bool]:
    return {
        (row.app, row.kind): row.enabled
        for row in (await connection.execute(PREFS)).all()
        if row.app and row.enabled is not None
    }


async def quiet(connection: AsyncConnection) -> tuple[time | None, time | None]:
    for row in (await connection.execute(PREFS)).all():
        if not row.app and not row.kind:
            return row.quiet_from, row.quiet_to
    return QUIET_FROM, QUIET_TO


def quiet_until(now: datetime, start: time | None, end: time | None) -> datetime | None:
    if start is None or end is None or start == end:
        return None
    local = now.astimezone(MADRID)
    clock = local.time()
    inside = start <= clock < end if start < end else clock >= start or clock < end
    if not inside:
        return None
    day = local.date() if clock < end else local.date() + timedelta(days=1)
    return datetime.combine(day, end, MADRID).astimezone(UTC)


class Keys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class DeviceIn(BaseModel):
    endpoint: str = Field(pattern=r"^https://", max_length=2000)
    keys: Keys
    name: str = Field(min_length=1, max_length=60)


class Device(BaseModel):
    id: str
    name: str
    created_at: datetime
    last_sent: datetime | None
    last_error: str | None = None
    last_error_at: datetime | None = None


class Recent(BaseModel):
    app: str
    title: str
    due_at: datetime
    sent_at: datetime | None
    outcome: str | None
    attempts: int


class Settings(BaseModel):
    configured: bool
    public_key: str | None
    devices: list[Device]
    kinds: list[Kind]
    quiet_from: time | None
    quiet_to: time | None
    recent: list[Recent] = Field(default_factory=list)
    late: int = 0


DEVICES = text(f"""
    select id::text, name, created_at, last_sent, last_error, last_error_at
    from kernel.push_subscription
    where user_id = {CURRENT_USER_SQL} order by created_at
""")

RECENT = text(f"""
    select app, title, due_at, sent_at, outcome, attempts from kernel.notification
    where user_id = {CURRENT_USER_SQL} and due_at <= now()
    order by due_at desc
    limit 15
""")

LATE_COUNT = text(f"""
    select count(*) from kernel.notification
    where user_id = {CURRENT_USER_SQL} and sent_at is null
      and coalesce(send_after, due_at) < :before
""")


@router.get("/notifications")
async def read_settings() -> Settings:
    require_person()
    keys = vapid()
    async with engine().begin() as connection:
        devices = [Device(**row._mapping) for row in (await connection.execute(DEVICES)).all()]
        start, end = await quiet(connection)
        found = await kinds(connection)
        recent = [Recent(**row._mapping) for row in (await connection.execute(RECENT)).all()]
        late = await connection.scalar(LATE_COUNT, {"before": datetime.now(UTC) - LATE})
    return Settings(
        configured=keys is not None,
        public_key=keys[1] if keys else None,
        devices=devices,
        kinds=found,
        quiet_from=start,
        quiet_to=end,
        recent=recent,
        late=late or 0,
    )


@router.post("/notifications/devices", status_code=201)
async def add_device(body: DeviceIn) -> Device:
    require_person()
    async with engine().begin() as connection:
        row = (
            await connection.execute(
                text("""
                    insert into kernel.push_subscription (endpoint, p256dh, auth, name)
                    values (:endpoint, :p256dh, :auth, :name)
                    on conflict (user_id, endpoint) do update
                    set p256dh = excluded.p256dh, auth = excluded.auth, name = excluded.name
                    returning id::text, name, created_at, last_sent, last_error, last_error_at
                """),
                {
                    "endpoint": body.endpoint,
                    "p256dh": body.keys.p256dh,
                    "auth": body.keys.auth,
                    "name": body.name.strip(),
                },
            )
        ).one()
    return Device(**row._mapping)


@router.delete("/notifications/devices/{device_id}", status_code=204)
async def remove_device(device_id: UUID) -> Response:
    require_person()
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.push_subscription where id = :id"), {"id": device_id}
        )
    return Response(status_code=204)


class PrefIn(BaseModel):
    app: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    kind: str = Field(pattern=NOTIFICATION_KIND_PATTERN)
    enabled: bool


@router.put("/notifications/prefs", status_code=204)
async def set_pref(body: PrefIn) -> Response:
    require_person()
    async with engine().begin() as connection:
        known = {(one.app, one.kind) for one in await kinds(connection)}
        if (body.app, body.kind) not in known:
            raise HTTPException(status_code=404, detail="esa app no declara ese aviso")
        await connection.execute(
            text("""
                insert into kernel.notification_pref (app, kind, enabled)
                values (:app, :kind, :enabled)
                on conflict (user_id, app, kind) do update
                set enabled = excluded.enabled, updated_at = now()
            """),
            body.model_dump(),
        )
    return Response(status_code=204)


class QuietIn(BaseModel):
    quiet_from: time | None
    quiet_to: time | None


@router.put("/notifications/quiet", status_code=204)
async def set_quiet(body: QuietIn) -> Response:
    require_person()
    if (body.quiet_from is None) != (body.quiet_to is None):
        raise HTTPException(status_code=422, detail="el silencio tiene principio y fin, o ninguno")
    async with engine().begin() as connection:
        await connection.execute(
            text("""
                insert into kernel.notification_pref (app, kind, quiet_from, quiet_to)
                values ('', '', :quiet_from, :quiet_to)
                on conflict (user_id, app, kind) do update
                set quiet_from = excluded.quiet_from, quiet_to = excluded.quiet_to,
                    updated_at = now()
            """),
            body.model_dump(),
        )
    return Response(status_code=204)


@router.post("/notifications/test")
async def send_test() -> dict[str, Any]:
    require_person()
    if vapid() is None:
        raise HTTPException(status_code=503, detail="los avisos aún no están configurados")
    message = {"title": "arga", "body": "Así te llegan los avisos.", "href": "/"}
    async with engine().begin() as connection:
        done = await deliver(connection, message)
    return {
        "sent": done.sent,
        "forgotten": done.gone,
        "failed": [{"device": name, "reason": refused.said()} for name, refused in done.failed],
    }


INBOX_DAYS = 30
NOT_FOR_YOU = ("apagado", "su app ya no lo declara")

INBOX = text(f"""
    select n.id::text, n.app, coalesce(m.manifest->>'name', n.app) as app_name, n.title, n.body,
           n.href, n.sent_at, n.read_at is not null as read
    from kernel.notification n
    left join kernel.modules m on m.id = n.app
    where n.user_id = {CURRENT_USER_SQL}
      and n.sent_at is not null and n.sent_at >= now() - make_interval(days => {INBOX_DAYS})
      and coalesce(n.outcome, '') <> all(:hidden)
    order by n.sent_at desc
    limit 300
""")

READ = text(f"""
    update kernel.notification set read_at = coalesce(read_at, now())
    where id = :id and user_id = {CURRENT_USER_SQL} and sent_at is not null
    returning id
""")


class Notice(BaseModel):
    id: str
    app: str
    app_name: str
    title: str
    body: str | None
    href: str
    sent_at: datetime
    read: bool


@router.get("/notifications/inbox")
async def inbox() -> list[Notice]:
    require_person()
    async with engine().connect() as connection:
        rows = (await connection.execute(INBOX, {"hidden": list(NOT_FOR_YOU)})).all()
    return [Notice(**row._mapping) for row in rows]


@router.post("/notifications/inbox/{notification_id}/read", status_code=204)
async def mark_read(notification_id: UUID) -> Response:
    require_person()
    async with engine().begin() as connection:
        found = await connection.scalar(READ, {"id": notification_id})
    if found is None:
        raise HTTPException(status_code=404, detail="ese aviso no está en tu bandeja")
    return Response(status_code=204)


class ScheduleIn(BaseModel):
    kind: str = Field(pattern=NOTIFICATION_KIND_PATTERN)
    key: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=120)
    body: str | None = Field(default=None, max_length=400)
    href: str = Field(pattern=r"^/", max_length=300)
    at: datetime


class CancelIn(BaseModel):
    key: str = Field(min_length=1, max_length=200)


class SyncIn(BaseModel):
    items: list[ScheduleIn] = Field(max_length=500)


STALE = timedelta(days=1)


SCHEDULE = text("""
    insert into kernel.notification (app, kind, key, title, body, href, due_at)
    values (:app, :kind, :key, :title, :body, :href, :at)
    on conflict (user_id, app, key) do update
    set kind = excluded.kind, title = excluded.title, body = excluded.body, href = excluded.href,
        due_at = excluded.due_at,
        outcome = case when kernel.notification.due_at = excluded.due_at
                       then kernel.notification.outcome end,
        attempts = case when kernel.notification.due_at = excluded.due_at
                        then kernel.notification.attempts else 0 end,
        send_after = case when kernel.notification.due_at = excluded.due_at
                          then kernel.notification.send_after end
    where kernel.notification.sent_at is null
    returning id::text, sent_at
""")
GONE_OUT = text("""
    select id::text, sent_at from kernel.notification where app = :app and key = :key
""")


async def serve(capability: str, app: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with engine().begin() as connection:
        if capability == "notify.sync":
            return await _sync(connection, app, SyncIn.model_validate(payload))
        if capability == "notify.cancel":
            wanted = CancelIn.model_validate(payload)
            result = await connection.execute(
                text(
                    "delete from kernel.notification "
                    "where app = :app and key = :key and sent_at is null"
                ),
                {"app": app, "key": wanted.key},
            )
            return {"cancelled": result.rowcount or 0}
        wanted = ScheduleIn.model_validate(payload)
        declared = {one.kind for one in await kinds(connection) if one.app == app}
        if wanted.kind not in declared:
            raise HTTPException(
                status_code=422, detail=f"'{app}' no declara el aviso '{wanted.kind}'"
            )
        row = (
            await connection.execute(
                SCHEDULE, {"app": app, **wanted.model_dump(exclude={"at"}), "at": wanted.at}
            )
        ).first() or (await connection.execute(GONE_OUT, {"app": app, "key": wanted.key})).one()
    return {"id": row.id, "sent": row.sent_at is not None}


PENDING_KEYS = text("""
    select key from kernel.notification where app = :app and sent_at is null
""")
KNOWN_KEYS = text("select key from kernel.notification where app = :app")


async def _sync(connection: AsyncConnection, app: str, wanted: SyncIn) -> dict[str, Any]:
    declared = {one.kind for one in await kinds(connection) if one.app == app}
    for item in wanted.items:
        if item.kind not in declared:
            raise HTTPException(
                status_code=422, detail=f"'{app}' no declara el aviso '{item.kind}'"
            )
    known = {row.key for row in (await connection.execute(KNOWN_KEYS, {"app": app})).all()}
    old = datetime.now(UTC) - STALE
    scheduled = skipped = 0
    for item in wanted.items:
        if item.key not in known and item.at < old:
            skipped += 1
            continue
        await connection.execute(
            SCHEDULE, {"app": app, **item.model_dump(exclude={"at"}), "at": item.at}
        )
        scheduled += 1
    keys = {item.key for item in wanted.items}
    gone = [row.key for row in (await connection.execute(PENDING_KEYS, {"app": app})).all()]
    gone = [key for key in gone if key not in keys]
    if gone:
        await connection.execute(
            text(
                "delete from kernel.notification "
                "where app = :app and sent_at is null and key = any(:keys)"
            ),
            {"app": app, "keys": gone},
        )
    return {"scheduled": scheduled, "cancelled": len(gone), "stale": skipped}


SUBSCRIPTIONS = text(f"""
    select id, endpoint, p256dh, auth, name from kernel.push_subscription
    where user_id = {CURRENT_USER_SQL}
""")


@dataclass(frozen=True)
class Refused:
    status: int | None
    reason: str = ""

    @property
    def gone(self) -> bool:
        return self.status in (404, 410)

    @property
    def passing(self) -> bool:
        return self.status is None or self.status in PASSING

    def said(self) -> str:
        code = str(self.status) if self.status is not None else "sin respuesta"
        return f"{code} {self.reason}".strip()[:200]


def _reason(response: Any) -> str:
    if response is None:
        return ""
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 - no era JSON: vale el texto
        body = None
    if isinstance(body, dict) and body.get("reason"):
        return str(body["reason"])[:120]
    said = (getattr(response, "text", "") or getattr(response, "reason", "") or "").strip()
    return said.splitlines()[0][:120] if said else ""


def _push(subscription: Any, message: dict[str, Any], keys: tuple[str, str, str]) -> Refused | None:
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(message, ensure_ascii=False),
            vapid_private_key=keys[0],
            vapid_claims={"sub": keys[2]},
            ttl=TTL_SECONDS,
            timeout=PUSH_TIMEOUT,
        )
    except WebPushException as error:
        response = getattr(error, "response", None)
        return Refused(getattr(response, "status_code", None), _reason(response))
    except Exception as error:  # noqa: BLE001 - la red, un certificado: se dice y se sigue
        return Refused(None, type(error).__name__)
    return None


@dataclass
class Delivery:
    devices: int = 0
    sent: int = 0
    gone: int = 0
    failed: list[tuple[str, Refused]] = field(default_factory=list)

    @property
    def passing(self) -> bool:
        return self.sent == 0 and any(refused.passing for _, refused in self.failed)

    def outcome(self) -> str:
        if not self.devices:
            return "sin dispositivos"
        said = [f"enviado a {self.sent} de {self.devices}"]
        said += [f"{name}: {refused.said()}" for name, refused in self.failed]
        return "; ".join(said)[:300]


FORGET = text("delete from kernel.push_subscription where id = :id")
WENT = text("update kernel.push_subscription set last_sent = now() where id = :id")
FAILED = text("""
    update kernel.push_subscription set last_error = :why, last_error_at = now() where id = :id
""")


async def deliver(connection: AsyncConnection, message: dict[str, Any]) -> Delivery:
    done = Delivery()
    keys = vapid()
    if keys is None:
        return done
    for subscription in (await connection.execute(SUBSCRIPTIONS)).all():
        done.devices += 1
        refused = await asyncio.to_thread(_push, subscription, message, keys)
        if refused is None:
            await connection.execute(WENT, {"id": subscription.id})
            done.sent += 1
            continue
        done.failed.append((subscription.name, refused))
        if refused.gone:
            await connection.execute(FORGET, {"id": subscription.id})
            done.gone += 1
        else:
            await connection.execute(FAILED, {"id": subscription.id, "why": refused.said()})
    return done


DUE = text(f"""
    select id, app, kind, title, body, href, due_at, attempts from kernel.notification
    where user_id = {CURRENT_USER_SQL} and sent_at is null and due_at <= :now
      and (send_after is null or send_after <= :now)
    order by coalesce(send_after, due_at)
    limit {BATCH}
""")

HOLD = text("update kernel.notification set send_after = :at where id = :id")

RETRY = text("""
    update kernel.notification
    set attempts = attempts + 1, send_after = :at, outcome = :why
    where id = :id
""")


async def _again(connection: AsyncConnection, row: Any, now: datetime, why: str) -> str:
    if row.attempts < len(RETRY_MINUTES):
        later = now + timedelta(minutes=RETRY_MINUTES[row.attempts])
        await connection.execute(RETRY, {"id": row.id, "at": later, "why": why[:300]})
        return "retrying"
    await _done(connection, row.id, f"no salió tras {row.attempts + 1} intentos: {why}"[:300])
    return "sent"


async def _one(
    connection: AsyncConnection,
    row: Any,
    now: datetime,
    enabled: dict[tuple[str, str], bool],
    until: datetime | None,
) -> str:
    state = enabled.get((row.app, row.kind))
    if not state:
        why = "apagado" if state is False else "su app ya no lo declara"
        await _done(connection, row.id, why)
        return "skipped"
    if until is not None:
        await connection.execute(HOLD, {"at": until, "id": row.id})
        return "waiting"
    message = {"title": row.title, "body": row.body or "", "href": row.href}
    done = await deliver(connection, message)
    if done.passing:
        return await _again(connection, row, now, done.outcome())
    await _done(connection, row.id, done.outcome())
    return "sent"


async def send_due(connection: AsyncConnection, now: datetime) -> dict[str, int]:
    counts = {"sent": 0, "skipped": 0, "waiting": 0, "retrying": 0}
    rows = (await connection.execute(DUE, {"now": now})).all()
    if not rows:
        return counts
    enabled = {(one.app, one.kind): one.enabled for one in await kinds(connection)}
    start, end = await quiet(connection)
    until = quiet_until(now, start, end)
    for row in rows:
        try:
            async with connection.begin_nested():
                counts[await _one(connection, row, now, enabled, until)] += 1
        except Exception as error:  # noqa: BLE001 - lo de un aviso no para a los demás
            print(
                f"avisos · {row.id}: {type(error).__name__}: {error}", file=sys.stderr, flush=True
            )
            counts[
                await _again(connection, row, now, f"falló al mandarlo: {type(error).__name__}")
            ] += 1
    return counts


async def _done(connection: AsyncConnection, notification_id: UUID, outcome: str) -> None:
    await connection.execute(
        text("update kernel.notification set sent_at = now(), outcome = :why where id = :id"),
        {"why": outcome, "id": notification_id},
    )


PEOPLE = text("select id from kernel.users order by created_at")


async def send_once(now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    total = {"sent": 0, "skipped": 0, "waiting": 0, "retrying": 0}
    async with engine().connect() as connection:
        people = [row.id for row in (await connection.execute(PEOPLE)).all()]
    for person in people:
        try:
            with as_user(person):
                async with engine().begin() as connection:
                    found = await send_due(connection, now)
        except Exception as error:  # noqa: BLE001 - lo de una persona no para a las demás
            print(
                f"avisos · {person}: {type(error).__name__}: {error}", file=sys.stderr, flush=True
            )
            continue
        for key, value in found.items():
            total[key] += value
    return total


async def loop() -> None:
    while True:
        if vapid() is not None:
            try:
                found = await send_once()
                if found["sent"] or found["retrying"]:
                    print(f"avisos · {found}", flush=True)
            except Exception as error:  # noqa: BLE001 - los avisos no tumban el kernel
                print(f"avisos · {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        await asyncio.sleep(SEND_EVERY)
