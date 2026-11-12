from __future__ import annotations

from test_money_api import book  # noqa: F401 -- la fixture con el log y la configuración

READ = {"x-arga-scopes": "money:read"}
WRITE = {"x-arga-scopes": "money:write"}


async def test_the_server_lists_every_tool_of_the_manifest(book) -> None:  # noqa: F811
    names = {t["name"] for t in (await book.get("/tools")).json()}
    assert names == {
        "get_summary",
        "get_movements",
        "get_shared_balance",
        "categorise_movement",
        "mark_transfer",
        "record_shared_expense",
        "get_products",
        "get_composition",
        "get_rules",
        "create_product",
        "update_product",
        "record_composition",
        "record_value",
        "classify_fund",
        "delete_rule",
    }


async def test_reading_tools_answer_with_the_reading_role(book) -> None:  # noqa: F811
    summary = await book.post("/tools/get_summary", json={}, headers=READ)
    assert summary.status_code == 200, summary.text
    assert [k["key"] for k in summary.json()["content"]["kpis"]][0] == "networth"
    moves = await book.post("/tools/get_movements", json={"month": "2026-03"}, headers=READ)
    content = moves.json()["content"]
    assert content["matching"] >= 8
    assert any(m["status"] == "transfer" for m in content["movements"])
    pending = await book.post(
        "/tools/get_movements", json={"month": "2026-03", "pending_only": True}, headers=READ
    )
    assert {m["status"] for m in pending.json()["content"]["movements"]} <= {"ask", "pending"}
    shared = await book.post("/tools/get_shared_balance", json={"year": 2026}, headers=READ)
    assert (
        "debe" in shared.json()["content"]["balance"]
        or "cero" in shared.json()["content"]["balance"]
    )


async def test_a_write_with_the_reading_role_is_refused_by_postgres(book) -> None:  # noqa: F811
    response = await book.post(
        "/tools/record_shared_expense",
        json={"description": "Luz", "amount": "30", "category": "Suministros"},
        headers=READ,
    )
    assert response.status_code == 403


async def test_writing_tools_label_a_movement_and_record_an_expense(book) -> None:  # noqa: F811
    labelled = await book.post(
        "/tools/categorise_movement",
        json={"movement_id": "main:old1", "category": "Suscripciones"},
        headers=WRITE,
    )
    assert labelled.status_code == 200, labelled.text
    assert labelled.json()["content"]["category"] == "Suscripciones"
    rows = (await book.get("/movements", params={"from": "2026-03-01", "to": "2026-03-31"})).json()
    old = next(m for m in rows["movements"] if m["id"] == "main:old1")
    assert old["status"] == "manual"
    unknown = await book.post(
        "/tools/categorise_movement",
        json={"movement_id": "main:old1", "category": "No existe"},
        headers=WRITE,
    )
    assert "error" in unknown.json()["content"]
    recorded = await book.post(
        "/tools/record_shared_expense",
        json={"description": "Luz", "amount": "30", "category": "Suministros", "on": "2026-03-04"},
        headers=WRITE,
    )
    assert recorded.status_code == 200, recorded.text
    shared = (await book.get("/shared", params={"year": 2026})).json()
    assert any(e["description"] == "Luz" for e in shared["entries"])


async def test_a_movement_marked_as_a_transfer_is_money_put_into_an_etf(book) -> None:  # noqa: F811
    created = await book.post(
        "/tools/create_product",
        json={"name": "Bróker", "type": "etf", "institution": "Bróker Inventado"},
        headers=WRITE,
    )
    assert created.status_code == 200, created.text
    assert "error" not in created.json()["content"]

    marked = await book.post(
        "/tools/mark_transfer",
        json={"movement_id": "main:old1", "product": "broker"},
        headers=WRITE,
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["content"] == {"movement": "main:old1", "transfer": "a Bróker"}
    rows = (await book.get("/movements", params={"from": "2026-03-01", "to": "2026-03-31"})).json()
    assert next(m for m in rows["movements"] if m["id"] == "main:old1")["status"] == "transfer"
    product = await book.post("/tools/get_products", json={"product": "Bróker"}, headers=READ)
    detail = product.json()["content"]
    assert (detail["type_label"], detail["group"]) == ("ETF o acciones", "Bolsa")
    assert detail["contributed"] == 12.99

    same = await book.post(
        "/tools/mark_transfer",
        json={"movement_id": "main:m3", "product": "Principal"},
        headers=WRITE,
    )
    assert "error" in same.json()["content"]
    nowhere = await book.post(
        "/tools/mark_transfer",
        json={"movement_id": "main:m3", "product": "No existe"},
        headers=WRITE,
    )
    assert "error" in nowhere.json()["content"]
    reading = await book.post(
        "/tools/mark_transfer", json={"movement_id": "main:m3", "product": "Bróker"}, headers=READ
    )
    assert reading.status_code == 403


async def test_without_a_money_scope_nothing_opens(book) -> None:  # noqa: F811
    response = await book.post(
        "/tools/get_summary", json={}, headers={"x-arga-scopes": "training:read"}
    )
    assert response.status_code == 403
