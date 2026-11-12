from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import re
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from kernel.manifests import load_all
from kernel.modules import modules_path
from kernel.provision import reader_for, role_for

DEFAULT_KERNEL_USER = "arga_kernel"
AUTH_USER = "arga_auth"
AUTH_SCHEMA = "auth"
BACKUP_USER = "arga_backup"
LOGIN_PREFIX = "svc_"
SCRAM_ITERATIONS = 4096
ROLE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


def login_for(module_id: str) -> str:
    return f"{LOGIN_PREFIX}{module_id}"


def password_variable(module_id: str) -> str:
    return f"{module_id.upper()}_DB_PASSWORD"


def scram_verifier(
    password: str, salt: bytes | None = None, iterations: int = SCRAM_ITERATIONS
) -> str:
    salt = salt if salt is not None else secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    encode = lambda raw: base64.b64encode(raw).decode("ascii")  # noqa: E731
    return f"SCRAM-SHA-256${iterations}:{encode(salt)}${encode(stored_key)}:{encode(server_key)}"


def verifies(password: str, stored: str | None) -> bool:
    match = re.fullmatch(r"SCRAM-SHA-256\$(\d+):([^$]+)\$([^:]+):(.+)", stored or "")
    if not match:
        return False
    iterations, salt = int(match.group(1)), base64.b64decode(match.group(2))
    return hmac.compare_digest(scram_verifier(password, salt, iterations), stored)


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        self.lines.append(line)


def _quote_ident(name: str) -> str:
    if not ROLE_NAME.fullmatch(name):
        raise ValueError(f"nombre de rol inválido: {name!r}")
    return f'"{name}"'


async def _role_exists(connection: AsyncConnection, name: str) -> bool:
    return bool(
        await connection.scalar(
            text("select 1 from pg_roles where rolname = :name"), {"name": name}
        )
    )


async def _ensure_login(
    connection: AsyncConnection, name: str, password: str, attributes: str, report: Report
) -> None:
    role = _quote_ident(name)
    if await _role_exists(connection, name):
        await connection.execute(text(f"alter role {role} {attributes}"))
        stored = await connection.scalar(
            text("select rolpassword from pg_authid where rolname = :name"), {"name": name}
        )
        if verifies(password, stored):
            report.say(f"sin cambios  {name}")
            return
        action = "contraseña   "
    else:
        await connection.execute(text(f"create role {role} {attributes}"))
        action = "creado       "
    verifier = scram_verifier(password).replace("'", "''")
    await connection.exec_driver_sql(f"alter role {role} password '{verifier}'")
    report.say(f"{action}{name}")


TRANSFERABLE = text("""
    select format('%s %s', kind, object) as target
    from (
        select n.nspname as schema_name,
               case c.relkind
                   when 'S' then 'sequence'
                   when 'v' then 'view'
                   when 'm' then 'materialized view'
                   when 'f' then 'foreign table'
                   else 'table'
               end as kind,
               c.oid::regclass::text as object
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where c.relkind in ('r', 'p', 'v', 'm', 'f', 'S')
          and c.relowner = (select oid from pg_roles where rolname = current_user)
          -- Una secuencia de identidad cambia de dueño con su tabla; tocarla aparte es un error.
          and not exists (
              select 1 from pg_depend d
              where d.objid = c.oid and d.classid = 'pg_class'::regclass and d.deptype in ('a', 'i')
          )
        union all
        select n.nspname, 'function', p.oid::regprocedure::text
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where p.proowner = (select oid from pg_roles where rolname = current_user)
    ) owned
    where schema_name = any(:schemas)
       or object = 'alembic_version'
    order by target
""")


async def _transfer_ownership(
    connection: AsyncConnection, kernel_user: str, schemas: list[str], report: Report
) -> None:
    role = _quote_ident(kernel_user)
    for schema in schemas:
        owned_by_admin = await connection.scalar(
            text(
                "select 1 from pg_namespace where nspname = :schema "
                "and nspowner = (select oid from pg_roles where rolname = current_user)"
            ),
            {"schema": schema},
        )
        if owned_by_admin:
            await connection.execute(text(f'alter schema "{schema}" owner to {role}'))
            report.say(f"propiedad    schema {schema}")

    targets = (await connection.execute(TRANSFERABLE, {"schemas": schemas})).scalars().all()
    for target in targets:
        await connection.execute(text(f"alter {target} owner to {role}"))
    if targets:
        report.say(f"propiedad    {len(targets)} objeto(s) de {', '.join(schemas)}")


async def bootstrap(
    connection: AsyncConnection,
    kernel_user: str,
    kernel_password: str,
    module_passwords: dict[str, str | None],
    auth_password: str | None = None,
    backup_password: str | None = None,
) -> Report:
    report = Report()

    if not await connection.scalar(
        text("select rolsuper from pg_roles where rolname = current_user")
    ):
        raise PermissionError(
            "kernel.roles necesita una conexión de superusuario en ADMIN_DATABASE_URL"
        )

    await _ensure_login(
        connection,
        kernel_user,
        kernel_password,
        "login nosuperuser createrole nocreatedb noreplication nobypassrls inherit",
        report,
    )
    database = await connection.scalar(text("select current_database()"))
    await connection.execute(
        text(f'grant connect, create on database "{database}" to {_quote_ident(kernel_user)}')
    )
    await connection.execute(
        text(f"grant usage, create on schema public to {_quote_ident(kernel_user)}")
    )

    module_ids = sorted(module_passwords)
    await _transfer_ownership(connection, kernel_user, ["kernel", *module_ids], report)

    for module_id in module_ids:
        module_role = role_for(module_id)
        for granted in (module_role, reader_for(module_id)):
            if await _role_exists(connection, granted):
                await connection.execute(
                    text(
                        f"grant {_quote_ident(granted)} to {_quote_ident(kernel_user)} "
                        "with admin true, set true, inherit false"
                    )
                )

        password = module_passwords[module_id]
        login = login_for(module_id)
        if not password:
            report.say(f"sin login    {login}: falta {password_variable(module_id)}")
            continue
        await _ensure_login(
            connection,
            login,
            password,
            "login nosuperuser nocreaterole nocreatedb noreplication nobypassrls inherit",
            report,
        )
        if await _role_exists(connection, module_role):
            await connection.execute(
                text(f"grant {_quote_ident(module_role)} to {_quote_ident(login)}")
            )

    if auth_password:
        await _ensure_login(
            connection,
            AUTH_USER,
            auth_password,
            "login nosuperuser nocreaterole nocreatedb noreplication nobypassrls inherit",
            report,
        )
        owner = _quote_ident(AUTH_USER)
        await connection.execute(
            text(f'create schema if not exists "{AUTH_SCHEMA}" authorization {owner}')
        )
        await connection.execute(text(f'alter schema "{AUTH_SCHEMA}" owner to {owner}'))
    else:
        report.say(f"sin login    {AUTH_USER}: falta AUTH_DB_PASSWORD")

    if backup_password:
        await _ensure_login(
            connection,
            BACKUP_USER,
            backup_password,
            "login nosuperuser nocreaterole nocreatedb noreplication bypassrls inherit",
            report,
        )
        await connection.execute(text(f"grant pg_read_all_data to {_quote_ident(BACKUP_USER)}"))
    else:
        report.say(f"sin login    {BACKUP_USER}: falta BACKUP_DB_PASSWORD")

    return report


MODULE_PASSWORD = re.compile(r"^([A-Z][A-Z0-9_]*)_DB_PASSWORD$")
NOT_MODULES = {"KERNEL", "AUTH", "POSTGRES", "ADMIN", "BACKUP"}


def declared_modules(environment: dict[str, str] | None = None) -> dict[str, str]:
    found: dict[str, str] = {}
    for name, value in (environment or os.environ).items():
        match = MODULE_PASSWORD.match(name)
        if not match or match.group(1) in NOT_MODULES or not value:
            continue
        module_id = match.group(1).lower()
        if ROLE_NAME.match(module_id):
            found[module_id] = value
    return found


def _passwords(root: Path) -> dict[str, str | None]:
    passwords: dict[str, str | None] = dict(declared_modules())
    for manifest in load_all(root) if root.is_dir() else []:
        passwords.setdefault(manifest.id, os.environ.get(password_variable(manifest.id)))
    return passwords


async def _run(admin_url: str, kernel_user: str, kernel_password: str, root: Path) -> Report:
    auth_password = os.environ.get("AUTH_DB_PASSWORD") or None
    backup_password = os.environ.get("BACKUP_DB_PASSWORD") or None
    passwords = _passwords(root)
    engine = create_async_engine(admin_url)
    try:
        async with engine.begin() as connection:
            return await bootstrap(
                connection,
                kernel_user,
                kernel_password,
                passwords,
                auth_password,
                backup_password,
            )
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    root = Path(arguments[0]) if arguments else modules_path()

    admin_url = os.environ.get("ADMIN_DATABASE_URL", "").strip()
    kernel_user = os.environ.get("KERNEL_DB_USER", DEFAULT_KERNEL_USER).strip()
    kernel_password = os.environ.get("KERNEL_DB_PASSWORD", "")
    missing = [
        name
        for name, value in (
            ("ADMIN_DATABASE_URL", admin_url),
            ("KERNEL_DB_PASSWORD", kernel_password),
        )
        if not value
    ]
    if missing:
        print(f"roles: faltan {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        report = asyncio.run(_run(admin_url, kernel_user, kernel_password, root))
    except Exception as error:  # noqa: BLE001 - se traduce a un exit code, no se traga
        print(f"roles: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    for line in report.lines:
        print(f"roles  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
