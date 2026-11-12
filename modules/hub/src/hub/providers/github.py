from __future__ import annotations

import base64
import contextlib
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from hub.declare import Provider, Secret, Setting
from hub.providers import SourceError

API = "https://api.github.com"
TOKEN = "token"
REPO = "repo"
BRANCH = "branch"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


def normalise(_key: str, raw: str) -> str:
    token = raw.strip()
    if not re.fullmatch(r"(github_pat_|ghp_|gho_|ghs_)[A-Za-z0-9_]{20,255}", token):
        raise ValueError("eso no parece un token de GitHub: empieza por github_pat_")
    return token


def clean_settings(raw: dict[str, Any]) -> dict[str, Any]:
    repo = str(raw.get(REPO) or "").strip().removeprefix("https://github.com/").strip("/")
    repo = repo.removesuffix(".git")
    if not REPO_PATTERN.match(repo):
        raise ValueError("el repo va como usuario/nombre, por ejemplo ana/notas")
    branch = str(raw.get(BRANCH) or "main").strip() or "main"
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", branch) or ".." in branch:
        raise ValueError("ese nombre de rama no vale")
    return {REPO: repo, BRANCH: branch}


@dataclass
class Change:
    texts: dict[str, str] = field(default_factory=dict)
    binaries: dict[str, str] = field(default_factory=dict)
    deletes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Pushed:
    commit: str
    url: str


def _headers(token: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {token}",
        "accept": "application/vnd.github+json",
        "x-github-api-version": "2022-11-28",
        "user-agent": "arga-hub",
    }


def _fail(response: httpx.Response, doing: str) -> SourceError:
    if response.status_code == 401:
        return SourceError("GitHub no acepta el token: puede que haya caducado")
    if response.status_code in (403, 404):
        return SourceError(
            f"GitHub no deja {doing}: comprueba que el token es de ese repo y puede escribir su "
            "contenido"
        )
    detail = ""
    with contextlib.suppress(ValueError):
        detail = str(response.json().get("message") or "")
    return SourceError(f"GitHub contesta {response.status_code} al {doing}: {detail}".strip(": "))


async def _call(client: httpx.AsyncClient, method: str, url: str, token: str, doing: str, **kw):
    try:
        response = await client.request(method, url, headers=_headers(token), timeout=30.0, **kw)
    except httpx.HTTPError as error:
        raise SourceError(f"GitHub no contesta ({type(error).__name__})") from error
    return response


async def _head(client: httpx.AsyncClient, token: str, repo: str, branch: str) -> str | None:
    got = await _call(
        client, "GET", f"{API}/repos/{repo}/git/ref/heads/{branch}", token, "leer la rama"
    )
    if got.status_code == 200:
        return got.json()["object"]["sha"]
    if got.status_code in (404, 409):
        repo_info = await _call(client, "GET", f"{API}/repos/{repo}", token, "ver el repo")
        if repo_info.status_code != 200:
            raise _fail(repo_info, "ver el repo")
        return None
    raise _fail(got, "leer la rama")


async def _first_commit(client: httpx.AsyncClient, token: str, repo: str, branch: str) -> str:
    readme = (
        "# Notas\n\nCopia de Notebook. Se escribe sola: lo que cambies aquí no vuelve a Notebook.\n"
    )
    made = await _call(
        client,
        "PUT",
        f"{API}/repos/{repo}/contents/README.md",
        token,
        "empezar el repo",
        json={
            "message": "Notebook empieza la copia",
            "content": base64.b64encode(readme.encode()).decode(),
            "branch": branch,
        },
    )
    if made.status_code not in (200, 201):
        raise _fail(made, "empezar el repo")
    return made.json()["commit"]["sha"]


async def push(
    client: httpx.AsyncClient, token: str, repo: str, branch: str, change: Change, message: str
) -> Pushed:
    head = await _head(client, token, repo, branch)
    if head is None:
        head = await _first_commit(client, token, repo, branch)
    commit = await _call(
        client, "GET", f"{API}/repos/{repo}/git/commits/{head}", token, "leer el último commit"
    )
    if commit.status_code != 200:
        raise _fail(commit, "leer el último commit")
    base_tree = commit.json()["tree"]["sha"]

    entries: list[dict[str, Any]] = [
        {"path": path, "mode": "100644", "type": "blob", "content": content}
        for path, content in change.texts.items()
    ]
    for path, encoded in change.binaries.items():
        blob = await _call(
            client,
            "POST",
            f"{API}/repos/{repo}/git/blobs",
            token,
            "subir un fichero",
            json={"content": encoded, "encoding": "base64"},
        )
        if blob.status_code != 201:
            raise _fail(blob, "subir un fichero")
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob.json()["sha"]})
    entries.extend(
        {"path": path, "mode": "100644", "type": "blob", "sha": None} for path in change.deletes
    )

    tree = await _call(
        client,
        "POST",
        f"{API}/repos/{repo}/git/trees",
        token,
        "preparar el árbol",
        json={"base_tree": base_tree, "tree": entries},
    )
    if tree.status_code != 201:
        raise _fail(tree, "preparar el árbol")
    made = await _call(
        client,
        "POST",
        f"{API}/repos/{repo}/git/commits",
        token,
        "hacer el commit",
        json={"message": message, "tree": tree.json()["sha"], "parents": [head]},
    )
    if made.status_code != 201:
        raise _fail(made, "hacer el commit")
    sha = made.json()["sha"]
    moved = await _call(
        client,
        "PATCH",
        f"{API}/repos/{repo}/git/refs/heads/{branch}",
        token,
        "mover la rama",
        json={"sha": sha, "force": False},
    )
    if moved.status_code != 200:
        raise _fail(moved, "mover la rama")
    return Pushed(commit=sha, url=f"https://github.com/{repo}/commit/{sha}")


SOURCES = (
    Provider(
        id="github",
        name="GitHub",
        category="notes",
        description="La copia de tus notas de Notebook en un repo privado tuyo, como ficheros .md que "
        "se abren en Obsidian. Notebook escribe un commit cada vez que cambian, como mucho cada diez "
        "minutos. Es de ida: lo que cambies en el repo no vuelve.",
        capabilities=("action",),
        serves=("notes.push",),
        secrets=(
            Secret(
                "token",
                "Token de GitHub",
                "En github.com, Settings → Developer settings → Fine-grained tokens: solo ese "
                "repo, y en permisos, Contents con lectura y escritura. Empieza por github_pat_.",
            ),
        ),
        settings=(
            Setting("repo", "Repo", "usuario/nombre: el repo privado donde va la copia."),
            Setting("branch", "Rama", "Donde se escribe.", default="main"),
        ),
        available=True,
        single=True,
        normalise=normalise,
        clean=clean_settings,
    ),
)
