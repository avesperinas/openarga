from __future__ import annotations

import base64
import secrets

import httpx
import pytest

from hub import capabilities
from hub.providers import github

TOKEN = secrets.token_hex(16)
PAT = "github_pat_" + "A1b2C3d4" * 6


class GitHub:
    def __init__(self) -> None:
        self.head: str | None = None
        self.commits: dict[str, dict] = {}
        self.trees: list[dict] = []
        self.blobs: list[str] = []
        self.asked: list[tuple[str, str]] = []
        self.token_ok = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append((request.method, request.url.path))
        assert request.url.host == "api.github.com"
        if not self.token_ok or request.headers["authorization"] != f"Bearer {PAT}":
            return httpx.Response(401, json={"message": "Bad credentials"})
        path = request.url.path.removeprefix("/repos/ana/notas")
        body = httpx.Request(request.method, request.url, content=request.content).read()
        payload = __import__("json").loads(body) if body else {}
        if request.method == "GET" and path == "/git/ref/heads/main":
            if self.head is None:
                return httpx.Response(409, json={"message": "Git Repository is empty."})
            return httpx.Response(200, json={"object": {"sha": self.head}})
        if request.method == "GET" and path == "":
            return httpx.Response(200, json={"full_name": "ana/notas"})
        if request.method == "PUT" and path == "/contents/README.md":
            self.head = "c0"
            self.commits["c0"] = {"tree": "t0"}
            return httpx.Response(201, json={"commit": {"sha": "c0"}})
        if request.method == "GET" and path.startswith("/git/commits/"):
            sha = path.rsplit("/", 1)[1]
            return httpx.Response(
                200, json={"sha": sha, "tree": {"sha": self.commits[sha]["tree"]}}
            )
        if request.method == "POST" and path == "/git/blobs":
            self.blobs.append(base64.b64decode(payload["content"]).hex())
            return httpx.Response(201, json={"sha": f"b{len(self.blobs)}"})
        if request.method == "POST" and path == "/git/trees":
            self.trees.append(payload)
            return httpx.Response(201, json={"sha": f"t{len(self.trees)}"})
        if request.method == "POST" and path == "/git/commits":
            sha = f"c{len(self.commits)}"
            self.commits[sha] = {"tree": payload["tree"], "message": payload["message"]}
            assert payload["parents"] == [self.head]
            return httpx.Response(201, json={"sha": sha})
        if request.method == "PATCH" and path == "/git/refs/heads/main":
            self.head = payload["sha"]
            return httpx.Response(200, json={"object": {"sha": self.head}})
        raise AssertionError(f"nadie debería pedir {request.method} {request.url}")


@pytest.fixture
def hub(monkeypatch) -> GitHub:
    fake = GitHub()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(
        capabilities,
        "kernel_transport",
        lambda: httpx.MockTransport(lambda _r: httpx.Response(201, json={"created": True})),
    )
    return fake


def push(api, body: dict):
    return api.post(
        "/capabilities/notes.push",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "notebook"},
    )


async def connect(api, repo: str = "https://github.com/ana/notas.git") -> httpx.Response:
    return await api.post(
        "/connections",
        json={"provider": "github", "secrets": {"token": f"  {PAT} "}, "settings": {"repo": repo}},
    )


async def test_the_connection_cleans_its_token_and_its_repo(api, hub) -> None:
    bad_token = await api.post(
        "/connections",
        json={
            "provider": "github",
            "secrets": {"token": "hola"},
            "settings": {"repo": "ana/notas"},
        },
    )
    bad_repo = await connect(api, "notas")
    created = await connect(api)

    assert bad_token.status_code in (400, 422)
    assert bad_repo.status_code in (400, 409, 422)
    assert created.status_code == 201, created.text
    detail = (await api.get(f"/connections/{created.json()['id']}")).json()
    assert detail["settings"] == {"repo": "ana/notas", "branch": "main"}


async def test_an_empty_repo_starts_itself_and_a_batch_is_one_commit(api, hub) -> None:
    await connect(api)

    answer = await push(
        api,
        {
            "key": "tanda-1",
            "message": "Notebook: 2 notas",
            "files": [
                {"path": "Study/Alemán/DE 1.1 Kasus.md", "text": "# Kasus\n"},
                {"path": "Adjuntos/tabla.png", "base64": base64.b64encode(b"\x89PNG").decode()},
            ],
            "deletes": ["Vieja.md"],
        },
    )

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert (body["outcome"], body["commit"], body["repeated"]) == ("ok", "c1", False)
    assert body["url"] == "https://github.com/ana/notas/commit/c1"
    [tree] = hub.trees
    assert tree["base_tree"] == "t0"
    assert tree["tree"] == [
        {
            "path": "Study/Alemán/DE 1.1 Kasus.md",
            "mode": "100644",
            "type": "blob",
            "content": "# Kasus\n",
        },
        {"path": "Adjuntos/tabla.png", "mode": "100644", "type": "blob", "sha": "b1"},
        {"path": "Vieja.md", "mode": "100644", "type": "blob", "sha": None},
    ]
    assert hub.head == "c1"
    assert hub.commits["c1"]["message"] == "Notebook: 2 notas"


async def test_the_same_batch_twice_is_written_once(api, hub) -> None:
    await connect(api)
    batch = {"key": "tanda-1", "message": "m", "files": [{"path": "a.md", "text": "a"}]}

    first = (await push(api, batch)).json()
    again = (await push(api, batch)).json()

    assert first["repeated"] is False and again["repeated"] is True
    assert again["outcome"] == "ok"
    assert len(hub.trees) == 1


async def test_without_a_repo_it_says_so(api, hub) -> None:
    answer = await push(api, {"key": "k", "message": "m", "files": []})

    assert answer.status_code == 404
    assert "GitHub" in answer.json()["detail"]


async def test_a_token_github_refuses_is_an_error_in_the_run(api, hub) -> None:
    created = await connect(api)
    hub.token_ok = False

    body = (
        await push(api, {"key": "k", "message": "m", "files": [{"path": "a.md", "text": "a"}]})
    ).json()

    assert body["outcome"] == "error"
    assert "token" in body["detail"]
    ficha = (await api.get(f"/connections/{created.json()['id']}")).json()
    assert ficha["runs"][0]["outcome"] == "error"


def test_the_repo_is_written_as_user_and_name() -> None:
    assert github.clean_settings({"repo": "https://github.com/ana/notas.git"}) == {
        "repo": "ana/notas",
        "branch": "main",
    }
    with pytest.raises(ValueError):
        github.clean_settings({"repo": "ana/notas/extra"})
    with pytest.raises(ValueError):
        github.clean_settings({"repo": "ana/notas", "branch": "a..b"})
