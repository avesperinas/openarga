from __future__ import annotations

import hashlib

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from notebook import markdown as md
from notebook.notes import Conflict, Invalid, NotFound

MAX_SIZE = 20 * 1024 * 1024

TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
    "svg": "image/svg+xml",
    "bmp": "image/bmp",
}


class FileOut(BaseModel):
    name: str
    content_type: str
    size: int
    existed: bool


def type_of(name: str) -> str | None:
    return TYPES.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None


def clean_name(name: str) -> str:
    clean = md.nfc(name).strip().rsplit("/", 1)[-1]
    if not clean or len(clean) > 200:
        raise Invalid("the file name is empty or longer than 200 characters")
    bad = md.FORBIDDEN.search(clean)
    if bad:
        raise Invalid(f"a file name cannot contain '{bad.group()}'")
    return clean


async def save(connection: AsyncConnection, name: str, data: bytes) -> FileOut:
    clean = clean_name(name)
    kind = type_of(clean)
    if kind is None:
        raise Invalid(f"'{clean}' is not an image Notebook can show")
    if not data:
        raise Invalid(f"'{clean}' is empty")
    if len(data) > MAX_SIZE:
        raise Invalid(f"'{clean}' is larger than 20 MB")
    digest = hashlib.sha256(data).hexdigest()
    found = (
        await connection.execute(
            text(
                "select sha256, content_type, size from notebook.notebook_file where name_key = :key"
            ),
            {"key": md.key(clean)},
        )
    ).first()
    if found is not None:
        if found.sha256 != digest:
            raise Conflict(f"there is already a different file '{clean}'")
        return FileOut(name=clean, content_type=found.content_type, size=found.size, existed=True)
    await connection.execute(
        text(
            "insert into notebook.notebook_file (name, name_key, content_type, size, content, sha256) "
            "values (:name, :key, :type, :size, :content, :sha)"
        ),
        {
            "name": clean,
            "key": md.key(clean),
            "type": kind,
            "size": len(data),
            "content": data,
            "sha": digest,
        },
    )
    return FileOut(name=clean, content_type=kind, size=len(data), existed=False)


async def read(connection: AsyncConnection, name: str) -> tuple[bytes, str, str]:
    found = (
        await connection.execute(
            text(
                "select content, content_type, sha256 from notebook.notebook_file where name_key = :key"
            ),
            {"key": md.key(name.rsplit("/", 1)[-1])},
        )
    ).first()
    if found is None:
        raise NotFound(f"file '{name}' not found")
    return bytes(found.content), found.content_type, found.sha256
