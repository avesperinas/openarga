from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.service import Service
from arga_tenancy import current_spaces, kernel_url, require_person, user_headers
from goals import goals, metrics, publisher, tasks, tools, widgets
from goals import panel as home_panel
from goals.common import Conflict, NotFound

MODULE_ID = "goals"
UI_ROOT = f"/{MODULE_ID}"


def _told(run):

    async def told(connection: AsyncConnection, arguments: Any, **extra: Any) -> dict[str, Any]:
        try:
            async with connection.begin_nested():
                return await run(connection, arguments, **extra)
        except (NotFound, Conflict) as error:
            return {"error": str(error)}

    return told


def _acting(widget_id: str):

    async def act(connection: AsyncConnection, verb: str, item_id: str) -> None:
        try:
            await widgets.act(connection, widget_id, verb, item_id)
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE:
                raise HTTPException(status_code=403, detail="no puedes hacer esto aquí") from error
            raise

    return act


service = Service(
    MODULE_ID,
    "KPIs",
    tools={
        name: dataclasses.replace(tool, run=_told(tool.run)) for name, tool in tools.TOOLS.items()
    },
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    actions={widget_id: _acting(widget_id) for widget_id in widgets.ACTING},
    errors={NotFound: 404, Conflict: 409},
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
service.ui_root = UI_ROOT
app = service.app
as_app = service.as_app

INSUFFICIENT_PRIVILEGE = "42501"


async def _edit(action, *args):
    try:
        async with as_app() as connection:
            return await action(connection, *args)
    except NotFound as error:
        raise HTTPException(status_code=404, detail=f"no existe: {error}") from error
    except Conflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE:
            raise HTTPException(status_code=403, detail="no puedes hacer esto aquí") from error
        raise


async def _seeded(connection: AsyncConnection, action, *args):
    await goals.seed(connection)
    return await action(connection, *args)


@app.get("/categories")
async def list_categories() -> list[tasks.Category]:
    return await _edit(_seeded, tasks.categories)


@app.post("/categories", status_code=201)
async def create_category(body: tasks.CategoryIn) -> tasks.Category:
    return await _edit(tasks.create_category, body)


@app.put("/categories/{category_id}")
async def update_category(category_id: UUID, body: tasks.CategoryPatch) -> tasks.Category:
    return await _edit(tasks.update_category, str(category_id), body)


@app.post("/categories/order")
async def order_categories(body: tasks.OrderIn) -> list[tasks.Category]:
    return await _edit(tasks.order, body)


@app.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: UUID) -> Response:
    await _edit(tasks.remove_category, str(category_id))
    return Response(status_code=204)


@app.get("/tasks")
async def list_tasks(
    state: Literal["pending", "done"] = "pending",
    category: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=300),
) -> list[tasks.Task]:
    wanted = str(category) if category else None
    if state == "done":
        return await _edit(tasks.done, wanted, limit)
    return await _edit(tasks.pending, wanted)


@app.get("/tasks/{task_id}")
async def read_task(task_id: UUID) -> tasks.Task:
    return await _edit(tasks.one, str(task_id))


@app.post("/tasks", status_code=201)
async def create_task(body: tasks.TaskIn) -> tasks.Task:
    return await _edit(tasks.create, body)


@app.put("/tasks/{task_id}")
async def update_task(task_id: UUID, body: tasks.TaskPatch) -> tasks.Task:
    return await _edit(tasks.update, str(task_id), body)


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: UUID) -> Response:
    await _edit(tasks.remove, str(task_id))
    return Response(status_code=204)


@app.post("/tasks/{task_id}/done")
async def complete_task(task_id: UUID) -> tasks.Completed:
    return await _edit(tasks.complete, str(task_id))


@app.post("/tasks/{task_id}/undo")
async def undo_task(task_id: UUID) -> tasks.Task:
    return await _edit(tasks.undo, str(task_id))


async def _settled(connection: AsyncConnection, action, *args):
    await goals.seed(connection)
    await goals.settle(connection)
    return await action(connection, *args)


@app.get("/goals")
async def list_goals(
    state: Literal["active", "closed"] = "active", category: UUID | None = None
) -> list[goals.Goal]:
    if state == "closed":
        return await _edit(_settled, goals.closed)
    return await _edit(_settled, goals.active, str(category) if category else None)


@app.get("/goals/{goal_id}")
async def read_goal(goal_id: UUID) -> goals.GoalDetail:
    return await _edit(goals.detail, str(goal_id))


@app.post("/goals", status_code=201)
async def create_goal(body: goals.GoalIn) -> goals.Goal:
    return await _edit(goals.create, body)


@app.post("/goals/past", status_code=201)
async def record_past_goal(body: goals.PastGoalIn) -> goals.Goal:
    return await _edit(goals.record_past, body)


@app.put("/goals/{goal_id}")
async def update_goal(goal_id: UUID, body: goals.GoalPatch) -> goals.Goal:
    return await _edit(goals.update, str(goal_id), body)


@app.delete("/goals/{goal_id}", status_code=204)
async def delete_goal(goal_id: UUID) -> Response:
    await _edit(goals.remove, str(goal_id))
    return Response(status_code=204)


@app.post("/goals/order")
async def order_goals(body: goals.OrderIn) -> list[goals.Goal]:
    return await _edit(goals.order, body)


@app.post("/goals/{goal_id}/checks")
async def check_goal(goal_id: UUID, body: goals.CheckIn) -> goals.Goal:
    return await _edit(goals.check, str(goal_id), body)


@app.delete("/goals/{goal_id}/checks/{day}")
async def uncheck_goal(goal_id: UUID, day: date) -> goals.Goal:
    return await _edit(goals.uncheck, str(goal_id), day)


class CloseIn(BaseModel):
    outcome: Literal["achieved", "abandoned"]


@app.post("/goals/{goal_id}/close")
async def close_goal(goal_id: UUID, body: CloseIn) -> goals.Goal:
    return await _edit(goals.close, str(goal_id), body.outcome)


@app.post("/goals/{goal_id}/reopen")
async def reopen_goal(goal_id: UUID) -> goals.Goal:
    return await _edit(goals.reopen, str(goal_id))


@app.get("/metrics")
async def list_metrics() -> list[metrics.Metric]:
    return await _edit(metrics.available)


async def ask_kernel(request: Request, method: str, path: str, body: dict | None = None) -> Any:
    require_person()
    try:
        response = await service.client().request(
            method, f"{kernel_url()}{path}", json=body, headers=user_headers(), timeout=10.0
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail="el kernel no contesta") from error
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail=f"el kernel contesta {response.status_code}")
    if response.status_code >= 400:
        detail = response.json().get("detail", "no se puede") if response.content else "no se puede"
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json() if response.content else None


async def fresh_spaces(request: Request) -> list[dict]:
    found = await ask_kernel(request, "GET", "/internal/spaces")
    current_spaces.set(tuple(UUID(space["id"]) for space in found))
    return found


class SpaceOut(BaseModel):
    id: str
    name: str
    role: str
    members: int


def _space(raw: dict) -> SpaceOut:
    return SpaceOut(
        id=raw["id"], name=raw["name"], role=raw["role"], members=len(raw.get("members", []))
    )


@app.get("/spaces")
async def list_spaces(request: Request) -> list[SpaceOut]:
    return [_space(raw) for raw in await fresh_spaces(request)]


class NewSpace(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@app.post("/spaces", status_code=201)
async def create_space(request: Request, body: NewSpace) -> SpaceOut:
    return _space(
        await ask_kernel(request, "POST", "/internal/spaces", {"name": body.name.strip()})
    )


@app.post("/spaces/{space_id}/invites", status_code=201)
async def invite(request: Request, space_id: UUID) -> dict:
    return await ask_kernel(request, "POST", f"/internal/spaces/{space_id}/invites")


class JoinIn(BaseModel):
    code: str = Field(min_length=12, max_length=32)


@app.post("/spaces/join")
async def join(request: Request, body: JoinIn) -> SpaceOut:
    return _space(await ask_kernel(request, "POST", "/internal/spaces/join", {"code": body.code}))


@app.put("/categories/{category_id}/space")
async def share_category(
    request: Request, category_id: UUID, body: tasks.SpaceIn
) -> tasks.Category:
    spaces = await fresh_spaces(request)
    if body.space_id is not None and body.space_id not in {s["id"] for s in spaces}:
        raise HTTPException(status_code=404, detail="no estás en ese espacio")
    return await _edit(tasks.share_category, str(category_id), body.space_id)


service.serve_ui()
