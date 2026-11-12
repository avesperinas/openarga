from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_tenancy import SPACES_HEADER, USER_HEADER, as_user
from kernel.db import engine
from kernel.main import app
from kernel.spaces import normalise

SUBJECTS = {
    "ana": "3f0c7a52-1d2e-4b8a-9c61-7e5d4a3b2c10",
    "luis": "8a1e6d4c-2b3f-4c5d-8e7f-0a1b2c3d4e5f",
    "eva": "c4d5e6f7-0819-4a2b-9c3d-4e5f60718293",
}


async def clean() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "delete from kernel.spaces where id in (select space_id from kernel.space_members "
                "where user_id in (select id from kernel.users where subject = any(:s)))"
            ),
            {"s": list(SUBJECTS.values())},
        )
        await connection.execute(
            text("delete from kernel.users where subject = any(:s)"),
            {"s": list(SUBJECTS.values())},
        )


@pytest.fixture
async def kernel(database_url: str):
    await clean()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await clean()
    await engine().dispose()


@pytest.fixture
async def people(kernel) -> dict[str, dict[str, str]]:
    found = {}
    for name, subject in SUBJECTS.items():
        person = (await kernel.post("/internal/users", json={"subject": subject})).json()
        found[name] = {USER_HEADER: person["id"]}
    return found


async def test_whoever_creates_a_space_owns_it_and_is_its_only_member(kernel, people) -> None:
    response = await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=people["ana"])

    body = response.json()
    assert response.status_code == 201
    assert (body["name"], body["role"]) == ("Casa", "owner")
    assert body["members"] == [
        {"user_id": people["ana"][USER_HEADER], "role": "owner", "name": None}
    ]


async def test_without_a_person_there_is_no_space(kernel) -> None:
    with as_user(None):
        response = await kernel.post("/internal/spaces", json={"name": "Casa"})

    assert response.status_code == 422


async def test_joining_with_the_code_makes_both_see_the_same_space(kernel, people) -> None:
    space = (
        await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=people["ana"])
    ).json()
    invite = (
        await kernel.post(f"/internal/spaces/{space['id']}/invites", headers=people["ana"])
    ).json()

    joined = await kernel.post(
        "/internal/spaces/join", json={"code": invite["code"].lower()}, headers=people["luis"]
    )
    ana = (await kernel.get("/internal/spaces", headers=people["ana"])).json()
    luis = (await kernel.get("/internal/spaces", headers=people["luis"])).json()

    assert joined.status_code == 200
    assert joined.json()["role"] == "member"
    assert [s["id"] for s in ana] == [s["id"] for s in luis] == [space["id"]]
    assert {m["user_id"] for m in luis[0]["members"]} == {
        people["ana"][USER_HEADER],
        people["luis"][USER_HEADER],
    }


async def test_a_code_works_once(kernel, people) -> None:
    space = (
        await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=people["ana"])
    ).json()
    code = (
        await kernel.post(f"/internal/spaces/{space['id']}/invites", headers=people["ana"])
    ).json()["code"]

    first = await kernel.post("/internal/spaces/join", json={"code": code}, headers=people["luis"])
    again = await kernel.post("/internal/spaces/join", json={"code": code}, headers=people["luis"])
    other = await kernel.post("/internal/spaces/join", json={"code": code}, headers=people["eva"])

    assert (first.status_code, again.status_code, other.status_code) == (200, 200, 410)
    assert (await kernel.get("/internal/spaces", headers=people["eva"])).json() == []


async def test_an_expired_code_does_not_open_the_space(kernel, people) -> None:
    space = (
        await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=people["ana"])
    ).json()
    code = (
        await kernel.post(f"/internal/spaces/{space['id']}/invites", headers=people["ana"])
    ).json()["code"]
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "update kernel.space_invites set expires_at = now() - interval '1 minute' "
                "where code = :c"
            ),
            {"c": code},
        )

    response = await kernel.post(
        "/internal/spaces/join", json={"code": code}, headers=people["luis"]
    )

    assert response.status_code == 410


async def test_a_code_that_does_not_exist_is_a_404(kernel, people) -> None:
    response = await kernel.post(
        "/internal/spaces/join", json={"code": "AAAA-BBBB-CCCC"}, headers=people["luis"]
    )

    assert response.status_code == 404


async def test_only_the_owner_invites_and_to_an_outsider_the_space_does_not_exist(
    kernel, people
) -> None:
    space = (
        await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=people["ana"])
    ).json()
    code = (
        await kernel.post(f"/internal/spaces/{space['id']}/invites", headers=people["ana"])
    ).json()["code"]
    await kernel.post("/internal/spaces/join", json={"code": code}, headers=people["luis"])

    member = await kernel.post(f"/internal/spaces/{space['id']}/invites", headers=people["luis"])
    outsider = await kernel.post(f"/internal/spaces/{space['id']}/invites", headers=people["eva"])

    assert (member.status_code, outsider.status_code) == (403, 404)


async def test_the_gateway_learns_the_spaces_with_the_person(kernel, people) -> None:
    space = (
        await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=people["ana"])
    ).json()

    ana = (await kernel.post("/internal/users", json={"subject": SUBJECTS["ana"]})).json()
    eva = (await kernel.post("/internal/users", json={"subject": SUBJECTS["eva"]})).json()

    assert ana == {"id": people["ana"][USER_HEADER], "spaces": [space["id"]]}
    assert eva["spaces"] == []


async def test_the_spaces_reach_the_transaction_and_do_not_stay_in_the_pool(
    database_url: str,
) -> None:
    ana = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
    casa = UUID("0c0c0c0c-0000-4000-8000-00000000c0c0")
    otro = UUID("0d0d0d0d-0000-4000-8000-00000000d0d0")
    read = text("select current_setting('arga.space_ids', true)")
    try:
        with as_user(ana, (casa, otro)):
            async with engine().begin() as connection:
                inside = await connection.scalar(read)
        with as_user(ana):
            async with engine().begin() as connection:
                after = await connection.scalar(read)
    finally:
        await engine().dispose()

    assert inside == f"{{{casa},{otro}}}"
    assert after in (None, "")


def test_a_code_is_read_however_it_is_typed() -> None:
    assert normalise(" abcd efgh-jkmn ") == "ABCD-EFGH-JKMN"


async def test_the_spaces_header_is_read_by_the_kernel(kernel, people) -> None:
    response = await kernel.get(
        "/internal/spaces", headers={**people["ana"], SPACES_HEADER: "no-es-un-id"}
    )

    assert response.status_code == 400


async def two_in_a_space(kernel, people, *others: str) -> str:
    space = (
        await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=people["ana"])
    ).json()
    for name in ("luis", *others):
        code = (
            await kernel.post(f"/internal/spaces/{space['id']}/invites", headers=people["ana"])
        ).json()["code"]
        await kernel.post("/internal/spaces/join", json={"code": code}, headers=people[name])
    return space["id"]


async def test_whoever_leaves_stops_seeing_the_space_and_the_rest_keep_it(kernel, people) -> None:
    space = await two_in_a_space(kernel, people)
    luis = people["luis"][USER_HEADER]

    left = await kernel.delete(f"/internal/spaces/{space}/members/{luis}", headers=people["luis"])
    theirs = (await kernel.get("/internal/spaces", headers=people["luis"])).json()
    ana = (await kernel.get("/internal/spaces", headers=people["ana"])).json()[0]
    resolved = (await kernel.post("/internal/users", json={"subject": SUBJECTS["luis"]})).json()

    assert left.status_code == 204
    assert theirs == []
    assert resolved["spaces"] == []
    assert [m["user_id"] for m in ana["members"]] == [people["ana"][USER_HEADER]]
    assert [f["user_id"] for f in ana["former"]] == [luis]


async def test_the_owner_removes_someone_and_nobody_else_does(kernel, people) -> None:
    space = await two_in_a_space(kernel, people, "eva")
    luis, eva = people["luis"][USER_HEADER], people["eva"][USER_HEADER]

    by_member = await kernel.delete(
        f"/internal/spaces/{space}/members/{eva}", headers=people["luis"]
    )
    by_owner = await kernel.delete(f"/internal/spaces/{space}/members/{eva}", headers=people["ana"])
    by_outsider = await kernel.delete(
        f"/internal/spaces/{space}/members/{luis}", headers=people["eva"]
    )

    assert (by_member.status_code, by_owner.status_code, by_outsider.status_code) == (
        403,
        204,
        404,
    )


async def test_the_only_person_in_a_space_does_not_leave_it(kernel, people) -> None:
    space = (
        await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=people["ana"])
    ).json()

    response = await kernel.delete(
        f"/internal/spaces/{space['id']}/members/{people['ana'][USER_HEADER]}",
        headers=people["ana"],
    )

    assert response.status_code == 409


async def test_when_the_owner_leaves_the_oldest_member_owns_the_space(kernel, people) -> None:
    space = await two_in_a_space(kernel, people, "eva")

    await kernel.delete(
        f"/internal/spaces/{space}/members/{people['ana'][USER_HEADER]}", headers=people["ana"]
    )
    luis = (await kernel.get("/internal/spaces", headers=people["luis"])).json()[0]
    invite = await kernel.post(f"/internal/spaces/{space}/invites", headers=people["luis"])

    assert luis["role"] == "owner"
    assert invite.status_code == 201


async def test_whoever_left_comes_back_with_a_new_code(kernel, people) -> None:
    space = await two_in_a_space(kernel, people)
    luis = people["luis"][USER_HEADER]
    await kernel.delete(f"/internal/spaces/{space}/members/{luis}", headers=people["ana"])
    code = (await kernel.post(f"/internal/spaces/{space}/invites", headers=people["ana"])).json()[
        "code"
    ]

    back = await kernel.post("/internal/spaces/join", json={"code": code}, headers=people["luis"])

    assert back.status_code == 200
    assert {m["user_id"] for m in back.json()["members"]} == {people["ana"][USER_HEADER], luis}
    assert back.json()["former"] == []


async def test_each_one_says_their_name_and_the_others_see_it(kernel, people) -> None:
    space = (
        await kernel.post("/spaces", json={"name": "Casa", "me": " Ana "}, headers=people["ana"])
    ).json()
    code = (await kernel.post(f"/spaces/{space['id']}/invites", headers=people["ana"])).json()[
        "code"
    ]
    await kernel.post("/spaces/join", json={"code": code, "me": "Luis"}, headers=people["luis"])

    seen = (await kernel.get("/spaces", headers=people["luis"])).json()[0]

    assert {m["user_id"]: m["name"] for m in seen["members"]} == {
        people["ana"][USER_HEADER]: "Ana",
        people["luis"][USER_HEADER]: "Luis",
    }


async def test_a_name_is_changed_by_its_owner_and_only_in_that_space(kernel, people) -> None:
    space = await two_in_a_space(kernel, people)
    other = (
        await kernel.post("/spaces", json={"name": "Viajes", "me": "Ana"}, headers=people["ana"])
    ).json()

    renamed = await kernel.put(f"/spaces/{space}/me", json={"name": "Anita"}, headers=people["ana"])
    outsider = await kernel.put(f"/spaces/{space}/me", json={"name": "Eva"}, headers=people["eva"])
    empty = await kernel.put(f"/spaces/{space}/me", json={"name": "  "}, headers=people["ana"])
    names = {
        s["id"]: {m["user_id"]: m["name"] for m in s["members"]}
        for s in (await kernel.get("/spaces", headers=people["ana"])).json()
    }

    assert renamed.status_code == 200
    assert (outsider.status_code, empty.status_code) == (404, 422)
    assert names[space][people["ana"][USER_HEADER]] == "Anita"
    assert names[other["id"]][people["ana"][USER_HEADER]] == "Ana"


async def test_whoever_comes_back_keeps_their_name_unless_they_say_another(kernel, people) -> None:
    space = (
        await kernel.post("/spaces", json={"name": "Casa", "me": "Ana"}, headers=people["ana"])
    ).json()["id"]
    luis = people["luis"][USER_HEADER]

    async def join(me: str | None) -> dict:
        code = (await kernel.post(f"/spaces/{space}/invites", headers=people["ana"])).json()["code"]
        body = {"code": code} | ({"me": me} if me else {})
        return (await kernel.post("/spaces/join", json=body, headers=people["luis"])).json()

    await join("Luis")
    await kernel.delete(f"/spaces/{space}/members/{luis}", headers=people["luis"])
    back = await join(None)

    assert {m["user_id"]: m["name"] for m in back["members"]}[luis] == "Luis"


async def test_the_list_of_people_for_workers_carries_each_ones_spaces(kernel, people) -> None:
    space = await two_in_a_space(kernel, people)
    ana, luis, eva = (people[name][USER_HEADER] for name in ("ana", "luis", "eva"))

    listed = {row["id"]: row["spaces"] for row in (await kernel.get("/internal/users")).json()}
    await kernel.delete(f"/internal/spaces/{space}/members/{luis}", headers=people["luis"])
    after = {row["id"]: row["spaces"] for row in (await kernel.get("/internal/users")).json()}

    assert (listed[ana], listed[luis], listed[eva]) == ([space], [space], [])
    assert (after[ana], after[luis]) == ([space], [])
