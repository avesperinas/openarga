from __future__ import annotations

from uuid import UUID

import pytest
from money_people import OTHER, PERSON
from test_money_api import book  # noqa: F401 - the usual book, One's

from arga_tenancy import SPACES_HEADER, USER_HEADER, as_user
from money import worker

CASA = UUID("0c0c0c0c-0000-4000-8000-00000000c0c0")
UNO = {USER_HEADER: str(PERSON), SPACES_HEADER: str(CASA)}
DOS = {USER_HEADER: str(OTHER), SPACES_HEADER: str(CASA)}
WRITE = {"x-arga-scopes": "money:write"}


@pytest.fixture
async def casa(book):  # noqa: F811
    for who in (UNO, DOS):
        chosen = await book.put("/shared/space", json={"space_id": str(CASA)}, headers=who)
        assert chosen.status_code == 200, chosen.text
    return book


async def shared(api, who: dict, year: int = 2026) -> dict:
    response = await api.get("/shared", params={"year": year}, headers=who)
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_other_member_sees_the_same_balance_from_the_other_side(casa) -> None:
    uno = await shared(casa, UNO)
    dos = await shared(casa, DOS)

    assert (uno["role"], dos["role"]) == ("keeper", "member")
    assert dos["balance_me"] == pytest.approx(-uno["balance_me"], abs=0.01)
    assert dos["ratio_me"] == pytest.approx(1 - uno["ratio_me"], abs=0.0001)
    assert dos["total"] == pytest.approx(uno["total"], abs=0.01)
    assert (dos["me"], dos["other"]) == (uno["other"], uno["me"])
    assert [m["month"] for m in dos["months"]] == [m["month"] for m in uno["months"]]
    for theirs, mine in zip(uno["months"], dos["months"], strict=True):
        assert mine["balance_me"] == pytest.approx(-theirs["balance_me"], abs=0.01)
        assert mine["paid"]["me"] == theirs["paid"]["other"]
        assert mine["deposits"]["other"] == theirs["deposits"]["me"]
    assert {c["name"] for c in dos["common_categories"]} == {
        "Rent",
        "Groceries",
        "Utilities",
        "Other",
    }
    assert dos["kept_at"] is not None


async def test_what_the_other_member_puts_down_counts_for_both(casa) -> None:
    before = (await shared(casa, UNO))["balance_me"]
    await shared(casa, DOS)

    created = await casa.post(
        "/shared/entries",
        json={
            "payer": "me",
            "on": "2026-03-03",
            "amount": "100",
            "description": "Electricity",
            "category": "utilities",
        },
        headers=DOS,
    )
    with as_user(PERSON, (CASA,)):
        await worker.keep_common(PERSON)
    uno = await shared(casa, UNO)
    dos = await shared(casa, DOS)

    assert created.status_code == 201, created.text
    r = 30000 / 50000
    assert uno["balance_me"] == pytest.approx(before - (r * 100 + r * 100) / 2, abs=0.01)
    assert dos["balance_me"] == pytest.approx(-uno["balance_me"], abs=0.01)
    assert [(e["description"], e["payer"]) for e in uno["entries"]] == [("Electricity", "other")]
    assert [(e["description"], e["payer"]) for e in dos["entries"]] == [("Electricity", "me")]

    gone = await casa.delete(f"/shared/entries/{dos['entries'][0]['id']}", headers=UNO)
    assert gone.status_code == 204
    assert (await shared(casa, UNO))["balance_me"] == pytest.approx(before, abs=0.01)


async def test_what_was_put_down_before_moves_to_the_space(book) -> None:  # noqa: F811
    cats = {
        c["name"]: c["id"] for c in (await book.get("/state", headers=UNO)).json()["categories"]
    }
    await book.post(
        "/shared/entries",
        json={
            "payer": "other",
            "on": "2026-03-03",
            "amount": "40",
            "description": "Gas bottle",
            "category": cats["Utilities"],
        },
        headers=UNO,
    )
    alone = (await shared(book, UNO))["balance_me"]

    for who in (UNO, DOS):
        await book.put("/shared/space", json={"space_id": str(CASA)}, headers=who)
    uno = await shared(book, UNO)
    dos = await shared(book, DOS)

    assert uno["balance_me"] == pytest.approx(alone, abs=0.01)
    assert [(e["description"], e["payer"]) for e in uno["entries"]] == [("Gas bottle", "other")]
    assert [(e["description"], e["payer"]) for e in dos["entries"]] == [("Gas bottle", "me")]


async def test_the_widget_and_the_tool_say_the_same_from_both_sides(casa) -> None:
    await shared(casa, UNO)

    widget_uno = (await casa.get("/widgets/shared", headers=UNO)).json()
    widget_dos = (await casa.get("/widgets/shared", headers=DOS)).json()
    tool_uno = await casa.post(
        "/tools/get_shared_balance", json={"year": 2026}, headers={**UNO, **WRITE}
    )
    tool_dos = await casa.post(
        "/tools/get_shared_balance", json={"year": 2026}, headers={**DOS, **WRITE}
    )

    assert widget_dos["body"]["value"] == pytest.approx(-widget_uno["body"]["value"], abs=0.01)
    uno, dos = tool_uno.json()["content"], tool_dos.json()["content"]
    assert dos["balance_me"] == pytest.approx(-uno["balance_me"], abs=0.01)
    assert dos["balance"] == uno["balance"]
    assert dos["kept_by"] == "One"


async def test_claude_puts_down_a_common_expense_from_the_other_side(casa) -> None:
    await shared(casa, UNO)

    recorded = await casa.post(
        "/tools/record_shared_expense",
        json={"description": "Butane", "amount": "25", "category": "Utilities", "payer": "me"},
        headers={**DOS, **WRITE},
    )
    unknown = await casa.post(
        "/tools/record_shared_expense",
        json={"description": "Something", "amount": "5", "category": "Invented", "payer": "me"},
        headers={**DOS, **WRITE},
    )

    assert recorded.json()["content"]["shared_space"] is True
    assert "Invented" in unknown.json()["content"]["error"]
    dos = await shared(casa, DOS)
    assert [(e["description"], e["payer"]) for e in dos["entries"]] == [("Butane", "me")]


async def test_settling_the_year_is_for_whoever_keeps_the_account(casa) -> None:
    await shared(casa, UNO)

    refused = await casa.put("/shared/years/2026", json={"settled": True}, headers=DOS)
    done = await casa.put("/shared/years/2026", json={"settled": True}, headers=UNO)
    dos = await shared(casa, DOS)

    assert refused.status_code == 409
    assert done.status_code == 200
    assert dos["settled"] is True


async def test_without_anyone_keeping_the_account_the_other_member_is_told(book) -> None:  # noqa: F811
    await book.put("/shared/space", json={"space_id": str(CASA)}, headers=DOS)

    dos = await shared(book, DOS)
    refused = await book.post(
        "/shared/entries",
        json={
            "payer": "me",
            "on": "2026-03-03",
            "amount": "10",
            "description": "X",
            "category": "Other",
        },
        headers=DOS,
    )

    assert (dos["role"], dos["has_keeper"], dos["months"]) == ("member", False, [])
    assert refused.status_code == 422
    assert "nobody" in refused.json()["detail"]
