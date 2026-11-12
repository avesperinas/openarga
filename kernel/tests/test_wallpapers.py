from __future__ import annotations

import io
import json
import math
import re
from pathlib import Path

import pytest
from PIL import Image

from kernel.wallpapers import (
    BLUR_SIDE,
    FLOOR,
    FORMATS,
    GRID,
    MAX_BYTES,
    MUTED_FLOOR,
    THEMES,
    VEIL_MAX,
    Uploaded,
    blurred,
    completed,
    contrast,
    encoded,
    measure,
    normalise,
    over,
    rgb,
    samples,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "packages/ui/wallpapers.json").read_text())


def parse_svg(name: str) -> tuple[tuple[int, int, int], list[dict]]:
    svg = (ROOT / f"shell/public/wallpapers/{name}.svg").read_text()

    base = re.search(r'<rect width="\d+" height="\d+" fill="(#[0-9a-f]{6})"/>', svg)
    assert base, f"{name}.svg no declara color base"

    blobs = []
    for gradient in re.finditer(
        r'<radialGradient id="b\d+" cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)">\s*'
        r'<stop offset="0" stop-color="(#[0-9a-f]{6})" stop-opacity="([\d.]+)"/>',
        svg,
    ):
        cx, cy, radius, colour, alpha = gradient.groups()
        blobs.append(
            {
                "cx": float(cx),
                "cy": float(cy),
                "r": float(radius),
                "colour": colour,
                "alpha": float(alpha),
            }
        )

    assert blobs, f"{name}.svg no declara ninguna mancha"
    return _rgb(base.group(1)), blobs


def _rgb(value: str) -> tuple[int, int, int]:
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def render(name: str, side: int = GRID) -> Image.Image:
    base, blobs = parse_svg(name)
    image = Image.new("RGB", (side, side))
    pixels = image.load()
    assert pixels is not None

    for row in range(side):
        for column in range(side):
            x = (column + 0.5) / side
            y = (row + 0.5) / side
            colour = [float(channel) for channel in base]
            for blob in blobs:
                distance = math.hypot(x - blob["cx"], y - blob["cy"]) / blob["r"]
                if distance >= 1:
                    continue
                alpha = blob["alpha"] * (1 - distance)
                source = _rgb(blob["colour"])
                colour = [s * alpha + c * (1 - alpha) for s, c in zip(source, colour, strict=True)]
            pixels[column, row] = tuple(round(channel) for channel in colour)

    return image


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda entry: entry["id"])
def test_python_mide_lo_mismo_que_javascript(entry: dict) -> None:
    measured = measure(render(entry["id"]))

    assert measured["scrim"] == entry["scrim"]
    assert measured["veil"] == entry["veil"]
    for theme in ("light", "dark"):
        assert measured["glass"][theme] == pytest.approx(entry["glass"][theme], abs=0.011)

    for theme in ("light", "dark"):
        assert measured["contrast"][theme] == pytest.approx(entry["contrast"][theme], abs=0.05)
        assert measured["contrast"][theme] >= 4.5


def solid(colour: tuple[int, int, int], side: int = 256) -> Image.Image:
    return Image.new("RGB", (side, side), colour)


def as_bytes(image: Image.Image, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def weakest(image: Image.Image, colour: str, fg: str, alpha: float) -> float:
    tint, front = rgb(colour), rgb(fg)
    return min(contrast(front, over(tint, point, alpha)) for point in samples(image))


def half_white() -> Image.Image:
    image = Image.new("RGB", (GRID, GRID), (110, 110, 110))
    pixels = image.load()
    assert pixels is not None
    for row in range(GRID):
        for column in range(GRID // 2):
            pixels[column, row] = (255, 255, 255)
    return image


@pytest.mark.parametrize(
    "image",
    [
        solid((255, 255, 255)),
        solid((0, 0, 0)),
        solid((245, 247, 250)),
        solid((122, 128, 140)),
        half_white(),
    ],
    ids=["blanco", "negro", "nieve", "gris", "medio-blanco"],
)
def test_ninguna_foto_se_rechaza_y_lo_escrito_encima_se_lee(image: Image.Image) -> None:
    measured = measure(image)

    assert "rejected" not in measured
    for theme, spec in THEMES.items():
        assert weakest(image, spec["scrim"], spec["fg"], measured["scrim"][theme]) >= FLOOR
        assert weakest(image, spec["glass"], spec["fg"], measured["glass"][theme]) >= FLOOR
        assert weakest(image, spec["glass"], spec["muted"], measured["glass"][theme]) >= MUTED_FLOOR
        assert measured["veil"][theme] == min(measured["scrim"][theme], VEIL_MAX)


def test_el_peor_punto_manda_sobre_la_media() -> None:
    half, white, grey = (
        measure(image)["scrim"]["dark"]
        for image in (half_white(), solid((255, 255, 255)), solid((110, 110, 110)))
    )

    assert half == white
    assert half > grey


def test_un_fondo_de_antes_se_completa_al_leerlo() -> None:
    soft, _, _ = blurred(solid((255, 255, 255), side=128))
    old = Uploaded(
        id="x",
        name="Tuyo",
        luminance={"mean": 1.0, "variance": 0.0},
        scrim={"light": 0.0, "dark": 0.55},
        contrast={"light": 19.0, "dark": 4.5},
        image="/i",
        blurred="/b",
    )

    entry = completed(old, soft)

    assert entry.veil == {"light": 0.0, "dark": VEIL_MAX}
    assert entry.glass is not None
    assert entry.glass["dark"] > 0.5
    assert completed(old.model_copy(update={"glass": None}), None).glass == {
        "light": 1.0,
        "dark": 1.0,
    }


def test_la_orientacion_exif_se_aplica_antes_de_medir() -> None:
    image = Image.new("RGB", (200, 100), (90, 90, 90))
    buffer = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    image.save(buffer, format="JPEG", exif=exif)

    straightened = normalise(buffer.getvalue())
    assert (straightened.width, straightened.height) == (100, 200)


def test_no_se_guarda_ni_un_byte_de_exif() -> None:
    image = Image.new("RGB", (400, 300), (100, 105, 110))
    buffer = io.BytesIO()
    exif = Image.Exif()
    exif[271] = "SyntheticCamera"
    exif[272] = "SyntheticModel"
    exif[34853] = {1: "N"}
    image.save(buffer, format="JPEG", exif=exif)

    payload, _, _ = encoded(normalise(buffer.getvalue()), 2560, 82)
    saved = Image.open(io.BytesIO(payload))

    assert not dict(saved.getexif())
    assert b"SyntheticCamera" not in payload


def test_la_version_desenfocada_sale_pequena_y_borrosa() -> None:
    image = render("marea", side=512)
    payload, width, height = blurred(image)

    assert max(width, height) <= BLUR_SIDE
    full, _, _ = encoded(image, 2560, 82)
    assert len(payload) < len(full)

    soft = Image.open(io.BytesIO(payload)).convert("L")
    pixels = soft.load()
    assert pixels is not None
    steepest = max(
        abs(pixels[x, y] - pixels[x + 1, y])
        for y in range(soft.height)
        for x in range(soft.width - 1)
    )
    assert steepest < 12


def test_una_foto_de_iphone_se_acepta_y_sale_como_jpeg_sin_exif() -> None:
    image = Image.new("RGB", (400, 300), (100, 105, 110))
    exif = Image.Exif()
    exif[271] = "SyntheticCamera"
    buffer = io.BytesIO()
    image.save(buffer, format="HEIF", exif=exif.tobytes())

    opened = normalise(buffer.getvalue())
    assert (opened.width, opened.height) == (400, 300)

    payload, _, _ = encoded(opened, 2560, 82)
    saved = Image.open(io.BytesIO(payload))
    assert saved.format == "JPEG"
    assert not dict(saved.getexif())
    assert b"SyntheticCamera" not in payload


def test_una_foto_de_iphone_se_gira_una_vez_y_no_dos() -> None:
    image = Image.new("RGB", (200, 100), (90, 90, 90))
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="HEIF", exif=exif.tobytes())

    straightened = normalise(buffer.getvalue())
    assert (straightened.width, straightened.height) == (100, 200)


def mpo(principal: Image.Image, *extra: Image.Image, exif: Image.Exif | None = None) -> bytes:
    buffer = io.BytesIO()
    options = {"exif": exif.tobytes()} if exif is not None else {}
    principal.save(buffer, format="MPO", save_all=True, append_images=list(extra), **options)
    return buffer.getvalue()


def test_un_jpeg_con_fotogramas_extra_se_acepta_y_se_queda_el_principal() -> None:
    exif = Image.Exif()
    exif[271] = "SyntheticCamera"
    raw = mpo(
        Image.new("RGB", (300, 200), (90, 100, 110)),
        Image.new("RGB", (150, 100), (250, 250, 250)),
        exif=exif,
    )
    assert Image.open(io.BytesIO(raw)).format == "MPO"

    opened = normalise(raw)
    assert (opened.width, opened.height) == (300, 200)
    assert opened.getpixel((10, 10)) == pytest.approx((90, 100, 110), abs=3)

    payload, _, _ = encoded(opened, 2560, 82)
    saved = Image.open(io.BytesIO(payload))
    assert saved.format == "JPEG"
    assert not dict(saved.getexif())
    assert b"SyntheticCamera" not in payload


def test_un_mpo_se_gira_con_su_orientacion() -> None:
    exif = Image.Exif()
    exif[274] = 6
    raw = mpo(
        Image.new("RGB", (200, 100), (90, 90, 90)),
        Image.new("RGB", (200, 100), (90, 90, 90)),
        exif=exif,
    )

    straightened = normalise(raw)
    assert (straightened.width, straightened.height) == (100, 200)


def test_solo_se_aceptan_los_formatos_de_la_lista() -> None:
    assert {"JPEG", "MPO", "PNG", "WEBP", "HEIF"} == FORMATS

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        normalise(as_bytes(solid((120, 120, 120)), fmt="BMP"))
    assert raised.value.status_code == 415

    with pytest.raises(HTTPException) as raised:
        normalise(b"esto no es una imagen")
    assert raised.value.status_code == 415


@pytest.fixture
async def api(database_url: str):
    from httpx import ASGITransport, AsyncClient

    from kernel.db import engine
    from kernel.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kernel",
        headers={"x-arga-subject": "sujeto-de-prueba"},
    ) as client:
        yield client
    await engine().dispose()


async def test_subes_una_foto_y_queda_puesta_con_sus_dos_versiones(api) -> None:
    payload = as_bytes(render("duna", side=256))

    created = await api.post("/ui/wallpapers", files={"file": ("fondo.jpg", payload, "image/jpeg")})
    assert created.status_code == 201, created.text

    entry = created.json()
    assert entry["contrast"]["dark"] >= 4.5
    assert entry["veil"]["light"] <= VEIL_MAX
    assert set(entry["glass"]) == {"light", "dark"}

    for variant in ("image", "blurred"):
        served = await api.get(f"/ui/wallpapers/{entry['id']}/{variant}")
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/jpeg"
        assert "immutable" in served.headers["cache-control"]
        assert "private" in served.headers["cache-control"]
        assert Image.open(io.BytesIO(served.content)).format == "JPEG"

    assert [item["id"] for item in (await api.get("/ui/wallpapers")).json()] == [entry["id"]]

    assert (await api.delete(f"/ui/wallpapers/{entry['id']}")).status_code == 204
    assert (await api.get("/ui/wallpapers")).json() == []
    assert (await api.get(f"/ui/wallpapers/{entry['id']}/image")).status_code == 404


async def test_una_foto_de_iphone_sube_por_el_mismo_camino(api) -> None:
    payload = as_bytes(render("duna", side=256), fmt="HEIF")

    created = await api.post(
        "/ui/wallpapers", files={"file": ("IMG_0001.HEIC", payload, "application/octet-stream")}
    )
    assert created.status_code == 201, created.text

    served = await api.get(f"/ui/wallpapers/{created.json()['id']}/image")
    assert served.headers["content-type"] == "image/jpeg"

    await api.delete(f"/ui/wallpapers/{created.json()['id']}")


async def test_un_mpo_sube_por_el_mismo_camino(api) -> None:
    payload = mpo(render("duna", side=256), render("marea", side=128))

    created = await api.post(
        "/ui/wallpapers", files={"file": ("IMG_0002.JPG", payload, "image/jpeg")}
    )
    assert created.status_code == 201, created.text

    served = await api.get(f"/ui/wallpapers/{created.json()['id']}/image")
    assert served.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(served.content)).size == (256, 256)

    await api.delete(f"/ui/wallpapers/{created.json()['id']}")


async def test_una_foto_de_nieve_se_acepta(api) -> None:
    payload = as_bytes(solid((250, 250, 250)))

    created = await api.post("/ui/wallpapers", files={"file": ("nieve.jpg", payload, "image/jpeg")})

    assert created.status_code == 201, created.text
    assert created.json()["scrim"]["dark"] > 0.55
    await api.delete(f"/ui/wallpapers/{created.json()['id']}")


async def test_lo_que_pasa_del_tope_se_rechaza_antes_de_abrirlo(api) -> None:
    payload = b"\0" * (MAX_BYTES + 1)

    refused = await api.post(
        "/ui/wallpapers", files={"file": ("enorme.jpg", payload, "image/jpeg")}
    )

    assert refused.status_code == 413
    assert "20 MB" in refused.json()["detail"]


async def test_el_encuadre_se_guarda_y_viaja_con_el_fondo(api) -> None:
    payload = as_bytes(render("marea", side=256))
    entry = (
        await api.post("/ui/wallpapers", files={"file": ("mio.jpg", payload, "image/jpeg")})
    ).json()
    assert entry["focus"] is None

    framed = await api.patch(f"/ui/wallpapers/{entry['id']}", json={"focus": {"x": 0.2, "y": 0.75}})

    assert framed.status_code == 200, framed.text
    assert framed.json()["focus"] == {"x": 0.2, "y": 0.75}
    listed = (await api.get("/ui/wallpapers")).json()
    assert listed[0]["focus"] == {"x": 0.2, "y": 0.75}
    outside = await api.patch(f"/ui/wallpapers/{entry['id']}", json={"focus": {"x": 1.5, "y": 0}})
    assert outside.status_code == 422
    ajeno = await api.patch(
        f"/ui/wallpapers/{entry['id']}",
        json={"focus": {"x": 0.5, "y": 0.5}},
        headers={"x-arga-subject": "otro-sujeto"},
    )
    assert ajeno.status_code == 404

    await api.delete(f"/ui/wallpapers/{entry['id']}")


async def test_el_fondo_de_otro_no_se_sirve(api) -> None:
    payload = as_bytes(render("marea", side=256))
    entry = (
        await api.post("/ui/wallpapers", files={"file": ("mio.jpg", payload, "image/jpeg")})
    ).json()

    ajeno = await api.get(
        f"/ui/wallpapers/{entry['id']}/image", headers={"x-arga-subject": "otro-sujeto"}
    )
    assert ajeno.status_code == 404

    await api.delete(f"/ui/wallpapers/{entry['id']}")


def wide() -> bytes:
    image = Image.linear_gradient("L").resize((3000, 2000)).convert("RGB")
    return as_bytes(image)


async def test_un_fondo_sale_por_ancho_en_avif_y_webp(api) -> None:
    entry = (
        await api.post("/ui/wallpapers", files={"file": ("ancho.jpg", wide(), "image/jpeg")})
    ).json()

    assert [source["type"] for source in entry["sources"]] == ["image/avif", "image/webp"]
    widths = [part.split(" ")[1] for part in entry["sources"][0]["srcset"].split(", ")]
    assert widths == ["360w", "720w", "1280w", "1920w", "2560w"]
    assert entry["thumb"].endswith("/webp-360")

    for variant, kind in (("avif-720", "image/avif"), ("webp-1280", "image/webp")):
        served = await api.get(f"/ui/wallpapers/{entry['id']}/{variant}")
        assert served.status_code == 200
        assert served.headers["content-type"] == kind
        assert "immutable" in served.headers["cache-control"]
        assert Image.open(io.BytesIO(served.content)).width == int(variant.split("-")[1])
    assert (await api.get(f"/ui/wallpapers/{entry['id']}/gif-720")).status_code == 422

    await api.delete(f"/ui/wallpapers/{entry['id']}")
    assert (await api.get(f"/ui/wallpapers/{entry['id']}/avif-720")).status_code == 404


async def test_una_foto_pequena_no_se_amplia(api) -> None:
    entry = (
        await api.post(
            "/ui/wallpapers",
            files={"file": ("mini.jpg", as_bytes(render("duna", side=256)), "image/jpeg")},
        )
    ).json()

    assert entry["sources"][1]["srcset"].endswith("/webp-360 256w")
    await api.delete(f"/ui/wallpapers/{entry['id']}")


async def test_un_fondo_de_antes_se_rellena_una_vez_y_la_lista_deja_de_traer_bytes(api) -> None:
    import asyncio

    from sqlalchemy import text

    from kernel import wallpapers
    from kernel.db import engine

    entry = (
        await api.post("/ui/wallpapers", files={"file": ("viejo.jpg", wide(), "image/jpeg")})
    ).json()
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "delete from kernel.ui_wallpapers where id = :id "
                "and variant not in ('image', 'blurred')"
            ),
            {"id": entry["id"]},
        )
        await connection.execute(
            text(
                "update kernel.ui_wallpapers set measured = measured - 'sources' - 'thumb' "
                "- 'glass' - 'veil' where id = :id"
            ),
            {"id": entry["id"]},
        )

    before = (await api.get("/ui/wallpapers")).json()[0]
    assert before["sources"] is None
    assert before["glass"] is not None
    await asyncio.gather(*wallpapers.BACKFILLS.values())

    after = (await api.get("/ui/wallpapers")).json()[0]
    assert after["sources"] == entry["sources"]
    assert after["glass"] == before["glass"]
    assert not wallpapers.BACKFILLS
    assert (await api.get(f"/ui/wallpapers/{entry['id']}/avif-1920")).status_code == 200
    async with engine().connect() as connection:
        soft = await connection.scalar(
            text(
                "select case when coalesce(jsonb_typeof(measured->'glass'), 'null') = 'null' "
                "then 1 end from kernel.ui_wallpapers where id = :id and variant = 'image'"
            ),
            {"id": entry["id"]},
        )
    assert soft is None

    await api.delete(f"/ui/wallpapers/{entry['id']}")
