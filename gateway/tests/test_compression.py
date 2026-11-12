import asyncio
import gzip
import zlib

import brotli
import httpx
import pytest
from conftest import USER, install_login, login_environment, session_cookie
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from gateway import compress, main
from gateway.session import COOKIE

upstream = FastAPI()
asked: dict[str, int] = {}
received: list[dict] = []

PAGE = ("<p>Hoy, sin nada pendiente.</p>" * 200).encode()
PHOTO = bytes(range(256)) * 16
TILE = b'\x1a\x8b\x01\n\x05roads\x12\x0c\x18\x02"\x08\t\x00\x00\x1a\x00\x00' * 200


@upstream.get("/modules")
async def modules() -> list[dict]:
    asked["modules"] = asked.get("modules", 0) + 1
    await asyncio.sleep(0.05)
    return [{"id": "demo", "enabled": True, "view": None}]


@upstream.post("/internal/users")
async def people() -> dict:
    asked["users"] = asked.get("users", 0) + 1
    await asyncio.sleep(0.05)
    return {"id": USER, "spaces": []}


@upstream.get("/page")
async def page(request: Request) -> Response:
    received.append(dict(request.headers))
    return Response(PAGE, media_type="text/html", headers={"etag": '"v1"'})


@upstream.get("/photo")
async def photo() -> Response:
    return Response(PHOTO, media_type="image/jpeg")


@upstream.get("/tile")
async def tile() -> Response:
    return Response(TILE, media_type="application/x-protobuf")


@upstream.get("/tiny")
async def tiny() -> dict:
    return {"ok": True}


@upstream.get("/events")
async def events() -> StreamingResponse:
    async def lines():
        yield b"data: " + b"x" * 2048 + b"\n\n"

    return StreamingResponse(lines(), media_type="text/event-stream")


@pytest.fixture
async def api(monkeypatch: pytest.MonkeyPatch):
    asked.clear()
    received.clear()
    login_environment(monkeypatch)
    monkeypatch.setattr(main, "module_url", lambda module_id: "http://demo")
    main.app.state.client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream), timeout=5.0
    )
    install_login(main.app, main.app.state.client)
    main.app.state.modules = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://arga",
        cookies={COOKIE: session_cookie()},
    ) as client:
        yield client
    await main.app.state.client.aclose()


async def raw(api, path: str, accept: str | None) -> httpx.Response:
    headers = {"accept-encoding": accept} if accept is not None else {}
    request = api.build_request("GET", path, headers=headers)
    response = await api.send(request, stream=True)
    response._content = b"".join([chunk async for chunk in response.aiter_raw()])
    return response


async def test_text_leaves_in_brotli_when_the_browser_takes_it(api) -> None:
    response = await raw(api, "/api/demo/page", "gzip, deflate, br, zstd")

    assert response.headers["content-encoding"] == "br"
    assert brotli.decompress(response.content) == PAGE
    assert "accept-encoding" in response.headers["vary"].lower()
    assert response.headers["etag"] == 'W/"v1"'


async def test_text_leaves_in_gzip_when_brotli_is_not_accepted(api) -> None:
    response = await raw(api, "/api/demo/page", "gzip")

    assert response.headers["content-encoding"] == "gzip"
    assert gzip.decompress(response.content) == PAGE


async def test_map_tiles_are_compressed_too(api) -> None:
    response = await raw(api, "/api/demo/tile", "gzip, br")

    assert response.headers["content-encoding"] == "br"
    assert brotli.decompress(response.content) == TILE
    assert len(response.content) < len(TILE) / 2


async def test_nothing_is_compressed_for_who_does_not_ask(api) -> None:
    response = await raw(api, "/api/demo/page", "identity")

    assert "content-encoding" not in response.headers
    assert response.content == PAGE
    assert response.headers["etag"] == '"v1"'


async def test_the_service_is_always_asked_for_the_plain_body(api) -> None:
    await raw(api, "/api/demo/page", "gzip, br")

    assert received[-1]["accept-encoding"] == "identity"


@pytest.mark.parametrize("path", ["/api/demo/photo", "/api/demo/tiny", "/api/demo/events"])
async def test_photos_small_answers_and_events_go_as_they_are(api, path: str) -> None:
    response = await raw(api, path, "gzip, br")

    assert "content-encoding" not in response.headers


async def test_a_head_has_no_body_to_compress(api) -> None:
    response = await api.head("/api/demo/page", headers={"accept-encoding": "br"})

    assert "content-encoding" not in response.headers


@pytest.mark.parametrize(
    ("accept", "chosen"),
    [
        ("gzip, deflate, br", "br"),
        ("br;q=0, gzip", "gzip"),
        ("gzip;q=0, br;q=0", None),
        ("*", "br"),
        ("identity", None),
        (None, None),
        ("br;q=nada, gzip", "gzip"),
    ],
)
def test_what_the_browser_accepts_decides(accept, chosen) -> None:
    assert compress.negotiate(accept) == chosen


@pytest.mark.parametrize("encoding", ["br", "gzip"])
async def test_each_piece_leaves_as_soon_as_it_arrives(encoding: str) -> None:
    second = asyncio.Event()

    async def pieces():
        yield b"<header>Hoy</header>"
        await second.wait()
        yield b"<main>tarjetas</main>"

    stream = compress.encoded(pieces(), encoding)
    first = await anext(stream)
    if encoding == "br":
        reader = brotli.Decompressor()
        assert reader.process(first) == b"<header>Hoy</header>"
    else:
        reader = zlib.decompressobj(16 + zlib.MAX_WBITS)
        assert reader.decompress(first) == b"<header>Hoy</header>"

    second.set()
    rest = b"".join([chunk async for chunk in stream])
    if encoding == "br":
        assert reader.process(rest) == b"<main>tarjetas</main>"
    else:
        assert reader.decompress(rest) + reader.flush() == b"<main>tarjetas</main>"


async def test_twenty_widgets_at_once_ask_the_kernel_once(api) -> None:
    responses = await asyncio.gather(*(api.get("/api/demo/tiny") for _ in range(20)))

    assert {response.status_code for response in responses} == {200}
    assert asked["modules"] == 1


async def test_a_person_is_asked_for_once_however_many_arrive_together(api) -> None:
    main.app.state.people._known.clear()

    await asyncio.gather(*(api.get("/api/demo/tiny") for _ in range(10)))

    assert asked["users"] == 1


async def test_who_leaves_first_does_not_leave_the_rest_without_an_answer(api) -> None:
    first = asyncio.create_task(main.registry(main.app.state))
    await asyncio.sleep(0.01)
    second = asyncio.create_task(main.registry(main.app.state))
    first.cancel()

    found = await second

    assert found is not None and "demo" in found[0]
    assert asked["modules"] == 1
