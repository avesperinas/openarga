from __future__ import annotations

import unicodedata

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def nfd(value: str) -> str:
    return unicodedata.normalize("NFD", value)


VAULT = [
    {
        "folder": "B1 Gramatik",
        "title": nfd("DE 4.2 Wechselpräpositionen"),
        "content": "---\nthema: Präpositionen\nnaechste_wiederholung: 2026-10-01\n---\n"
        "# Wechsel\n\nSee [[DE 1.1 Kasus]] and ![[table.png]].\n",
    },
    {
        "folder": "B1 Gramatik",
        "title": "DE 1.1 Kasus",
        "content": f"# Kasus\n\n[[DE 4.2 {nfd('Wechselpräpositionen')}]]\n",
    },
    {"folder": "", "title": "Ideas", "content": "No folder."},
]


async def test_a_vault_comes_in_with_its_links_resolved_and_twice_does_not_duplicate(api) -> None:
    first = await api.post("/import", json={"notes": VAULT})
    again = await api.post("/import", json={"notes": VAULT})

    assert first.json() == {"created": 3, "filled": 0, "skipped": [], "invalid": []}
    assert again.json()["created"] == 0
    assert sorted(again.json()["skipped"]) == [
        "B1 Gramatik/DE 1.1 Kasus",
        "B1 Gramatik/DE 4.2 Wechselpräpositionen",
        "Ideas",
    ]
    tree = (await api.get("/tree")).json()
    kasus = next(n for n in tree["notes"] if n["title"] == "DE 1.1 Kasus")
    links = (await api.get(f"/notes/{kasus['id']}/links")).json()
    assert links["links"][0]["note"]["title"] == "DE 4.2 Wechselpräpositionen"
    assert links["backlinks"][0]["note"]["title"] == "DE 4.2 Wechselpräpositionen"
    note = (await api.get(f"/notes/{kasus['id']}")).json()
    assert note["updated_by"] == "import"


async def test_the_properties_of_the_vault_are_searchable(api) -> None:
    await api.post("/import", json={"notes": VAULT})

    found = await api.post(
        "/tools/search_notes",
        json={
            "properties": [{"name": "naechste_wiederholung", "op": "lte", "value": "2026-10-01"}]
        },
        headers={"x-arga-scopes": "notebook:read"},
    )

    assert [n["path"] for n in found.json()["content"]["notes"]] == [
        "B1 Gramatik/DE 4.2 Wechselpräpositionen"
    ]


async def test_what_cannot_be_saved_is_said_and_does_not_stop_the_rest(api) -> None:
    result = await api.post(
        "/import",
        json={"notes": [{"folder": "", "title": "a|b"}, {"folder": "X", "title": "Fine"}]},
    )

    assert result.json()["created"] == 1
    assert result.json()["invalid"] == [{"path": "a|b", "reason": "a title cannot contain '|'"}]


async def test_an_image_is_stored_once_and_served_by_its_name(api) -> None:
    first = await api.post("/files", params={"name": "table.png"}, content=PNG)
    again = await api.post("/files", params={"name": "Table.PNG"}, content=PNG)
    other = await api.post("/files", params={"name": "table.png"}, content=PNG + b"x")
    served = await api.get("/files/table.png")

    assert first.status_code == 201 and first.json()["existed"] is False
    assert again.json()["existed"] is True
    assert other.status_code == 409
    assert served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert "sandbox" in served.headers["content-security-policy"]


async def test_only_images_and_not_too_big(api) -> None:
    pdf = await api.post("/files", params={"name": "doc.pdf"}, content=b"%PDF")
    empty = await api.post("/files", params={"name": "x.png"}, content=b"")
    missing = await api.get("/files/nada.png")

    assert pdf.status_code == 422
    assert empty.status_code == 422
    assert missing.status_code == 404


async def test_a_null_character_is_dropped_instead_of_breaking_the_batch(api) -> None:
    result = await api.post(
        "/import", json={"notes": [{"folder": "", "title": "Odd", "content": "one\u0000two"}]}
    )
    tree = (await api.get("/tree")).json()
    note = (await api.get(f"/notes/{tree['notes'][0]['id']}")).json()

    assert result.json()["created"] == 1
    assert note["content"] == "onetwo"


async def test_a_note_imported_empty_is_filled_by_importing_it_again(api) -> None:
    empty = await api.post(
        "/import",
        json={
            "notes": [
                {"folder": "claude", "title": "Empty", "content": "\u0000" * 40},
                {"folder": "claude", "title": "With text", "content": "mine"},
            ]
        },
    )
    good = await api.post(
        "/import",
        json={
            "notes": [
                {"folder": "claude", "title": "Empty", "content": "Now yes."},
                {"folder": "claude", "title": "With text", "content": "other"},
            ]
        },
    )
    tree = (await api.get("/tree")).json()
    texts = {
        n["title"]: (await api.get(f"/notes/{n['id']}")).json()["content"] for n in tree["notes"]
    }

    assert empty.json()["created"] == 2
    assert (good.json()["filled"], good.json()["skipped"]) == (1, ["claude/With text"])
    assert texts == {"Empty": "Now yes.", "With text": "mine"}
