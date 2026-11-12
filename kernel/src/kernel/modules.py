from __future__ import annotations

import asyncio
import hmac
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel import isolation, rls, schemas
from kernel.backfill import backfill_module
from kernel.db import engine
from kernel.isolation import Isolation, ModuleNotProvisioned
from kernel.manifests import ADDRESSED, InvalidManifest, Manifest, load_all
from kernel.provision import MODULE_ID_PATTERN

router = APIRouter(tags=["modules"])

DEFAULT_MODULES_PATH = "modules"

UPSERT = text("""
    insert into kernel.modules (id, version, enabled, manifest, updated_at, registered_at)
    values (:id, :version, true, cast(:manifest as jsonb), now(), now())
    on conflict (id) do update
    set version = excluded.version,
        enabled = true,
        manifest = excluded.manifest,
        updated_at = now(),
        registered_at = now()
""")

DISABLE_STALE = text("""
    update kernel.modules
    set enabled = false, updated_at = now()
    where enabled and registered_at < now() - make_interval(days => :days)
    returning id
""")

DISABLE_MISSING = text("""
    update kernel.modules
    set enabled = false, updated_at = now()
    where enabled and id <> all(string_to_array(:ids, ','))
""")

LIST_MODULES = text("""
    select id, version, enabled, updated_at,
           manifest->>'name' as name,
           manifest->'database'->>'schema' as db_schema,
           manifest->'database'->>'role' as role,
           manifest->'api'->>'prefix' as api_prefix,
           manifest->'ui'->>'view' as view,
           manifest->'ui'->>'family' as family,
           manifest->'ui'->>'badge' as badge,
           manifest->'ui'->>'search' as search,
           coalesce(
               (select array_agg(distinct tool->>'scope' order by tool->>'scope')
                from jsonb_array_elements(manifest->'tools') as tool),
               '{}'
           ) as scopes,
           coalesce(
               (select jsonb_agg(connector->'credential')
                from jsonb_array_elements(coalesce(manifest->'connectors', '[]')) as connector
                where connector->'credential' is not null
                  and connector->'credential' <> 'null'::jsonb),
               '[]'
           ) as credentials,
           coalesce(manifest->'provides', '[]'::jsonb) as provides,
           coalesce(manifest->'uses', '[]'::jsonb) as uses
    from kernel.modules
    order by id
""")


class ModuleSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    version: str
    enabled: bool
    db_schema: str = Field(alias="schema")
    role: str
    api_prefix: str
    view: str | None = None
    family: str | None = None
    badge: str | None = None
    search: str | None = None
    scopes: list[str]
    credentials: list[dict[str, str]] = []
    provides: list[str] = []
    uses: list[str] = []
    updated_at: datetime


def modules_path() -> Path:
    return Path(os.environ.get("MODULES_PATH", DEFAULT_MODULES_PATH))


SERVED_ELSEWHERE = text("""
    select m.id, served
    from kernel.modules m,
         jsonb_array_elements_text(coalesce(m.manifest->'provides', '[]'::jsonb)) as served
    where m.enabled and m.id <> :id and served = any(cast(:provides as text[]))
    order by served
""")


class ServedElsewhere(Exception):
    pass


VIEW_TAKEN = text("""
    select m.id from kernel.modules m
    where m.enabled and m.id <> :id
      and (m.manifest->'ui'->>'view' = :view or '/' || m.id = :view
           or m.manifest->'ui'->>'view' = '/' || :id)
    order by m.id
""")


REGISTRATION_LOCK = text("select pg_advisory_xact_lock(hashtext('arga.module_registration'))")


async def register(
    connection: AsyncConnection,
    manifest: Manifest,
    version: str,
    files: Sequence[schemas.SchemaFile],
) -> None:
    await connection.execute(REGISTRATION_LOCK)
    alone = [service for service in manifest.provides if service not in ADDRESSED]
    if alone:
        taken = (
            await connection.execute(SERVED_ELSEWHERE, {"id": manifest.id, "provides": alone})
        ).all()
        if taken:
            raise ServedElsewhere(
                "; ".join(f"'{row.served}' ya lo sirve '{row.id}'" for row in taken)
            )
    clash = (
        (await connection.execute(VIEW_TAKEN, {"id": manifest.id, "view": manifest.ui.view}))
        .scalars()
        .all()
    )
    if clash:
        raise ServedElsewhere(f"la dirección '{manifest.ui.view}' choca con '{', '.join(clash)}'")
    await connection.execute(
        UPSERT,
        {
            "id": manifest.id,
            "version": version,
            "manifest": manifest.model_dump_json(by_alias=True),
        },
    )
    await connection.execute(
        text("select kernel.provision_module(:module_id)"), {"module_id": manifest.id}
    )
    moved = await backfill_module(connection, manifest.id)
    for table, rows in moved.items():
        print(f"dueño      {table}: {rows} fila(s) de antes de M5")
    await schemas.apply(connection, files, manifest.id)
    for table in await rls.enforce(connection, manifest.id):
        print(f"separado   {table}: cada persona ve lo suyo")


def heartbeat_days() -> int:
    return int(os.environ.get("MODULE_HEARTBEAT_DAYS", "7"))


async def disable_stale(connection: AsyncConnection, days: int) -> list[str]:
    return list((await connection.execute(DISABLE_STALE, {"days": days})).scalars())


async def sync(
    connection: AsyncConnection, manifests: list[Manifest], root: Path | None = None
) -> None:
    for manifest in manifests:
        if root is None:
            await connection.execute(
                UPSERT,
                {
                    "id": manifest.id,
                    "version": manifest.version,
                    "manifest": manifest.model_dump_json(by_alias=True),
                },
            )
            await connection.execute(
                text("select kernel.provision_module(:module_id)"), {"module_id": manifest.id}
            )
        else:
            await register(
                connection, manifest, manifest.version, schemas.from_disk(root, manifest.id)
            )
    await connection.execute(
        DISABLE_MISSING, {"ids": ",".join(manifest.id for manifest in manifests)}
    )


@router.get("/modules")
async def list_modules() -> list[ModuleSummary]:
    async with engine().connect() as connection:
        rows = (await connection.execute(LIST_MODULES)).all()
    return [
        ModuleSummary(
            id=row.id,
            name=row.name,
            version=row.version,
            enabled=row.enabled,
            db_schema=row.db_schema,
            role=row.role,
            api_prefix=row.api_prefix,
            view=row.view,
            family=row.family,
            badge=row.badge,
            search=row.search,
            scopes=list(row.scopes),
            credentials=list(row.credentials),
            provides=list(row.provides),
            uses=list(row.uses),
            updated_at=row.updated_at,
        )
        for row in rows
    ]


class SchemaFileIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[0-9a-z_]+\.sql$")]
    sql: str


INLETS = text("""
    select m.id as module, m.manifest->>'name' as name, m.manifest->'ui'->>'view' as view,
           inlet
    from kernel.modules m, jsonb_array_elements(coalesce(m.manifest->'inlets', '[]')) as inlet
    where m.enabled
    order by m.id, inlet->>'id'
""")


class InletSummary(BaseModel):
    key: str
    module: str
    name: str
    view: str | None = None
    id: str
    title: str
    contracts: list[str]
    settings: list[dict[str, Any]] = []


@router.get("/inlets")
async def list_inlets() -> list[InletSummary]:
    async with engine().connect() as connection:
        rows = (await connection.execute(INLETS)).all()
    return [
        InletSummary(
            key=f"{row.module}.{row.inlet['id']}",
            module=row.module,
            name=row.name,
            view=row.view,
            id=row.inlet["id"],
            title=row.inlet["title"],
            contracts=list(row.inlet.get("contracts") or []),
            settings=list(row.inlet.get("settings") or []),
        )
        for row in rows
    ]


class Registration(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    manifest: dict
    schema_files: list[SchemaFileIn] = Field(default_factory=list, alias="schema")
    version: Annotated[str, Field(min_length=1, max_length=60)]


class Registered(BaseModel):
    id: str
    version: str
    applied: list[str]


def registration_token() -> str:
    return os.environ.get("MODULE_REGISTRATION_TOKEN", "")


@router.put("/internal/modules/{module_id}")
async def register_module(
    module_id: Annotated[str, PathParam(pattern=MODULE_ID_PATTERN)],
    body: Registration,
    x_module_token: Annotated[str, Header()] = "",
) -> Registered:
    expected = registration_token()
    if not expected:
        raise HTTPException(status_code=503, detail="el kernel no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="token de registro inválido")

    try:
        manifest = Manifest.model_validate(body.manifest)
    except Exception as error:  # noqa: BLE001 - pydantic y el validador propio, misma respuesta
        raise HTTPException(status_code=422, detail=f"manifiesto inválido: {error}") from error
    if manifest.id != module_id:
        raise HTTPException(
            status_code=422, detail=f"el manifiesto es de '{manifest.id}', no de '{module_id}'"
        )

    files = [schemas.SchemaFile(file.name, file.sql) for file in body.schema_files]
    async with engine().begin() as connection:
        before = set((await connection.execute(schemas.APPLIED, {"module": module_id})).scalars())
        try:
            await register(connection, manifest, body.version, files)
        except (schemas.ChangedMigration, ServedElsewhere) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        after = set((await connection.execute(schemas.APPLIED, {"module": module_id})).scalars())
        for stale in await disable_stale(connection, heartbeat_days()):
            print(f"apagado    {stale}: lleva días sin registrarse")
    return Registered(id=module_id, version=body.version, applied=sorted(after - before))


@router.get("/modules/{module_id}/isolation")
async def module_isolation(
    module_id: Annotated[str, PathParam(pattern=MODULE_ID_PATTERN)],
) -> Isolation:
    async with engine().connect() as connection:
        try:
            return await isolation.describe(connection, module_id)
        except ModuleNotProvisioned as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


async def _sync_from_disk(root: Path) -> list[Manifest]:
    manifests = load_all(root)
    async with engine().begin() as connection:
        await sync(connection, manifests, root)
    await engine().dispose()
    return manifests


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    root = Path(arguments[0]) if arguments else modules_path()

    try:
        manifests = asyncio.run(_sync_from_disk(root))
    except InvalidManifest as error:
        print(f"manifiesto inválido · {error}", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001 - se traduce a un exit code, no se traga
        print(f"sincronización fallida: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    for manifest in manifests:
        print(f"registrado  {manifest.id} {manifest.version}  scopes={manifest.scopes or '[]'}")
    print(f"{len(manifests)} módulo(s) en kernel.modules desde {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
