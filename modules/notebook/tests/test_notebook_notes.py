from __future__ import annotations

import unicodedata

import httpx


def nfd(value: str) -> str:
    return unicodedata.normalize("NFD", value)


async def create(api, title: str, content: str = "", folder: str = "") -> dict:
    response = await api.post("/notes", json={"folder": folder, "title": title, "content": content})
    assert response.status_code == 201, response.text
    return response.json()


async def links(api, note: dict) -> dict:
    response = await api.get(f"/notes/{note['id']}/links")
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_note_is_created_in_its_folder_with_its_properties_and_tags(api) -> None:
    note = await create(
        api,
        "DE 1.1 Kasus",
        "---\ntags: [deutsch]\nstatus: offen\n---\n# Kasus\n\n#grammatik\n",
        "Study/Alemán/B1 Gramatik",
    )

    assert note["path"] == "Study/Alemán/B1 Gramatik/DE 1.1 Kasus"
    assert note["properties"] == {"tags": ["deutsch"], "status": "offen"}
    assert note["tags"] == ["grammatik", "deutsch"]
    assert note["outline"] == [{"level": 1, "text": "Kasus", "line": 4}]
    tree = (await api.get("/tree")).json()
    assert tree["folders"] == ["Study", "Study/Alemán", "Study/Alemán/B1 Gramatik"]


async def test_a_title_taken_in_the_same_folder_is_a_conflict_whatever_its_case(api) -> None:
    await create(api, "Plan", folder="A")
    again = await api.post("/notes", json={"folder": "a", "title": "PLAN"})
    elsewhere = await api.post("/notes", json={"folder": "B", "title": "Plan"})

    assert again.status_code == 409
    assert "ya hay una nota «PLAN» en «A»" in again.json()["detail"]
    assert elsewhere.status_code == 201


async def test_a_folder_keeps_the_case_it_was_created_with(api) -> None:
    await create(api, "Uno", folder="Study/Alemán")
    second = await create(api, "Dos", folder="study/alemán")

    assert second["folder"] == "Study/Alemán"


async def test_a_bad_title_says_why(api) -> None:
    response = await api.post("/notes", json={"title": "a/b"})

    assert response.status_code == 422
    assert "«/»" in response.json()["detail"]


async def test_a_link_written_in_nfd_reaches_the_note_and_counts_as_a_backlink(api) -> None:
    target = await create(api, "DE 4.2 Wechselpräpositionen", "Texto", "B1")
    source = await create(api, "Índice", f"Ver [[DE 4.2 {nfd('Wechselpräpositionen')}]] hoy.", "B1")

    out = await links(api, source)
    back = await links(api, target)

    assert out["links"][0]["note"]["id"] == target["id"]
    assert [(b["note"]["id"], b["lines"]) for b in back["backlinks"]] == [
        (source["id"], ["Ver [[DE 4.2 Wechselpräpositionen]] hoy."])
    ]


async def test_a_link_waits_for_its_note_and_finds_it_when_created(api) -> None:
    source = await create(api, "Índice", "[[Todavía no]]")
    assert (await links(api, source))["links"][0]["note"] is None

    created = await create(api, "Todavía no")

    assert (await links(api, source))["links"][0]["note"]["id"] == created["id"]


async def test_two_notes_with_the_same_title_the_same_folder_wins(api) -> None:
    near = await create(api, "Plan", folder="Proyectos/Casa")
    await create(api, "Plan", folder="Otros")
    source = await create(api, "Obra", "[[Plan]] y [[Otros/Plan]]", "Proyectos/Casa")

    found = (await links(api, source))["links"]

    assert found[0]["note"]["id"] == near["id"]
    assert found[1]["note"]["path"] == "Otros/Plan"


async def test_resolving_a_link_for_the_app(api) -> None:
    note = await create(api, "Destino", folder="X")

    found = (await api.get("/notes/resolve", params={"target": "destino"})).json()
    missing = (await api.get("/notes/resolve", params={"target": "Nada"})).json()

    assert found["note"]["id"] == note["id"]
    assert missing["note"] is None


async def test_search_ignores_umlauts_accents_and_case_and_puts_titles_first(api) -> None:
    await create(api, "Otra", "Aquí se habla de Präfixe de pasada.")
    await create(api, "Präfixe und Suffixe", "Wortbildung.")

    found = (await api.get("/search", params={"q": "prafix"})).json()

    assert [hit["title"] for hit in found] == ["Präfixe und Suffixe", "Otra"]
    assert "Präfixe" in found[1]["snippet"]


async def test_search_by_folder_and_by_parent_tag(api) -> None:
    await create(api, "Uno", "#deutsch/b1 nada", "Study/Alemán")
    await create(api, "Dos", "#deutsch nada", "Otros")
    await create(api, "Tres", "#english nada", "Study")

    by_folder = (await api.get("/search", params={"folder": "study"})).json()
    by_tag = (await api.get("/search", params={"tag": "#Deutsch"})).json()

    assert {hit["title"] for hit in by_folder} == {"Uno", "Tres"}
    assert {hit["title"] for hit in by_tag} == {"Uno", "Dos"}


async def test_renaming_a_note_rewrites_the_links_that_would_lose_it(api) -> None:
    target = await create(api, "Viejo", folder="A")
    source = await create(api, "Fuente", "[[Viejo#Parte|alias]] y ![[Viejo]] y [[Otro]]", "B")

    moved = await api.post(f"/notes/{target['id']}/move", json={"title": "Nuevo"})

    assert moved.status_code == 200, moved.text
    assert moved.json()["relinked"] == 1
    content = (await api.get(f"/notes/{source['id']}")).json()["content"]
    assert content == "[[Nuevo#Parte|alias]] y ![[Nuevo]] y [[Otro]]"


async def test_moving_a_note_next_to_a_namesake_writes_the_path(api) -> None:
    target = await create(api, "Plan", folder="A")
    await create(api, "Plan", folder="C")
    source = await create(api, "Fuente", "[[A/Plan]]", "C")

    await api.post(f"/notes/{target['id']}/move", json={"folder": "B"})

    assert (await api.get(f"/notes/{source['id']}")).json()["content"] == "[[B/Plan]]"


async def test_moving_a_folder_moves_its_notes_and_fixes_path_links(api) -> None:
    inside = await create(api, "Dentro", folder="Viejo/Sub")
    source = await create(api, "Fuente", "[[Viejo/Sub/Dentro]] y [[Dentro]]")

    moved = await api.put("/folders", json={"from": "Viejo", "to": "Study/Nuevo"})

    assert moved.json() == {"path": "Study/Nuevo", "notes": 1}
    assert (await api.get(f"/notes/{inside['id']}")).json()["path"] == "Study/Nuevo/Sub/Dentro"
    content = (await api.get(f"/notes/{source['id']}")).json()["content"]
    assert content == "[[Dentro]] y [[Dentro]]"
    assert (await api.get("/tree")).json()["folders"] == ["Study", "Study/Nuevo", "Study/Nuevo/Sub"]


async def test_a_folder_cannot_move_inside_itself(api) -> None:
    await create(api, "Uno", folder="A")

    response = await api.put("/folders", json={"from": "A", "to": "A/B"})

    assert response.status_code == 422


async def test_listing_a_folder_counts_what_is_inside(api) -> None:
    await create(api, "Uno", folder="Study/Alemán/B1")
    await create(api, "Dos", folder="Study/Alemán")
    await create(api, "Raíz")

    root = (await api.get("/folders")).json()
    study = (await api.get("/folders", params={"path": "study"})).json()

    assert [(f["path"], f["notes"]) for f in root["folders"]] == [("Study", 2)]
    assert [n["title"] for n in root["notes"]] == ["Raíz"]
    assert study["path"] == "Study"
    assert [(f["name"], f["notes"]) for f in study["folders"]] == [("Alemán", 2)]


async def test_the_trash_keeps_a_note_until_it_is_emptied(api) -> None:
    note = await create(api, "Borrable", "texto")

    assert (await api.delete(f"/notes/{note['id']}")).status_code == 204
    assert (await api.get(f"/notes/{note['id']}")).status_code == 404
    assert [n["title"] for n in (await api.get("/trash")).json()] == ["Borrable"]
    blocker = await create(api, "Borrable")
    assert (await api.post(f"/trash/{note['id']}/restore")).status_code == 409
    await api.delete(f"/notes/{blocker['id']}")
    await api.delete(f"/trash/{blocker['id']}")

    restored = await api.post(f"/trash/{note['id']}/restore")

    assert restored.status_code == 200 and restored.json()["content"] == "texto"
    await api.delete(f"/notes/{note['id']}")
    assert (await api.delete("/trash")).json() == {"deleted": 1}
    assert (await api.get("/trash")).json() == []


async def test_deleting_a_folder_sends_its_notes_to_the_trash(api) -> None:
    await create(api, "Uno", folder="Fuera/Sub")

    assert (await api.delete("/folders", params={"path": "Fuera"})).json() == {"trashed": 1}
    assert (await api.get("/tree")).json() == {"folders": [], "notes": []}
    assert len((await api.get("/trash")).json()) == 1


async def test_the_app_cannot_overwrite_a_version_it_did_not_see(api) -> None:
    note = await create(api, "Compartida", "uno")
    await api.put(f"/notes/{note['id']}", json={"content": "dos", "version": note["version"]})

    stale = await api.put(f"/notes/{note['id']}", json={"content": "tres", "version": 1})

    assert stale.status_code == 409
    assert "cambió mientras la editabas" in stale.json()["detail"]


async def test_typing_in_the_app_keeps_one_version_every_ten_minutes(api) -> None:
    note = await create(api, "Diario", "a")
    for text in ("ab", "abc", "abcd"):
        await api.put(f"/notes/{note['id']}", json={"content": text})

    history = (await api.get(f"/notes/{note['id']}/revisions")).json()

    assert len(history) == 1
    assert history[0]["written_by"] == "app"


async def test_a_version_is_restored_and_the_restore_is_undoable(api) -> None:
    note = await create(api, "Texto", "original")
    await api.put(f"/notes/{note['id']}", json={"content": "cambiado"})
    (first,) = (await api.get(f"/notes/{note['id']}/revisions")).json()
    old = (await api.get(f"/notes/{note['id']}/revisions/{first['id']}")).json()

    restored = await api.post(f"/notes/{note['id']}/revisions/{first['id']}/restore")

    assert old["content"] == "original"
    assert restored.json()["content"] == "original"
    history = (await api.get(f"/notes/{note['id']}/revisions")).json()
    assert [
        (await api.get(f"/notes/{note['id']}/revisions/{r['id']}")).json()["content"]
        for r in history
    ] == ["cambiado", "original"]


async def test_the_daily_note_is_created_once_in_its_folder(api) -> None:
    first = await api.post("/daily", params={"day": "2026-09-28"})
    again = await api.post("/daily", params={"day": "2026-09-28"})

    assert first.json()["path"] == "Diario/2026-09-28"
    assert again.json()["id"] == first.json()["id"]


async def test_the_graph_has_the_notes_and_the_links_between_them(api) -> None:
    a = await create(api, "A", "[[B]] [[Nada]]")
    b = await create(api, "B", "[[C]]")
    c = await create(api, "C")
    await create(api, "Suelta")

    whole = (await api.get("/graph")).json()
    local = (await api.get("/graph", params={"center": a["id"], "depth": 1})).json()

    assert sorted(map(tuple, whole["edges"])) == sorted([(a["id"], b["id"]), (b["id"], c["id"])])
    assert len(whole["nodes"]) == 4
    assert {n["title"]: n["depth"] for n in local["nodes"]} == {"A": 0, "B": 1}


async def test_the_app_is_served_for_any_of_its_paths(api, tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>Notebook</title>")
    monkeypatch.setenv("UI_DIST", str(tmp_path))

    page = await api.get("/notebook/nota/cualquiera")
    ready = await api.get("/readyz")

    assert page.status_code == 200 and "Notebook" in page.text
    assert ready.status_code == 200


async def test_an_unknown_note_is_a_404(api) -> None:
    response = await api.get("/notes/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert isinstance(response, httpx.Response)


async def test_the_properties_form_changes_them_without_touching_the_text(api) -> None:
    note = await create(api, "Con", "---\na: 1\nb: x\n---\nTexto\n")

    changed = await api.put(
        f"/notes/{note['id']}/properties", json={"set": {"b": "y", "c": [1, 2]}, "remove": ["a"]}
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["content"] == "---\nb: y\nc:\n  - 1\n  - 2\n---\nTexto\n"
    history = (await api.get(f"/notes/{note['id']}/revisions")).json()
    assert len(history) == 1
