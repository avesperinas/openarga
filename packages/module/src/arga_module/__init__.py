from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

DEFAULT_MANIFEST = "/opt/module/manifest.yaml"
DEFAULT_SCHEMA = "/opt/module/schema"
DEFAULT_KERNEL = "http://kernel:8000"
TOKEN_HEADER = "x-module-token"


class RegistrationFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class Registration:
    module_id: str
    version: str
    applied: list[str]


def _read_manifest(path: Path) -> dict:
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest.get("id"):
        raise RegistrationFailed(f"{path} no es un manifiesto con id")
    return manifest


def _read_schema(directory: Path) -> list[dict[str, str]]:
    if not directory.is_dir():
        return []
    return [
        {"name": path.name, "sql": path.read_text(encoding="utf-8")}
        for path in sorted(directory.glob("*.sql"))
        if path.is_file()
    ]


def register(
    kernel_url: str,
    manifest_path: Path,
    schema_dir: Path,
    version: str,
    token: str,
    client: httpx.Client | None = None,
) -> Registration:
    manifest = _read_manifest(manifest_path)
    module_id = str(manifest["id"])
    body = {"manifest": manifest, "schema": _read_schema(schema_dir), "version": version}

    owned = client is None
    http = client or httpx.Client(timeout=30)
    try:
        response = http.put(
            f"{kernel_url.rstrip('/')}/internal/modules/{module_id}",
            json=body,
            headers={TOKEN_HEADER: token},
        )
    finally:
        if owned:
            http.close()

    if response.status_code != 200:
        raise RegistrationFailed(f"{response.status_code} · {response.text[:400]}")
    payload = response.json()
    return Registration(module_id, str(payload["version"]), list(payload.get("applied", [])))


def main(argv: list[str] | None = None) -> int:
    del argv
    kernel_url = os.environ.get("KERNEL_URL", DEFAULT_KERNEL)
    manifest_path = Path(os.environ.get("MANIFEST_PATH", DEFAULT_MANIFEST))
    schema_dir = Path(os.environ.get("SCHEMA_PATH", DEFAULT_SCHEMA))
    version = os.environ.get("APP_VERSION", "dev")
    token = os.environ.get("MODULE_REGISTRATION_TOKEN", "")

    if not token:
        print(
            "falta MODULE_REGISTRATION_TOKEN: sin él el kernel no acepta el registro",
            file=sys.stderr,
        )
        return 1

    last = ""
    for attempt in range(1, 6):
        try:
            done = register(kernel_url, manifest_path, schema_dir, version, token)
        except RegistrationFailed as error:
            last = str(error)
        except httpx.HTTPError as error:
            last = f"{type(error).__name__}: {error}"
        else:
            applied = ", ".join(done.applied) or "nada nuevo"
            print(f"registrado  {done.module_id} {done.version}  schema: {applied}")
            return 0
        print(f"registro fallido (intento {attempt}): {last}", file=sys.stderr)
        time.sleep(attempt * 2)

    print(f"no se pudo registrar en {kernel_url}: {last}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
