from __future__ import annotations

import base64
import json

import httpx

PAT = "github_pat_" + "Z9y8X7w6" * 6
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


class Repo:
    def __init__(self) -> None:
        self.head = "c0"
        self.files: dict[str, str] = {"README.md": "# Notas\n"}
        self.messages: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/repos/ana/notas")
        body = json.loads(request.content) if request.content else {}
        if request.method == "GET" and path == "/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": self.head}})
        if request.method == "GET" and path.startswith("/git/commits/"):
            return httpx.Response(200, json={"tree": {"sha": "t-" + self.head}})
        if request.method == "POST" and path == "/git/blobs":
            data = base64.b64decode(body["content"])
            return httpx.Response(201, json={"sha": "blob:" + data.hex()})
        if request.method == "POST" and path == "/git/trees":
            self.pending = body["tree"]
            return httpx.Response(201, json={"sha": "t-next"})
        if request.method == "POST" and path == "/git/commits":
            self.messages.append(body["message"])
            return httpx.Response(201, json={"sha": f"c{len(self.messages)}"})
        if request.method == "PATCH" and path == "/git/refs/heads/main":
            for entry in self.pending:
                if "content" in entry:
                    self.files[entry["path"]] = entry["content"]
                elif entry["sha"] is None:
                    self.files.pop(entry["path"], None)
                else:
                    self.files[entry["path"]] = entry["sha"]
            self.head = body["sha"]
            return httpx.Response(200, json={"object": {"sha": self.head}})
        raise AssertionError(f"nadie debería pedir {request.method} {request.url}")


async def note(api, title: str, content: str, folder: str = "") -> dict:
    response = await api.post("/notes", json={"folder": folder, "title": title, "content": content})
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_change_becomes_a_commit_and_only_the_change_travels(api, hub) -> None:
    repo = Repo()
    hub.answer(repo)
    kasus = await note(api, "DE 1.1 Kasus", "---\nthema: Kasus\n---\n# Kasus\n", "Study/Alemán")
    vieja = await note(api, "Vieja", "se irá")
    await api.post("/files", params={"name": "tabla.png"}, content=PNG)

    before = await api.post("/export")
    assert before.json()["outcome"] == "unconnected"
    assert "GitHub" in before.json()["detail"]
    assert before.json()["pending"] == 3

    connected = await hub.client.post(
        "/connections",
        json={"provider": "github", "secrets": {"token": PAT}, "settings": {"repo": "ana/notas"}},
    )
    assert connected.status_code == 201, connected.text

    first = (await api.post("/export")).json()

    assert (first["outcome"], first["pending"]) == ("ok", 0)
    assert first["commit_url"] == "https://github.com/ana/notas/commit/c1"
    assert repo.files["Study/Alemán/DE 1.1 Kasus.md"] == "---\nthema: Kasus\n---\n# Kasus\n"
    assert repo.files["Vieja.md"] == "se irá"
    assert repo.files["Adjuntos/tabla.png"] == "blob:" + PNG.hex()

    await api.post(
        "/tools/edit_note",
        json={"note": kasus["id"], "old_text": "# Kasus", "new_text": "# Die Kasus"},
        headers={"x-arga-scopes": "notebook:write"},
    )
    await api.delete(f"/notes/{vieja['id']}")
    pending = (await api.get("/export")).json()
    second = (await api.post("/export")).json()

    assert pending["pending"] == 2
    assert second["outcome"] == "ok" and second["pending"] == 0
    assert repo.files["Study/Alemán/DE 1.1 Kasus.md"].endswith("# Die Kasus\n")
    assert "Vieja.md" not in repo.files
    assert repo.messages[1].startswith("Notebook: 1 cambio, 1 borrado (Claude en 1)")
    assert (await api.post("/export")).json()["pending"] == 0
    assert len(repo.messages) == 2


async def test_a_failed_copy_is_said_and_retried_whole(api, hub) -> None:
    calls = {"n": 0}

    def down(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"message": "Bad credentials"})

    hub.answer(down)
    await note(api, "Una", "uno")
    await hub.client.post(
        "/connections",
        json={"provider": "github", "secrets": {"token": PAT}, "settings": {"repo": "ana/notas"}},
    )

    failed = (await api.post("/export")).json()

    assert failed["outcome"] == "error"
    assert "token" in failed["detail"]
    assert failed["pending"] == 1
    assert failed["pushed_at"] is None
