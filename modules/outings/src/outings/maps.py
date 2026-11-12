from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"


def version(root: Path) -> str | None:
    try:
        return (root / "map" / "VERSION").read_text().strip() or None
    except OSError:
        return None


def serve(root: Path, asked: str, path: str) -> FileResponse:
    folder = (root / "map").resolve()
    candidate = (folder / path).resolve()
    if not path or not candidate.is_relative_to(folder) or not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"no existe: {path}")
    current = version(root)
    cache = IMMUTABLE if current is not None and asked == current else REVALIDATE
    return FileResponse(candidate, headers={"cache-control": cache})
