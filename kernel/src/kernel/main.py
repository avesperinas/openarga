import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from sqlalchemy import text

from arga_tenancy import UserFromHeader
from kernel.capabilities import router as capabilities_router
from kernel.db import engine
from kernel.desktop import router as desktop_router
from kernel.entities import router as entities_router
from kernel.events import router as events_router
from kernel.modules import router as modules_router
from kernel.notifications import loop as notifications_loop
from kernel.notifications import router as notifications_router
from kernel.preferences import router as preferences_router
from kernel.resolution import router as resolution_router
from kernel.spaces import router as spaces_router
from kernel.tools import router as tools_router
from kernel.ui import router as ui_router
from kernel.users import router as users_router
from kernel.wallpapers import router as wallpapers_router

SERVICE = "kernel"


@asynccontextmanager
async def lifespan(app: FastAPI):
    sender = (
        asyncio.create_task(notifications_loop()) if os.environ.get("NOTIFY", "1") == "1" else None
    )
    yield
    if sender is not None:
        sender.cancel()
    await engine().dispose()


app = FastAPI(title="OpenArga kernel", lifespan=lifespan)
app.add_middleware(UserFromHeader)
app.include_router(events_router)
app.include_router(entities_router)
app.include_router(resolution_router)
app.include_router(modules_router)
app.include_router(ui_router)
app.include_router(desktop_router)
app.include_router(tools_router)
app.include_router(wallpapers_router)
app.include_router(users_router)
app.include_router(preferences_router)
app.include_router(spaces_router)
app.include_router(capabilities_router)
app.include_router(notifications_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> dict[str, str]:
    return {"service": SERVICE, "version": os.environ.get("APP_VERSION", "dev")}


@app.get("/readyz")
async def readyz(response: Response) -> dict[str, str]:
    try:
        async with engine().connect() as connection:
            revision = (
                await connection.scalar(text("select version_num from alembic_version"))
            ) or "none"
    except Exception as error:  # noqa: BLE001 - cualquier fallo de dependencia es "no listo"
        response.status_code = 503
        return {"status": "not ready", "detail": type(error).__name__}
    return {"status": "ready", "revision": revision}
