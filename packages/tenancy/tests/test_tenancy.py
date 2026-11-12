from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from arga_tenancy import (
    SPACES_HEADER,
    USER_HEADER,
    UserFromHeader,
    as_user,
    current_spaces,
    current_user,
    from_environment,
    people,
    user_headers,
)


async def whoami(request: Request) -> JSONResponse:
    user = current_user.get()
    return JSONResponse({"user": str(user) if user else None, "headers": user_headers()})


app = Starlette(routes=[Route("/", whoami)])
app.add_middleware(UserFromHeader)


@pytest.fixture
async def service():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://m") as c:
        yield c


async def test_the_header_is_the_person_for_the_whole_request(service) -> None:
    person = str(uuid4())

    body = (await service.get("/", headers={USER_HEADER: person})).json()

    assert body == {"user": person, "headers": {USER_HEADER: person}}


async def test_without_the_header_there_is_nobody_and_nothing_is_forwarded(service) -> None:
    assert (await service.get("/")).json() == {"user": None, "headers": {}}


async def test_a_header_that_is_not_a_person_is_a_400(service) -> None:
    response = await service.get("/", headers={USER_HEADER: "yo"})

    assert response.status_code == 400


async def test_the_person_does_not_outlive_the_request(service) -> None:
    await service.get("/", headers={USER_HEADER: str(uuid4())})

    assert current_user.get() is None


def test_a_background_pass_is_in_the_name_of_its_person_and_only_inside() -> None:
    person = uuid4()
    with as_user(person):
        assert user_headers() == {USER_HEADER: str(person)}
    assert user_headers() == {}


def test_a_child_process_reads_its_person_from_the_environment(monkeypatch) -> None:
    person = uuid4()
    monkeypatch.setenv("ARGA_USER_ID", str(person))
    assert from_environment() == person
    monkeypatch.delenv("ARGA_USER_ID")
    assert from_environment() is None


async def test_without_the_header_an_in_process_caller_is_still_who_it_was(service) -> None:
    person = uuid4()
    with as_user(person):
        body = (await service.get("/")).json()

    assert body["user"] == str(person)


CASA = UUID("0c0c0c0c-0000-4000-8000-00000000c0c0")
OTRO = UUID("0d0d0d0d-0000-4000-8000-00000000d0d0")


async def spaces_seen(request: Request) -> JSONResponse:
    return JSONResponse(
        {"spaces": [str(s) for s in current_spaces.get()], "headers": user_headers()}
    )


spaces_app = Starlette(routes=[Route("/", spaces_seen)])
spaces_app.add_middleware(UserFromHeader)


@pytest.fixture
async def spaces_service():
    transport = httpx.ASGITransport(app=spaces_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://m") as c:
        yield c


async def test_the_spaces_come_with_the_person_and_are_forwarded(spaces_service) -> None:
    person = str(uuid4())
    header = f"{CASA},{OTRO}"

    body = (
        await spaces_service.get("/", headers={USER_HEADER: person, SPACES_HEADER: header})
    ).json()

    assert body["spaces"] == [str(CASA), str(OTRO)]
    assert body["headers"] == {USER_HEADER: person, SPACES_HEADER: header}


async def test_a_space_that_is_not_an_id_is_a_400(spaces_service) -> None:
    response = await spaces_service.get(
        "/", headers={USER_HEADER: str(uuid4()), SPACES_HEADER: f"{CASA},casa"}
    )

    assert response.status_code == 400


async def test_without_spaces_there_are_none_and_none_are_forwarded(spaces_service) -> None:
    person = str(uuid4())

    body = (await spaces_service.get("/", headers={USER_HEADER: person})).json()

    assert body == {"spaces": [], "headers": {USER_HEADER: person}}


def test_a_background_pass_carries_the_spaces_only_inside() -> None:
    person = uuid4()
    with as_user(person, (CASA,)):
        assert user_headers() == {USER_HEADER: str(person), SPACES_HEADER: str(CASA)}
    assert current_spaces.get() == ()


def test_spaces_without_a_person_are_not_forwarded() -> None:
    with as_user(None, (CASA,)):
        assert user_headers() == {}


async def test_a_worker_gets_each_person_with_their_spaces_and_none_from_an_older_kernel() -> None:
    ana, luis, casa = uuid4(), uuid4(), uuid4()

    def kernel(spaces: bool):
        def answer(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/internal/users"
            rows = [{"id": str(ana)}, {"id": str(luis)}]
            if spaces:
                rows = [{**rows[0], "spaces": [str(casa)]}, {**rows[1], "spaces": []}]
            return httpx.Response(200, json=rows)

        return httpx.AsyncClient(transport=httpx.MockTransport(answer))

    async with kernel(True) as client:
        now = await people(client)
    async with kernel(False) as client:
        before = await people(client)

    assert now == [(ana, (casa,)), (luis, ())]
    assert before == [(ana, ()), (luis, ())]


async def test_every_answer_says_how_long_it_took(service) -> None:
    response = await service.get("/", headers={USER_HEADER: str(uuid4())})

    timing = response.headers["server-timing"]
    assert timing.startswith('db;dur=0.0;desc="0 consultas", app;dur=')


async def test_an_answer_without_a_person_is_measured_too(service) -> None:
    assert "app;dur=" in (await service.get("/")).headers["server-timing"]
