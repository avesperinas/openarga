from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from vitals import rhythm

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
            level = f" al {device.battery_pct} %" if device.battery_pct is not None else ""
            out.append(
                notify.notification(
                    BATTERY,
                    f"battery:{device.id}:{now.astimezone(notify.MADRID).date().isoformat()}",
                    f"{device.name}: batería baja{level}",
                    "/vitals/",
                    now,
                    body="Cárgala para que sigan llegando el vitals y el sueño.",
                )
            )
        if device.last_sync is not None and now - device.last_sync > STALE:
            out.append(
                notify.notification(
                    SYNC,
                    f"sync:{device.id}:{device.last_sync.isoformat()}",
                    f"{device.name} lleva un día sin sincronizar",
                    "/vitals/",
                    device.last_sync + STALE,
                    body="Abre la app de Google Health con la pulsera cerca.",
                )
            )
    for one in await rhythm.ecgs(connection):
        out.append(
            notify.notification(
                ECG,
                f"ecg:{one.id}",
                "Electrocardiograma nuevo",
                "/vitals/cuerpo",
                one.end,
                body=one.result_text or "Sin resultado del aparato.",
            )
        )
    for one in await rhythm.irns(connection):
        out.append(
            notify.notification(
                IRN,
                f"irn:{one.id}",
                "Aviso de ritmo irregular de la pulsera",
                "/vitals/cuerpo",
                one.end,
                body=f"Entre {one.start.astimezone(notify.MADRID):%H:%M} y "
                f"{one.end.astimezone(notify.MADRID):%H:%M}.",
            )
        )
    return out
