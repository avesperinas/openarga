from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

ALLOWED_DOMAINS = frozenset({"ejemplo.com", "ejemplo.local", "example.com", "example.org"})
ALLOWED_ADDRESSES = frozenset({"noreply@anthropic.com"})

SKIP_SUFFIXES = frozenset({".png", ".ico", ".lock"})
SKIP_NAMES = frozenset({"pnpm-lock.yaml", "uv.lock"})


def tracked_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [
        ROOT / name
        for name in listed.stdout.split("\0")
        if name and Path(name).suffix not in SKIP_SUFFIXES and Path(name).name not in SKIP_NAMES
    ]


def personal_addresses(text: str) -> set[str]:
    found = set()
    for address in EMAIL.findall(text):
        lowered = address.lower()
        if lowered in ALLOWED_ADDRESSES:
            continue
        if lowered.rsplit("@", 1)[-1] in ALLOWED_DOMAINS:
            continue
        found.add(address)
    return found


@pytest.mark.parametrize("path", tracked_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_real_email_addresses_are_committed(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return

    found = personal_addresses(text)

    assert not found, (
        f"{path.relative_to(ROOT)} lleva {sorted(found)}. Principio 10: los fixtures son "
        f"sintéticos. Usa un dominio de ejemplo ({', '.join(sorted(ALLOWED_DOMAINS))})."
    )


PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*[A-Za-z0-9+/=\s]{200,}")

ASSIGNED_SECRET = re.compile(
    r"^[A-Z0-9_]*(KEY|SECRET|TOKEN|PASSWORD)\s*=\s*['\"]?[A-Za-z0-9+/_\-]{32,}", re.MULTILINE
)
SYNTHETIC = re.compile(r"prueba|sintetic|synthetic|ejemplo|example|fake|dummy", re.IGNORECASE)


@pytest.mark.parametrize("path", tracked_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_credential_is_committed(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return

    assert not PRIVATE_KEY.search(text), f"{path.relative_to(ROOT)} lleva una clave privada"
    assigned = [
        found.group(0)
        for found in ASSIGNED_SECRET.finditer(text)
        if not SYNTHETIC.search(found.group(0))
    ]
    assert not assigned, (
        f"{path.relative_to(ROOT)} asigna en claro un secreto: {assigned[0][:24]}…. Si es de "
        f"prueba, que lo diga el valor (`prueba`, `sintetico`), o genéralo al ejecutar."
    )


def test_the_credential_guard_catches_what_it_is_meant_to_catch() -> None:
    body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" * 8
    assert PRIVATE_KEY.search(f"-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----")
    assert not PRIVATE_KEY.search("-----BEGIN PRIVATE KEY-----AAAA-----END PRIVATE KEY-----")
    assert ASSIGNED_SECRET.search("MONEY_CREDENTIALS_KEY=" + "ab12" * 16)
    assert not ASSIGNED_SECRET.search("MONEY_CREDENTIALS_KEY=$(openssl rand -hex 32)")
    assert SYNTHETIC.search('SESSION_SECRET = "secreto-de-sesion-de-prueba-bastante-largo"')
