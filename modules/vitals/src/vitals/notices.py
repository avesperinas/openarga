from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from vitals import rhythm
from vitals.text import t

BATTERY, SYNC, ECG, IRN = "battery_low", "not_synced", "ecg", "irn"
LOW = 20
STALE = timedelta(hours=24)


def _low(device: rhythm.Device) -> bool:
    return device.battery in ("low", "empty") or (
        device.battery_pct is not None and device.battery_pct <= LOW
    )


async def build(connection: AsyncConnection, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    out = []
    for device in await rhythm.devices(connection):
        if _low(device):
            level = (
                t("notice.battery_level", value=device.battery_pct)
                if device.battery_pct is not None
                else ""
            )
            out.append(
                notify.notification(
                    BATTERY,
                    f"battery:{device.id}:{now.astimezone(notify.zone()).date().isoformat()}",
                    t("notice.battery", name=device.name, level=level),
                    "/vitals/",
                    now,
                    body=t("notice.battery_body"),
                )
            )
        if device.last_sync is not None and now - device.last_sync > STALE:
            out.append(
                notify.notification(
                    SYNC,
                    f"sync:{device.id}:{device.last_sync.isoformat()}",
                    t("notice.sync", name=device.name),
                    "/vitals/",
                    device.last_sync + STALE,
                    body=t("notice.sync_body"),
                )
            )
    for one in await rhythm.ecgs(connection):
        out.append(
            notify.notification(
                ECG,
                f"ecg:{one.id}",
                t("notice.ecg"),
                "/vitals/body",
                one.end,
                body=one.result_text or t("notice.ecg_empty"),
            )
        )
    for one in await rhythm.irns(connection):
        out.append(
            notify.notification(
                IRN,
                f"irn:{one.id}",
                t("notice.irn"),
                "/vitals/body",
                one.end,
                body=t(
                    "notice.irn_body",
                    start=f"{one.start.astimezone(notify.zone()):%H:%M}",
                    end=f"{one.end.astimezone(notify.zone()):%H:%M}",
                ),
            )
        )
    return out
