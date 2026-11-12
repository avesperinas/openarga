import pytest
from fastapi.testclient import TestClient

from kernel.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_reads_app_version_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "v0.1.0")
    assert client.get("/version").json() == {"service": "kernel", "version": "v0.1.0"}


def test_version_falls_back_to_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_VERSION", raising=False)
    assert client.get("/version").json()["version"] == "dev"


def test_version_is_read_per_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "v0.1.0")
    assert client.get("/version").json()["version"] == "v0.1.0"
    monkeypatch.setenv("APP_VERSION", "v0.2.0")
    assert client.get("/version").json()["version"] == "v0.2.0"
