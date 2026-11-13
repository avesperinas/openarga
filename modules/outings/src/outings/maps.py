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


def has_map(root: Path, area_id: str) -> bool:
    return (root / "map" / area_id / "region.pmtiles").is_file()


def _file(folder: Path, path: str) -> Path | None:
    head, _, rest = path.partition("/")
    tried = [path]
    if rest and (folder / head).is_dir():
        tried = [path, rest]
    for one in tried:
        candidate = (folder / one).resolve()
        if candidate.is_relative_to(folder) and candidate.is_file():
            return candidate
    return None


def serve(root: Path, asked: str, path: str) -> FileResponse:
    folder = (root / "map").resolve()
    found = _file(folder, path) if path else None
    if found is None:
        raise HTTPException(status_code=404, detail=f"not found: {path}")
    current = version(root)
    cache = IMMUTABLE if current is not None and asked == current else REVALIDATE
    return FileResponse(found, headers={"cache-control": cache})
