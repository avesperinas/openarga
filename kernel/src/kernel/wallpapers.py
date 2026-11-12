from __future__ import annotations

import asyncio
import hashlib
import io
import json
import secrets
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Path, Response, UploadFile
from PIL import Image, ImageFilter, ImageOps
from pillow_heif import register_heif_opener
from pydantic import BaseModel, Field
from sqlalchemy import text

from arga_tenancy import require_person
from kernel.db import engine
from kernel.subject import SUBJECT_HEADER, subject_of

router = APIRouter(tags=["ui"])


FLOOR = 4.5
MUTED_FLOOR = 3.0
VEIL_MAX = 0.35
GRID = 64
THEMES: dict[str, dict[str, str]] = {
    "light": {"fg": "#10131a", "muted": "#5b6272", "scrim": "#eef1f6", "glass": "#ffffff"},
    "dark": {"fg": "#f2f4f8", "muted": "#a2aabb", "scrim": "#0b0e14", "glass": "#161c2a"},
}


MAX_BYTES = 20 * 1024 * 1024
MAX_SIDE = 2560
BLUR_SIDE = 480
BLUR_RATIO = 0.06
FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "HEIF"}
SIDES = (360, 720, 1280, 1920, 2560)
MODERN: dict[str, tuple[str, str, dict[str, Any]]] = {
    "avif": ("AVIF", "image/avif", {"quality": 55, "speed": 8}),
    "webp": ("WEBP", "image/webp", {"quality": 78, "method": 4}),
}
VARIANT_PATTERN = r"^(image|blurred|(avif|webp)-[0-9]{2,4})$"

register_heif_opener(thumbnails=False, depth_images=False, aux_images=False)


WRITE = text("""
    insert into kernel.ui_wallpapers
        (id, variant, subject, content_type, bytes, width, height, measured)
    values (:id, :variant, :subject, :content_type, :bytes, :width, :height,
            cast(:measured as jsonb))
""")

WRITE_VARIANT = text("""
    insert into kernel.ui_wallpapers
        (id, variant, subject, content_type, bytes, width, height, measured)
    values (:id, :variant, :subject, :content_type, :bytes, :width, :height,
            cast(:measured as jsonb))
    on conflict do nothing
""")

READ = text("""
    select content_type, bytes
    from kernel.ui_wallpapers
    where id = :id and variant = :variant and subject = :subject
""")

MINE = text("""
    select i.id, i.measured,
           case when coalesce(jsonb_typeof(i.measured->'glass'), 'null') = 'null'
                then b.bytes end as soft
    from kernel.ui_wallpapers i
    left join kernel.ui_wallpapers b
      on b.id = i.id and b.subject = i.subject and b.variant = 'blurred'
    where i.subject = :subject and i.variant = 'image'
    order by i.created_at desc
""")

COMPLETE = text("""
    update kernel.ui_wallpapers set measured = measured || cast(:extra as jsonb)
    where id = :id and subject = :subject
""")

FRAME = text("""
    update kernel.ui_wallpapers
    set measured = jsonb_set(measured, '{focus}', cast(:focus as jsonb))
    where id = :id and subject = :subject
    returning measured
""")

FORGET = text("delete from kernel.ui_wallpapers where id = :id and subject = :subject")


def rgb(value: str) -> tuple[float, float, float]:
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def luminance(colour: tuple[float, float, float]) -> float:

    def channel(value: float) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = colour
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def over(
    source: tuple[float, float, float], backdrop: tuple[float, float, float], alpha: float
) -> tuple[float, float, float]:
    return tuple(s * alpha + b * (1 - alpha) for s, b in zip(source, backdrop, strict=True))


def samples(image: Image.Image, grid: int = GRID) -> list[tuple[float, float, float]]:
    reduced = image.convert("RGB").resize((grid, grid), Image.Resampling.BOX)
    raw = reduced.tobytes()
    return [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]


def weakest(
    front: float, points: list[tuple[float, float, float]], tint, alpha: float, floor: float
) -> float:
    worst = float("inf")
    for point in points:
        mixed = luminance(over(tint, point, alpha))
        high, low = (front, mixed) if front > mixed else (mixed, front)
        value = (high + 0.05) / (low + 0.05)
        if value < worst:
            worst = value
            if worst < floor:
                return worst
    return worst


def alpha_for(
    points: list[tuple[float, float, float]], tint: str, needs: list[tuple[str, float]]
) -> dict[str, float]:
    colour = rgb(tint)
    fronts = [(luminance(rgb(colour_of)), floor) for colour_of, floor in needs]
    worst = 0.0
    for step in range(101):
        alpha = step / 100
        results = [weakest(front, points, colour, alpha, floor) for front, floor in fronts]
        worst = results[0]
        if all(value >= floor for value, (_, floor) in zip(results, fronts, strict=True)):
            return {"alpha": round(alpha, 2), "worst": round(worst, 2)}
    return {"alpha": 1.0, "worst": round(worst, 2)}


def measure(image: Image.Image) -> dict[str, Any]:
    points = samples(image)
    values = [luminance(point) for point in points]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)

    scrim = {
        theme: alpha_for(points, spec["scrim"], [(spec["fg"], FLOOR)])
        for theme, spec in THEMES.items()
    }
    glass = {
        theme: alpha_for(points, spec["glass"], [(spec["fg"], FLOOR), (spec["muted"], MUTED_FLOOR)])
        for theme, spec in THEMES.items()
    }

    return {
        "luminance": {"mean": round(mean, 4), "variance": round(variance, 5)},
        "scrim": {theme: solved["alpha"] for theme, solved in scrim.items()},
        "veil": {theme: min(solved["alpha"], VEIL_MAX) for theme, solved in scrim.items()},
        "glass": {theme: solved["alpha"] for theme, solved in glass.items()},
        "contrast": {theme: solved["worst"] for theme, solved in scrim.items()},
    }


def normalise(raw: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as error:
        raise HTTPException(status_code=415, detail="no se pudo decodificar la imagen") from error

    if image.format not in FORMATS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"formato {image.format or 'desconocido'} no aceptado; "
                f"se aceptan {', '.join(sorted(FORMATS))}"
            ),
        )

    image = ImageOps.exif_transpose(image) or image
    return image.convert("RGB")


def encoded(image: Image.Image, side: int, quality: int) -> tuple[bytes, int, int]:
    copy = image.copy()
    copy.thumbnail((side, side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue(), copy.width, copy.height


def blurred(image: Image.Image) -> tuple[bytes, int, int]:
    copy = image.copy()
    copy.thumbnail((BLUR_SIDE, BLUR_SIDE), Image.Resampling.LANCZOS)
    copy = copy.filter(ImageFilter.GaussianBlur(radius=max(copy.size) * BLUR_RATIO))
    buffer = io.BytesIO()
    copy.save(buffer, format="JPEG", quality=72, optimize=True)
    return buffer.getvalue(), copy.width, copy.height


@dataclass(frozen=True)
class Variant:
    name: str
    content_type: str
    payload: bytes
    width: int
    height: int


def variants(image: Image.Image) -> list[Variant]:
    biggest = max(image.size)
    sides = [side for side in SIDES if side <= biggest] or [SIDES[0]]
    made: list[Variant] = []
    for side in sides:
        copy = image.copy()
        copy.thumbnail((side, side), Image.Resampling.LANCZOS)
        for name, (fmt, content_type, options) in MODERN.items():
            buffer = io.BytesIO()
            copy.save(buffer, format=fmt, **options)
            made.append(
                Variant(f"{name}-{side}", content_type, buffer.getvalue(), copy.width, copy.height)
            )
    return made


class Source(BaseModel):
    type: str
    srcset: str


def sources_of(identifier: str, made: list[Variant]) -> tuple[list[Source], str]:
    sources = [
        Source(
            type=content_type,
            srcset=", ".join(
                f"/api/kernel/ui/wallpapers/{identifier}/{one.name} {one.width}w"
                for one in made
                if one.content_type == content_type
            ),
        )
        for _fmt, content_type, _options in MODERN.values()
    ]
    smallest = min(
        (one for one in made if one.content_type == "image/webp"), key=lambda one: one.width
    )
    return sources, f"/api/kernel/ui/wallpapers/{identifier}/{smallest.name}"


class Focus(BaseModel):
    x: Annotated[float, Field(ge=0, le=1)] = 0.5
    y: Annotated[float, Field(ge=0, le=1)] = 0.5


class Uploaded(BaseModel):
    id: str
    name: str
    luminance: dict[str, float]
    scrim: dict[str, float]
    veil: dict[str, float] | None = None
    glass: dict[str, float] | None = None
    contrast: dict[str, float]
    focus: Focus | None = None
    image: str
    blurred: str
    sources: list[Source] | None = None
    thumb: str | None = None
    aspect: float | None = None


class Framing(BaseModel):
    focus: Focus


def as_entry(identifier: str, measured: dict[str, Any]) -> Uploaded:
    return Uploaded(
        id=identifier,
        name="Tuyo",
        luminance=measured["luminance"],
        scrim=measured["scrim"],
        veil=measured["veil"],
        glass=measured["glass"],
        contrast=measured["contrast"],
        image=f"/api/kernel/ui/wallpapers/{identifier}/image",
        blurred=f"/api/kernel/ui/wallpapers/{identifier}/blurred",
    )


def completed(entry: Uploaded, soft: bytes | None) -> Uploaded:
    if entry.veil is None:
        entry.veil = {theme: min(alpha, VEIL_MAX) for theme, alpha in entry.scrim.items()}
    if entry.glass is None:
        entry.glass = {theme: 1.0 for theme in THEMES}
        if soft:
            try:
                points = samples(Image.open(io.BytesIO(soft)))
                entry.glass = {
                    theme: alpha_for(
                        points,
                        spec["glass"],
                        [(spec["fg"], FLOOR), (spec["muted"], MUTED_FLOOR)],
                    )["alpha"]
                    for theme, spec in THEMES.items()
                }
            except Exception:  # noqa: BLE001 - sin desenfocada legible, el cristal va opaco
                pass
    return entry


@dataclass(frozen=True)
class Prepared:
    entry: Uploaded
    full: Variant
    soft: Variant
    variants: list[Variant]


def prepared(raw: bytes, identifier: str) -> Prepared:
    image = normalise(raw)
    measured = measure(image)
    full = Variant("image", "image/jpeg", *encoded(image, MAX_SIDE, 82))
    soft = Variant("blurred", "image/jpeg", *blurred(image))
    made = variants(image)
    entry = as_entry(identifier, measured)
    entry.sources, entry.thumb = sources_of(identifier, made)
    entry.aspect = round(full.width / full.height, 3)
    return Prepared(entry, full, soft, made)


BACKFILLS: dict[str, asyncio.Task[None]] = {}


async def backfill(entry: Uploaded, who: str) -> None:
    try:
        async with engine().connect() as connection:
            row = (
                await connection.execute(READ, {"id": entry.id, "variant": "image", "subject": who})
            ).first()
        if row is None:
            return

        def make() -> tuple[list[Variant], list[Source], str, float]:
            with Image.open(io.BytesIO(row.bytes)) as opened:
                made = variants(opened.convert("RGB"))
                aspect = round(opened.width / opened.height, 3)
            return made, *sources_of(entry.id, made), aspect

        made, sources, thumb, aspect = await asyncio.to_thread(make)
        extra = {
            "veil": entry.veil,
            "glass": entry.glass,
            "sources": [source.model_dump() for source in sources],
            "thumb": thumb,
            "aspect": aspect,
        }
        async with engine().begin() as connection:
            for variant in made:
                await connection.execute(
                    WRITE_VARIANT,
                    {
                        "id": entry.id,
                        "variant": variant.name,
                        "subject": who,
                        "content_type": variant.content_type,
                        "bytes": variant.payload,
                        "width": variant.width,
                        "height": variant.height,
                        "measured": "{}",
                    },
                )
            await connection.execute(
                COMPLETE, {"id": entry.id, "subject": who, "extra": json.dumps(extra)}
            )
    except Exception as error:  # noqa: BLE001 - un relleno que falla no rompe la lista
        print(f"fondo {entry.id} sin variantes: {type(error).__name__}", flush=True)
    finally:
        BACKFILLS.pop(entry.id, None)


@router.post("/ui/wallpapers", status_code=201)
async def upload(
    file: UploadFile,
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Uploaded:
    require_person()
    who = subject_of(subject)

    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"la imagen pasa de {MAX_BYTES // (1024 * 1024)} MB",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="no llegó ninguna imagen")

    identifier = secrets.token_urlsafe(12)
    made = await asyncio.to_thread(prepared, raw, identifier)
    entry = made.entry

    async with engine().begin() as connection:
        for variant in (made.full, made.soft, *made.variants):
            await connection.execute(
                WRITE,
                {
                    "id": identifier,
                    "variant": variant.name,
                    "subject": who,
                    "content_type": variant.content_type,
                    "bytes": variant.payload,
                    "width": variant.width,
                    "height": variant.height,
                    "measured": entry.model_dump_json(),
                },
            )

    return entry


@router.get("/ui/wallpapers")
async def mine(
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> list[Uploaded]:
    who = subject_of(subject)
    async with engine().connect() as connection:
        rows = (await connection.execute(MINE, {"subject": who})).all()
    entries = []
    for row in rows:
        entry = completed(Uploaded.model_validate(row.measured), row.soft)
        if entry.sources is None and entry.id not in BACKFILLS:
            BACKFILLS[entry.id] = asyncio.create_task(backfill(entry.model_copy(), who))
        entries.append(entry)
    return entries


@router.patch("/ui/wallpapers/{identifier}")
async def frame(
    identifier: Annotated[str, Path()],
    framing: Framing,
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Uploaded:
    require_person()
    who = subject_of(subject)
    async with engine().begin() as connection:
        rows = (
            await connection.execute(
                FRAME,
                {"id": identifier, "subject": who, "focus": framing.focus.model_dump_json()},
            )
        ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="ese fondo no existe")
    return completed(Uploaded.model_validate(rows[0].measured), None)


@router.get("/ui/wallpapers/{identifier}/{variant}")
async def serve(
    identifier: Annotated[str, Path()],
    variant: Annotated[str, Path(pattern=VARIANT_PATTERN)],
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Response:
    who = subject_of(subject)
    async with engine().connect() as connection:
        row = (
            await connection.execute(READ, {"id": identifier, "variant": variant, "subject": who})
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="ese fondo no existe")

    return Response(
        content=row.bytes,
        media_type=row.content_type,
        headers={
            "cache-control": "private, max-age=31536000, immutable",
            "etag": f'"{hashlib.sha256(row.bytes).hexdigest()[:32]}"',
        },
    )


@router.delete("/ui/wallpapers/{identifier}", status_code=204)
async def forget(
    identifier: Annotated[str, Path()],
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Response:
    who = subject_of(subject)
    async with engine().begin() as connection:
        await connection.execute(FORGET, {"id": identifier, "subject": who})
    return Response(status_code=204)
