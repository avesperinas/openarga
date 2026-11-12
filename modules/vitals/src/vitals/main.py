from __future__ import annotations

import hmac
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_tenancy import UserFromHeader, require_person
from vitals import (
    body,
    heart,
    kpis,
    labs,
    night,
    panel,
    patterns,
    rhythm,
    sleep,
    steps,
    stress,
    today,
    tools,
    weight,
    widgets,
    workouts,
)
from vitals.db import SCHEMA, engine

MODULE_ID = "vitals"
UI_ROOT = f"/{MODULE_ID}"

app = FastAPI(title="Vitals", version=os.environ.get("APP_VERSION", "dev"))
app.add_middleware(UserFromHeader)


def ui_dist() -> Path:
    default = Path(__file__).resolve().parents[2] / "ui" / "dist"
    return Path(os.environ.get("UI_DIST", default))


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "module": MODULE_ID}


@app.get("/readyz")
async def readyz() -> dict:
    try:
        async with engine().connect() as connection:
            found = await connection.scalar(
                text("select 1 from information_schema.schemata where schema_name = :schema"),
                {"schema": SCHEMA},
            )
    except Exception as error:  # noqa: BLE001 -- cualquier fallo de conexión es "no listo"
        raise HTTPException(status_code=503, detail=f"sin base de datos: {error}") from error

    if not found:
        raise HTTPException(
            status_code=503,
            detail=f"el schema '{SCHEMA}' no existe todavía; lo aprovisiona el kernel al "
            f"registrar el manifiesto",
        )
    if not (ui_dist() / "index.html").is_file():
        raise HTTPException(status_code=503, detail=f"la app no está construida en {ui_dist()}")
    return {"status": "ready", "module": MODULE_ID, "schema": SCHEMA}


APP_ROLE = f"mod_{MODULE_ID}"
READER_ROLE = f"mod_{MODULE_ID}_read"


@asynccontextmanager
async def as_app() -> AsyncIterator[AsyncConnection]:
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{APP_ROLE}"'))
        yield connection


@app.get("/widgets/{widget_id}")
async def widget(widget_id: str) -> dict:
    renderer = widgets.RENDERERS.get(widget_id)
    if renderer is None:
        raise HTTPException(status_code=404, detail=f"vitals no tiene el widget '{widget_id}'")
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{READER_ROLE}"'))
        return await renderer(connection)


@app.get("/panel")
async def home_panel() -> dict:
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{READER_ROLE}"'))
        return await panel.build(connection)


INSUFFICIENT_PRIVILEGE = "42501"


@app.get("/tools")
async def list_tools() -> list[dict]:
    return [
        {"name": name, "input_schema": tool.arguments.model_json_schema()}
        for name, tool in tools.TOOLS.items()
    ]


@app.post("/tools/{name}")
async def call_tool(name: str, request: Request, x_arga_scopes: str = Header(default="")) -> dict:
    tool = tools.TOOLS.get(name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"vitals no tiene la tool '{name}'")

    role = tools.role_for_scopes(set(x_arga_scopes.split()))
    if role is None:
        raise HTTPException(status_code=403, detail=f"ningún scope de {MODULE_ID} en la llamada")

    try:
        arguments = tool.arguments.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        async with engine().begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            return {"content": await tool.run(connection, arguments)}
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE:
            raise HTTPException(
                status_code=403, detail=f"Postgres no deja a {role} hacer esto: {name}"
            ) from error
        raise


async def _edit(action, *args):
    try:
        async with as_app() as connection:
            return await action(connection, *args)
    except weight.NotFound as error:
        raise HTTPException(status_code=404, detail=f"no existe: {error}") from error
    except weight.Conflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/weight")
async def read_weight() -> weight.Summary:
    return await _edit(weight.summary)


@app.post("/weight", status_code=201)
async def log_weight(request: weight.WeightIn) -> weight.Logged:
    return await _edit(weight.log, request)


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Vitals no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Vitals")
    if capability not in (contracts.WEIGHT_LOG, contracts.WORKOUT_HEART):
        raise HTTPException(status_code=404, detail=f"Vitals no sabe hacer '{capability}'")
    require_person()
    if capability == contracts.WORKOUT_HEART:
        return await _workout_heart(await request.json(), x_arga_module)
    try:
        asked = contracts.WeightLog.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    logged = await _edit(weight.set_day, asked.kg, asked.day)
    print(f"peso       {logged.entry.kg} kg pedido por {x_arga_module}", flush=True)
    return contracts.weight_logged(
        id=logged.entry.id, day=logged.entry.day, kg=logged.entry.kg, already=logged.already
    )


async def _workout_heart(body: dict, asker: str) -> dict:
    try:
        asked = contracts.WorkoutHeartAsk.model_validate(body)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not asked.id.startswith(f"{asker}:"):
        raise HTTPException(status_code=403, detail="solo el vitals de lo que publicó quien pide")
    found = await _edit(workouts.one, asked.id)
    if found is None:
        return contracts.workout_heart(found=False)
    return contracts.workout_heart(
        found=True,
        minutes=found.minutes,
        avg=found.heart.avg,
        max=found.heart.max,
        zones=found.heart.zones,
        load=found.heart.load,
        recovery_2min=found.heart.recovery_2min,
        source=found.heart.source,
        kcal=found.kcal,
        max_heart_rate=found.max_heart_rate,
        beats=[one.model_dump() for one in found.beats],
        marks=[one.model_dump() for one in found.marks],
    )


@app.put("/weight/{weight_id}")
async def correct_weight(weight_id: UUID, request: weight.WeightIn) -> weight.Entry:
    return await _edit(weight.correct, str(weight_id), request)


@app.get("/kpis")
async def read_kpis() -> kpis.Kpis:
    return await _edit(kpis.read)


@app.get("/steps")
async def read_steps() -> steps.Summary:

    async def both(connection: AsyncConnection) -> steps.Summary:
        goal = await weight.goal(connection)
        return await steps.summary(connection, goal.steps_per_day)

    return await _edit(both)


@app.get("/body")
async def read_body() -> body.Overview:
    return await _edit(body.overview)


@app.get("/profile")
async def read_profile() -> body.Profile | None:
    return await _edit(body.profile)


@app.get("/body/{metric}")
async def read_figure(metric: str) -> body.Series:
    if metric not in body.BY_ID:
        raise HTTPException(status_code=404, detail=f"vitals no conoce la cifra '{metric}'")
    return await _edit(body.series, metric)


@app.get("/sleep")
async def read_sleep(since: date | None = None, until: date | None = None) -> sleep.Summary:
    return await _edit(sleep.summary, since, until)


@app.get("/sleep/{day}")
async def read_night(day: date) -> sleep.NightDetail:
    found = await _edit(sleep.night, day)
    if found is None:
        raise HTTPException(status_code=404, detail=f"no hay sueño del {day.isoformat()}")
    return found


@app.get("/night/{day}")
async def read_night_page(day: date) -> night.Page:
    found = await _edit(night.page, day)
    if found is None:
        raise HTTPException(status_code=404, detail=f"no hay noche el {day}")
    return found


@app.get("/heart")
async def read_heart_days() -> list[date]:
    return await _edit(heart.days)


@app.get("/heart/{day}")
async def read_heart_day(day: date) -> heart.Day:
    found = await _edit(heart.of_day, day)
    if found is None:
        raise HTTPException(status_code=404, detail=f"no hay vitals del {day.isoformat()}")
    return found


@app.get("/today")
async def read_today() -> today.Today:
    return await _edit(today.read)


@app.get("/day/{day}")
async def read_day(day: date) -> today.DayLine:
    return await _edit(today.day_line, day)


@app.get("/stress")
async def read_stress() -> stress.Stress:
    return await _edit(stress.read)


@app.get("/workouts")
async def read_workouts(
    since: date | None = None, until: date | None = None
) -> list[workouts.Workout]:
    last = until or steps.today()
    first = since or last - timedelta(days=89)
    if first > last:
        raise HTTPException(status_code=422, detail="`since` va antes que `until`")
    return await _edit(workouts.between, first, last)


@app.get("/workouts/detail")
async def read_workout(id: str) -> workouts.WorkoutDetail:
    found = await _edit(workouts.one, id)
    if found is None:
        raise HTTPException(status_code=404, detail="no hay ese entreno")
    return found


@app.get("/load")
async def read_load() -> workouts.Load:
    return await _edit(workouts.load)


@app.get("/sleep-patterns")
async def read_patterns() -> patterns.Patterns:
    return await _edit(patterns.read)


@app.get("/ecg")
async def read_ecgs() -> list[rhythm.Ecg]:
    return await _edit(rhythm.ecgs)


@app.get("/ecg/trace")
async def read_ecg(id: str) -> rhythm.EcgTrace:
    found = await _edit(rhythm.ecg_trace, id)
    if found is None:
        raise HTTPException(status_code=404, detail="no hay ese electrocardiograma")
    return found


@app.get("/irn")
async def read_irns() -> list[rhythm.Irn]:
    return await _edit(rhythm.irns)


@app.get("/devices")
async def read_devices() -> list[rhythm.Device]:
    return await _edit(rhythm.devices)


@app.get("/analytes")
async def read_analytes() -> list[labs.Analyte]:
    return await _edit(labs.catalogue)


@app.get("/checkups")
async def read_checkups() -> list[labs.Checkup]:
    return await _edit(labs.checkups)


class Recorded(BaseModel):
    id: str
    existed: bool


@app.post("/checkups", status_code=201)
async def record_checkup(request: labs.CheckupIn) -> Recorded:

    async def both(connection: AsyncConnection) -> Recorded:
        found, existed = await labs.record_checkup(connection, request)
        return Recorded(id=found, existed=existed)

    return await _edit(both)


@app.post("/checkups/{checkup_id}/results", status_code=201)
async def add_result(checkup_id: UUID, request: labs.ResultIn) -> labs.Result:
    return await _edit(labs.add_result, str(checkup_id), request)


@app.put("/checkups/{checkup_id}/document", status_code=204)
async def upload_document(checkup_id: UUID, request: Request, filename: str = "") -> Response:
    declared = int(request.headers.get("content-length") or 0)
    if declared > labs.PDF_LIMIT:
        raise HTTPException(status_code=413, detail="el PDF pasa de 20 MB")
    content = await request.body()
    await _edit(labs.save_document, str(checkup_id), filename, content)
    return Response(status_code=204)


@app.get("/checkups/{checkup_id}/document")
async def read_document(checkup_id: UUID) -> Response:
    name, content = await _edit(labs.document, str(checkup_id))
    return Response(
        content,
        media_type="application/pdf",
        headers={"content-disposition": f'inline; filename="{name}"', "cache-control": "private"},
    )


@app.get("/labs/changes")
async def read_changes() -> labs.Changes:
    return await _edit(labs.changes)


@app.get("/labs")
async def read_labs() -> labs.Table:
    return await _edit(labs.table)


@app.get("/labs/{analyte}")
async def read_analyte(analyte: str) -> labs.Evolution:
    return await _edit(labs.evolution, analyte)


@app.get("/goals")
async def read_goals() -> weight.Goal:
    return await _edit(weight.goal)


@app.put("/goals")
async def set_goals(request: weight.Goal) -> weight.Goal:
    return await _edit(weight.set_goal, request)


@app.get("/version")
async def version() -> dict:
    return {"service": MODULE_ID, "version": app.version}


@app.get(UI_ROOT)
@app.get(UI_ROOT + "/{path:path}")
async def ui(path: str = "") -> FileResponse:
    root = ui_dist().resolve()
    candidate = (root / path).resolve()
    if path and candidate.is_file() and candidate.is_relative_to(root):
        immutable = candidate.parent.name == "assets"
        return FileResponse(
            candidate,
            headers={
                "cache-control": "public, max-age=31536000, immutable" if immutable else "no-cache"
            },
        )
    index = root / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="la app no está construida")
    return FileResponse(index, headers={"cache-control": "no-cache"})
