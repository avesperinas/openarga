from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from arga_module import RegistrationFailed, main, register


@pytest.fixture
def image(tmp_path: Path) -> Path:
    (tmp_path / "manifest.yaml").write_text("id: demo\nname: Demo\n", encoding="utf-8")
    schema = tmp_path / "schema"
    schema.mkdir()
    (schema / "0002_after.sql").write_text("alter table demo.items add column b int;\n")
    (schema / "0001_init.sql").write_text("create table demo.items (a int);\n")
    return tmp_path


def transport(record: list[httpx.Request], status: int = 200, body: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        record.append(request)
        return httpx.Response(
            status, json=body or {"id": "demo", "version": "v1.0.0", "applied": ["0001_init.sql"]}
        )

    return httpx.MockTransport(handler)


def test_the_manifest_and_the_schema_travel_in_order(image: Path) -> None:
    seen: list[httpx.Request] = []
    with httpx.Client(transport=transport(seen)) as client:
        done = register(
            "http://kernel:8000",
            image / "manifest.yaml",
            image / "schema",
            "v1.0.0",
            "s3cr3t",
            client=client,
        )

    request = seen[0]
    assert str(request.url) == "http://kernel:8000/internal/modules/demo"
    assert request.headers["x-module-token"] == "s3cr3t"
    sent = json.loads(request.content)
    assert sent["manifest"]["id"] == "demo"
    assert [file["name"] for file in sent["schema"]] == ["0001_init.sql", "0002_after.sql"]
    assert sent["version"] == "v1.0.0"
    assert done.applied == ["0001_init.sql"]


def test_a_rejected_registration_is_an_error(image: Path) -> None:
    seen: list[httpx.Request] = []
    with (
        httpx.Client(transport=transport(seen, status=401, body={"detail": "token"})) as client,
        pytest.raises(RegistrationFailed) as error,
    ):
        register(
            "http://kernel:8000",
            image / "manifest.yaml",
            image / "schema",
            "v1",
            "malo",
            client=client,
        )
    assert "401" in str(error.value)


def test_without_the_secret_the_container_does_not_start(
    image: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MODULE_REGISTRATION_TOKEN", raising=False)
    monkeypatch.setenv("MANIFEST_PATH", str(image / "manifest.yaml"))

    assert main([]) == 1
    assert "MODULE_REGISTRATION_TOKEN" in capsys.readouterr().err
