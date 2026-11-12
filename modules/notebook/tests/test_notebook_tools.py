from __future__ import annotations

from datetime import timedelta

import httpx

from notebook.notes import today

WRITE = {"x-arga-scopes": "notebook:write"}
READ = {"x-arga-scopes": "notebook:read"}


async def call(api, name: str, body: dict, headers=WRITE) -> httpx.Response:
    return await api.post(f"/tools/{name}", json=body, headers=headers)


async def content(api, name: str, body: dict, headers=WRITE) -> dict:
    response = await call(api, name, body, headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def test_claude_writes_links_finds_edits_and_the_app_undoes_it(api) -> None:
    created = await content(
        api,
        "create_note",
        {
            "title": "DE 4.2 Wechselpräpositionen",
            "folder": "Study/Alemán/B1 Gramatik",
            "content": "# Wechselpräpositionen\n\nin, an, auf: Akkusativ o Dativ.\n",
            "properties": {"status": "offen"},
        },
    )
    await content(
        api,
        "create_note",
        {"title": "Índice", "content": "- [[DE 4.2 Wechselpräpositionen]]\n"},
    )

    found = await content(api, "search_notes", {"query": "wechselprapositionen"}, READ)
    read = await content(api, "read_note", {"note": "DE 4.2 Wechselpräpositionen"}, READ)
    links = await content(api, "read_note", {"note": created["path"], "links": True}, READ)
    edited = await content(
        api,
        "edit_note",
        {"note": created["id"], "old_text": "Akkusativ o Dativ", "new_text": "Wohin? / Wo?"},
    )

    assert found["notes"][0]["path"] == "Study/Alemán/B1 Gramatik/DE 4.2 Wechselpräpositionen"
    assert found["notes"][0]["href"] == f"/notebook/nota/{created['id']}"
    assert read["href"] == f"/notebook/nota/{created['id']}"
    assert "links" not in read
    assert read["properties"] == {"status": "offen"}
    assert read["backlinks"] == 1
    assert links["backlinks"] == [
        {"path": "Índice", "lines": ["- [[DE 4.2 Wechselpräpositionen]]"]}
    ]
    assert edited["version"] == 2

    history = (await api.get(f"/notes/{created['id']}/revisions")).json()
    assert [(r["replaced_by"], r["written_by"]) for r in history] == [("tool", "tool")]
    undone = await api.post(f"/notes/{created['id']}/revisions/{history[0]['id']}/restore")
    assert "Akkusativ o Dativ" in undone.json()["content"]


async def test_the_reader_scope_cannot_write(api) -> None:
    response = await call(api, "create_note", {"title": "No"}, READ)

    assert response.status_code == 403


async def test_a_title_shared_by_two_notes_asks_for_the_path(api) -> None:
    await content(api, "create_note", {"title": "Plan", "folder": "A"})
    await content(api, "create_note", {"title": "Plan", "folder": "B"})

    ambiguous = await call(api, "read_note", {"note": "plan"}, READ)
    by_path = await content(api, "read_note", {"note": "B/Plan"}, READ)
    by_link = await content(api, "read_note", {"note": "[[A/Plan|el plan]]"}, READ)

    assert ambiguous.status_code == 409
    assert "«A/Plan», «B/Plan»" in ambiguous.json()["detail"]
    assert by_path["path"] == "B/Plan"
    assert by_link["path"] == "A/Plan"


async def test_a_missing_note_suggests_similar_ones(api) -> None:
    await content(api, "create_note", {"title": "DE 2.3 Perfekt"})

    response = await call(api, "read_note", {"note": "Perfekt"}, READ)

    assert response.status_code == 404
    assert "«DE 2.3 Perfekt»" in response.json()["detail"]


async def test_a_fragment_that_is_not_there_or_twice_changes_nothing(api) -> None:
    await content(api, "create_note", {"title": "N", "content": "dos y dos"})

    missing = await call(api, "edit_note", {"note": "N", "old_text": "tres", "new_text": "3"})
    twice = await call(api, "edit_note", {"note": "N", "old_text": "dos", "new_text": "2"})
    read = await content(api, "read_note", {"note": "N"}, READ)

    assert missing.status_code == 422 and "no aparece" in missing.json()["detail"]
    assert twice.status_code == 409 and "2 veces" in twice.json()["detail"]
    assert read["content"] == "dos y dos" and read["version"] == 1


async def test_sections_are_read_replaced_and_appended_to(api) -> None:
    await content(
        api,
        "create_note",
        {"title": "Kasus", "content": "# Kasus\n\n## Dativ\n\nviejo\n\n## Genitiv\n\ng\n"},
    )

    await content(api, "replace_section", {"note": "Kasus", "heading": "Dativ", "text": "nuevo"})
    await content(api, "append_to_note", {"note": "Kasus", "text": "- mit", "heading": "## Dativ"})
    await content(api, "append_to_note", {"note": "Kasus", "text": "Fin."})
    dative = await content(api, "read_note", {"note": "Kasus", "section": "dativ"}, READ)
    whole = await content(api, "read_note", {"note": "Kasus"}, READ)

    assert dative["content"] == "## Dativ\nnuevo\n\n- mit\n\n"
    assert whole["content"].endswith("## Genitiv\n\ng\n\nFin.\n")
    assert whole["outline"] == ["# Kasus", "## Dativ", "## Genitiv"]


async def test_what_is_due_for_review_is_found_by_its_property(api) -> None:
    day = today().isoformat()
    await content(
        api,
        "create_note",
        {
            "title": "Toca",
            "properties": {"naechste_wiederholung": "2020-01-01", "fehlerquote": 0.4},
        },
    )
    await content(
        api,
        "create_note",
        {"title": "Aún no", "properties": {"naechste_wiederholung": "2999-01-01"}},
    )

    due = await content(
        api,
        "search_notes",
        {"properties": [{"name": "naechste_wiederholung", "op": "lte", "value": "today"}]},
        READ,
    )
    errors = await content(
        api,
        "search_notes",
        {"properties": [{"name": "fehlerquote", "op": "gt", "value": 0.3}]},
        READ,
    )
    await content(
        api,
        "set_properties",
        {"note": "Toca", "set": {"naechste_wiederholung": day}, "remove": ["fehlerquote"]},
    )
    read = await content(api, "read_note", {"note": "Toca"}, READ)

    assert [n["path"] for n in due["notes"]] == ["Toca"]
    assert [n["path"] for n in errors["notes"]] == ["Toca"]
    assert read["properties"] == {"naechste_wiederholung": day}
    assert read["content"].startswith(f"---\nnaechste_wiederholung: {day}\n---\n")


async def test_a_tag_in_a_list_property_is_found_with_eq(api) -> None:
    await content(api, "create_note", {"title": "Con", "properties": {"thema": ["Kasus", "Verb"]}})

    found = await content(
        api,
        "search_notes",
        {"properties": [{"name": "thema", "op": "eq", "value": "Verb"}]},
        READ,
    )

    assert [n["path"] for n in found["notes"]] == ["Con"]


async def test_the_daily_note_is_created_and_added_to(api) -> None:
    before = await content(api, "read_note", {"day": "2026-09-28"}, READ)
    await content(api, "add_to_daily_note", {"text": "- Hablé de Notebook", "day": "2026-09-28"})
    await content(api, "add_to_daily_note", {"text": "- Y del alemán", "day": "2026-09-28"})
    after = await content(api, "read_note", {"day": "2026-09-28"}, READ)
    today = await content(api, "read_note", {}, READ)

    assert before == {"date": "2026-09-28", "exists": False}
    assert after["path"] == "Diario/2026-09-28"
    assert after["content"] == "- Hablé de Notebook\n\n- Y del alemán\n"
    assert after["exists"] is True and after["date"] == "2026-09-28"
    assert today["exists"] is False


async def test_moving_a_note_says_how_many_notes_were_relinked(api) -> None:
    await content(api, "create_note", {"title": "Viejo"})
    await content(api, "create_note", {"title": "A", "content": "[[Viejo]]"})
    await content(api, "create_note", {"title": "B", "content": "[[Viejo|v]]"})

    moved = await content(
        api, "move_note", {"note": "Viejo", "folder": "Archivo", "title": "Nuevo"}
    )
    b = await content(api, "read_note", {"note": "B"}, READ)

    assert moved["path"] == "Archivo/Nuevo" and moved["relinked_notes"] == 2
    assert b["content"] == "[[Nuevo|v]]"


async def test_folders_tags_graph_and_what_changed(api) -> None:
    await content(api, "create_note", {"title": "A", "folder": "X/Y", "content": "#t1 [[B]]"})
    await content(api, "create_note", {"title": "B", "folder": "X", "content": "#t1/sub [[C]]"})
    await content(api, "create_note", {"title": "C", "content": "#t2"})

    root = await content(api, "list_folder", {}, READ)
    inside = await content(api, "list_folder", {"folder": "X"}, READ)
    graph = await content(api, "explore_graph", {"note": "A", "depth": 2}, READ)
    week_ago = (today() - timedelta(days=7)).isoformat()
    changes = await content(api, "search_notes", {"since": week_ago, "by": "claude"}, READ)
    mine = await content(api, "search_notes", {"since": week_ago, "by": "me"}, READ)
    before = await content(api, "search_notes", {"until": week_ago}, READ)

    assert root["folder"] == "" and root["notes"] == ["C"]
    assert root["folders"] == [{"path": "X", "notes": 2}]
    assert "tags" not in inside
    assert root["tags"] == [
        {"tag": "t1", "notes": 1},
        {"tag": "t1/sub", "notes": 1},
        {"tag": "t2", "notes": 1},
    ]
    assert [(n["path"], n["depth"]) for n in graph["notes"]] == [("X/Y/A", 0), ("X/B", 1), ("C", 2)]
    assert sorted(map(tuple, graph["edges"])) == [("X/B", "C"), ("X/Y/A", "X/B")]
    assert {c["path"] for c in changes["notes"]} == {"X/Y/A", "X/B", "C"}
    assert all(c["updated_by"] == "claude" and c["changes"] == 1 for c in changes["notes"])
    assert mine["notes"] == [] and before["notes"] == []


async def test_bad_arguments_are_a_422(api) -> None:
    assert (await call(api, "create_note", {"title": "a|b"})).status_code == 422
    assert (await call(api, "set_properties", {"note": "x"})).status_code == 422
    assert (await call(api, "explore_graph", {"note": "x", "depth": 5}, READ)).status_code == 422
