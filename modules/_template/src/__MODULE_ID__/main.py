from __future__ import annotations

from fastapi import Query

from __MODULE_ID__ import publisher, readings, tools, widgets
from arga_module.service import Service

MODULE_ID = "__MODULE_ID__"

service = Service(
    MODULE_ID,
    "__MODULE_NAME__",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    errors={readings.NotFound: 404},
    publisher=publisher.PUBLISHER,
    ui=False,
)
app = service.app
_edit = service.edit


@app.get("/readings")
async def list_readings(
    label: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=30, ge=1, le=500),
) -> list[readings.Reading]:
    return await _edit(readings.list_readings, label, limit)


@app.post("/readings", status_code=201)
async def add_reading(request: readings.ReadingIn) -> readings.Reading:
    return await _edit(readings.add, request)


@app.put("/targets")
async def set_target(request: readings.TargetIn) -> readings.Target:
    return await _edit(readings.set_target, request)
