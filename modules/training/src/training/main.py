from __future__ import annotations

import hmac
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_module import preferences
from arga_tenancy import UserFromHeader, require_person, user_headers
from training import (
    activities,
    bodyweight,
    editor,
    links,
    moving,
    outcome,
    panel,
    plan,
    stats,
    tools,
    training,
    widgets,
)
from training.db import SCHEMA, engine
from training.publisher import kernel_url

MODULE_ID = "training"
log = logging.getLogger(__name__)
UI_ROOT = f"/{MODULE_ID}"

app = FastAPI(title="Training", version=os.environ.get("APP_VERSION", "dev"))
app.add_middleware(UserFromHeader)


@app.middleware("http")
async def person_preferences(request: Request, call_next):
    token = preferences.use(preferences.from_headers(request.headers))
    try:
        return await call_next(request)
    finally:
        preferences.reset(token)


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
    except Exception as error:  # noqa: BLE001 -- any connection failure means "not ready"
        raise HTTPException(status_code=503, detail=f"no database: {error}") from error

    if not found:
        raise HTTPException(
            status_code=503,
            detail=f"schema '{SCHEMA}' does not exist yet; the kernel provisions it when it "
            f"registers the manifest",
        )
    if not (ui_dist() / "index.html").is_file():
        raise HTTPException(status_code=503, detail=f"the app is not built in {ui_dist()}")
    return {"status": "ready", "module": MODULE_ID, "schema": SCHEMA}


APP_ROLE = f"mod_{MODULE_ID}"


@asynccontextmanager
async def as_app() -> AsyncIterator[AsyncConnection]:
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{APP_ROLE}"'))
        yield connection


READER_ROLE = f"mod_{MODULE_ID}_read"


@app.get("/widgets/{widget_id}")
async def widget(widget_id: str) -> dict:
    renderer = widgets.RENDERERS.get(widget_id)
    if renderer is None:
        raise HTTPException(status_code=404, detail=f"training has no widget '{widget_id}'")
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
        raise HTTPException(status_code=404, detail=f"training has no tool '{name}'")

    role = tools.role_for_scopes(set(x_arga_scopes.split()))
    if role is None:
        raise HTTPException(status_code=403, detail=f"no {MODULE_ID} scope in the call")

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


class Today(BaseModel):
    plan: plan.ActivePlan | None
    settings: plan.Settings
    next: training.NextSession | None
    in_progress: str | None
    week: training.Week
    rotation: training.Rotation | None


async def warm_stats() -> None:
    try:
        async with as_app() as connection:
            await stats.warm(connection, training.local_day(datetime.now(UTC)))
    except Exception:  # noqa: BLE001 -- warming up is a favour, never a request error
        log.exception("could not precompute Stats")


@app.get("/today")
async def today(background: BackgroundTasks) -> Today:
    background.add_task(warm_stats)
    async with as_app() as connection:
        return Today(
            plan=await plan.active_plan(connection),
            settings=await plan.settings(connection),
            next=await training.next_session(connection),
            in_progress=await training.in_progress(connection),
            week=await training.week(connection, training.local_day(datetime.now(UTC))),
            rotation=await training.rotation(connection),
        )


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, training.NotFound):
        return HTTPException(status_code=404, detail=f"not found: {error}")
    return HTTPException(status_code=409, detail=str(error))


class Created(BaseModel):
    id: str


@app.post("/sessions", status_code=201)
async def start_session(request: training.Start) -> Created:
    try:
        async with as_app() as connection:
            return Created(id=await training.start_session(connection, request))
    except training.Conflict as error:
        raise _translate(error) from error


@app.get("/sessions")
async def list_sessions(
    since: date | None = None, until: date | None = None
) -> list[training.SessionSummary]:
    last = until or training.local_day(datetime.now(UTC))
    first = since or last - timedelta(days=366)
    if first > last:
        raise HTTPException(status_code=422, detail="`since` must come before `until`")
    async with as_app() as connection:
        return await training.sessions_between(connection, first, last)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: UUID, with_sets: bool = False) -> None:
    try:
        async with as_app() as connection:
            await training.delete_session(connection, str(session_id), with_sets)
    except (training.NotFound, training.Conflict) as error:
        raise _translate(error) from error


@app.get("/sessions/{session_id}")
async def read_session(session_id: UUID) -> training.SessionView:
    try:
        async with as_app() as connection:
            return await training.read_session(connection, str(session_id))
    except training.NotFound as error:
        raise _translate(error) from error


@app.put("/sessions/{session_id}")
async def start_session_with_id(session_id: UUID, request: training.Start) -> Created:
    try:
        async with as_app() as connection:
            started = training.Start(**{**request.model_dump(), "id": str(session_id)})
            return Created(id=await training.start_session(connection, started))
    except (training.NotFound, training.Conflict) as error:
        raise _translate(error) from error


@app.get("/me")
async def me() -> dict[str, str]:
    return {"user_id": str(require_person())}


@app.get("/sessions/{session_id}/outcome")
async def read_outcome(session_id: UUID) -> outcome.Outcome:
    try:
        async with as_app() as connection:
            return await outcome.read(connection, str(session_id))
    except outcome.NotFound as error:
        raise HTTPException(status_code=404, detail=f"session {error} does not exist") from error


@app.post("/sessions/{session_id}/finish")
async def finish_session(
    session_id: UUID, request: training.Finish, background: BackgroundTasks
) -> training.SessionView:
    background.add_task(warm_stats)
    try:
        async with as_app() as connection:
            await training.finish_session(connection, str(session_id), request)
            return await training.read_session(connection, str(session_id))
    except (training.NotFound, training.Conflict) as error:
        raise _translate(error) from error


@app.put("/sessions/{session_id}/times")
async def change_times(session_id: UUID, request: training.Times) -> training.SessionView:
    try:
        async with as_app() as connection:
            await training.change_times(connection, str(session_id), request)
            return await training.read_session(connection, str(session_id))
    except (training.NotFound, training.Conflict) as error:
        raise _translate(error) from error


@app.post("/sessions/{session_id}/exercises")
async def add_exercise(session_id: UUID, request: training.ExerciseIn) -> Created:
    try:
        async with as_app() as connection:
            return Created(id=await training.add_exercise(connection, str(session_id), request))
    except training.NotFound as error:
        raise _translate(error) from error
    except DBAPIError as error:
        raise HTTPException(status_code=409, detail=str(error.orig).splitlines()[0]) from error


@app.put("/sessions/{session_id}/exercises/{exercise_id}")
async def put_exercise(
    session_id: UUID, exercise_id: UUID, request: training.ExerciseIn
) -> Created:
    try:
        async with as_app() as connection:
            return Created(
                id=await training.put_exercise(
                    connection, str(session_id), str(exercise_id), request
                )
            )
    except (training.NotFound, training.Conflict) as error:
        raise _translate(error) from error
    except DBAPIError as error:
        raise HTTPException(status_code=409, detail=str(error.orig).splitlines()[0]) from error


@app.put("/sessions/{session_id}/exercises/{exercise_id}/notes")
async def set_exercise_notes(
    session_id: UUID, exercise_id: UUID, request: training.NotesIn
) -> training.NotesIn:
    try:
        async with as_app() as connection:
            notes = await training.set_exercise_notes(
                connection, str(session_id), str(exercise_id), request
            )
            return training.NotesIn(notes=notes)
    except training.NotFound as error:
        raise _translate(error) from error


@app.put("/sessions/{session_id}/exercises/{exercise_id}/sets/{number}")
async def put_set(
    session_id: UUID,
    exercise_id: UUID,
    number: Annotated[int, PathParam(ge=1, le=50)],
    request: training.SetIn,
) -> training.SetOut:
    try:
        async with as_app() as connection:
            return await training.put_set(
                connection, str(session_id), str(exercise_id), number, request
            )
    except training.NotFound as error:
        raise _translate(error) from error


async def _edit(action, *args):
    try:
        async with as_app() as connection:
            return await action(connection, *args)
    except (training.NotFound, training.Conflict) as error:
        raise _translate(error) from error
    except DBAPIError as error:
        raise HTTPException(status_code=409, detail=str(error.orig).splitlines()[0]) from error


@app.get("/plan")
async def read_plan() -> editor.Editor:
    return await _edit(editor.editor)


@app.post("/plan", status_code=201)
async def create_plan(request: editor.PlanIn) -> editor.Editor:
    return await _edit(editor.create_plan, request)


@app.patch("/plan")
async def rename_plan(request: editor.PlanIn) -> editor.Editor:
    return await _edit(editor.rename_plan, request)


@app.post("/plan/draft")
async def open_draft() -> editor.Editor:
    return await _edit(editor.open_draft)


@app.put("/plan/draft")
async def save_draft(request: editor.DraftIn) -> editor.Editor:
    return await _edit(editor.save_draft, request)


@app.delete("/plan/draft")
async def discard_draft() -> editor.Editor:
    return await _edit(editor.discard_draft)


@app.post("/plan/draft/publish")
async def publish_draft() -> editor.Editor:
    return await _edit(editor.publish_draft)


@app.get("/catalogue")
async def read_catalogue() -> editor.Catalogue:
    return await _edit(editor.catalogue)


@app.post("/exercises", status_code=201)
async def create_exercise(request: editor.ExerciseIn) -> editor.Exercise:
    return await _edit(editor.create_exercise, request)


@app.put("/exercises/{exercise_id}/muscles")
async def update_muscles(exercise_id: UUID, request: editor.MusclesIn) -> editor.Exercise:
    return await _edit(editor.update_muscles, str(exercise_id), request)


@app.post("/exercises/{exercise_id}/variants", status_code=201)
async def create_variant(exercise_id: UUID, request: editor.VariantIn) -> editor.Variant:
    return await _edit(editor.create_variant, str(exercise_id), request)


@app.post("/gyms", status_code=201)
async def create_gym(request: editor.GymIn) -> editor.Gym:
    return await _edit(editor.create_gym, request)


@app.put("/gyms/{gym_id}")
async def update_gym(gym_id: UUID, request: editor.GymIn) -> editor.Gym:
    return await _edit(editor.update_gym, str(gym_id), request)


@app.put("/settings")
async def update_settings(request: editor.SettingsIn) -> plan.Settings:
    return await _edit(editor.update_settings, request)


def kernel_transport() -> httpx.AsyncBaseTransport | None:
    return None


async def _log_weight(kg: float, day: date | None) -> bodyweight.History:
    on = day or training.local_day(datetime.now(UTC))
    await _edit(bodyweight.keep, on, kg)
    async with httpx.AsyncClient(transport=kernel_transport()) as client:
        sent = await bodyweight.ask(client, on, kg)
    found = await _edit(bodyweight.history)
    return bodyweight.with_logged(found, on, kg, sent is not None)


HEART_ID = r"^training:(session|activity):[0-9a-f-]{36}$"


@app.get("/heart")
async def read_heart(id: Annotated[str, Query(pattern=HEART_ID)]) -> contracts.WorkoutHeart:
    require_person()
    try:
        async with httpx.AsyncClient(transport=kernel_transport()) as client:
            response = await client.post(
                f"{kernel_url()}/internal/capabilities/{contracts.WORKOUT_HEART}",
                json=contracts.workout_heart_ask(id=id),
                headers={**user_headers(), "x-arga-module": MODULE_ID},
                timeout=10.0,
            )
        if response.status_code == 200:
            return contracts.WorkoutHeart.model_validate(response.json())
    except (httpx.HTTPError, ValidationError, ValueError):
        pass
    return contracts.WorkoutHeart(found=False)


@app.get("/weight")
async def read_weight() -> bodyweight.History:
    return await _edit(bodyweight.history)


@app.post("/weight")
async def log_weight(request: bodyweight.WeightIn) -> bodyweight.History:
    return await _log_weight(request.kg, request.day)


@app.put("/bodyweight")
async def update_bodyweight(request: editor.BodyweightIn) -> plan.Settings:
    logged = await _log_weight(request.kg, None)
    found = await _edit(plan.settings)
    return found.model_copy(update={"bodyweight": logged.latest.kg if logged.latest else None})


@app.get("/stats")
async def read_stats(period: stats.Period = "3m") -> stats.Stats:
    async with as_app() as connection:
        settings = await plan.settings(connection)
        return await stats.read(
            connection, period, training.local_day(datetime.now(UTC)), settings.weekly_goal
        )


@app.get("/stats/muscles/{muscle_id}")
async def read_muscle_stats(muscle_id: str, period: stats.Period = "3m") -> stats.MuscleStats:
    async with as_app() as connection:
        found = await stats.read_muscle(
            connection, muscle_id, period, training.local_day(datetime.now(UTC))
        )
    if found is None:
        raise HTTPException(status_code=404, detail=f"muscle {muscle_id} does not exist")
    return found


@app.get("/stats/variants/{variant_id}")
async def read_variant_stats(variant_id: UUID, period: stats.Period = "3m") -> stats.VariantStats:
    async with as_app() as connection:
        found = await stats.read_variant(
            connection, str(variant_id), period, training.local_day(datetime.now(UTC))
        )
        if found is not None:
            found.notes = await links.notes_about(connection, str(variant_id))
    if found is None:
        raise HTTPException(status_code=404, detail=f"variant {variant_id} does not exist")
    return found


@app.put("/stats/points/{point_id}", status_code=204)
async def judge_point(point_id: UUID, request: stats.VerdictIn) -> None:
    async with as_app() as connection:
        if not await stats.set_verdict(connection, str(point_id), request):
            raise HTTPException(status_code=404, detail=f"exercise {point_id} does not exist")


@app.delete("/stats/points/{point_id}", status_code=204)
async def unjudge_point(point_id: UUID) -> None:
    async with as_app() as connection:
        await stats.clear_verdict(connection, str(point_id))


@app.post("/stats/marks", status_code=201)
async def mark_machine(request: stats.MarkIn) -> Created:
    try:
        async with as_app() as connection:
            found = await stats.add_mark(connection, request)
    except DBAPIError as error:
        raise HTTPException(status_code=409, detail=str(error.orig).splitlines()[0]) from error
    if found is None:
        raise HTTPException(status_code=404, detail=f"variant {request.variant_id} does not exist")
    return Created(id=found)


@app.delete("/stats/marks/{mark_id}", status_code=204)
async def unmark_machine(mark_id: UUID) -> None:
    async with as_app() as connection:
        await stats.remove_mark(connection, str(mark_id))


@app.get("/activity-types")
async def activity_types() -> list[activities.ActivityType]:
    return await _edit(activities.types)


@app.post("/activity-types", status_code=201)
async def create_activity_type(request: activities.ActivityTypeIn) -> activities.ActivityType:
    return await _edit(activities.create_type, request)


@app.put("/activity-types/{type_id}")
async def update_activity_type(
    type_id: UUID, request: activities.ActivityTypeIn
) -> activities.ActivityType:
    return await _edit(activities.update_type, str(type_id), request)


@app.get("/activities")
async def list_activities(
    since: date | None = None, until: date | None = None
) -> list[activities.Activity]:
    last = until or training.local_day(datetime.now(UTC))
    first = since or last - timedelta(days=366)
    if first > last:
        raise HTTPException(status_code=422, detail="`since` must come before `until`")
    return await _edit(activities.between, first, last)


@app.post("/activities", status_code=201)
async def log_activity(request: activities.ActivityIn) -> activities.Activity:
    return await _edit(activities.log, request)


@app.delete("/activities/{activity_id}", status_code=204)
async def remove_activity(activity_id: UUID) -> None:
    await _edit(activities.remove, str(activity_id))


class StartActivity(BaseModel):
    activity_type_id: str


@app.post("/activities/start", status_code=201)
async def start_activity(request: StartActivity) -> activities.Activity:
    return await _edit(activities.start_now, request.activity_type_id)


@app.get("/activities/ongoing")
async def ongoing_activities() -> list[activities.Activity]:
    return await _edit(activities.ongoing)


@app.post("/activities/{activity_id}/finish")
async def finish_activity(activity_id: UUID) -> activities.Activity:
    return await _edit(activities.finish, str(activity_id))


class ActivityTimes(BaseModel):
    start: datetime
    end: datetime


@app.put("/activities/{activity_id}/times")
async def activity_times(activity_id: UUID, request: ActivityTimes) -> activities.Activity:
    return await _edit(activities.move, str(activity_id), request.start, request.end)


@app.get("/variants/{variant_id}/last")
async def last_time(
    variant_id: UUID, before: UUID | None = None, gym_id: UUID | None = None
) -> training.LastTime | None:
    async with as_app() as connection:
        return await training.last_time(
            connection,
            str(variant_id),
            str(before) if before else None,
            str(gym_id) if gym_id else None,
        )


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Training has no MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Training")
    if capability != contracts.AGENDA_MOVE:
        raise HTTPException(status_code=404, detail=f"Training no sabe hacer '{capability}'")
    require_person()
    try:
        asked = contracts.AgendaMove.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    answer = await _edit(moving.move, asked)
    print(f"calendar {asked.uid} moved by {x_arga_module}", flush=True)
    return answer


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
    if path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
        raise HTTPException(status_code=404, detail=f"not found: {path}")
    index = root / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="the app is not built")
    return FileResponse(index, headers={"cache-control": "no-cache"})
