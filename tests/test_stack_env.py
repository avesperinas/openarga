from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/stack-env.sh"


def filled() -> dict[str, str]:
    output = subprocess.run(
        ["bash", str(SCRIPT)], check=True, capture_output=True, text=True
    ).stdout
    return dict(
        line.split("=", 1) for line in output.splitlines() if re.match(r"^[A-Z0-9_]+=", line)
    )


def test_every_internal_secret_keeps_its_own_name_and_gets_a_value():
    values = filled()
    for name in (
        "KERNEL_DB_PASSWORD",
        "MODULE_REGISTRATION_TOKEN",
        "KC_ADMIN_PASSWORD",
        "ARGA_WEB_CLIENT_SECRET",
        "SESSION_SECRET",
        "HUB_CREDENTIALS_KEY",
        "OPENARGA_ADMIN_PASSWORD",
        "MONEY_DB_PASSWORD",
    ):
        assert len(values[name]) >= 48, name
    assert not {"PASSWORD", "SECRET", "TOKEN", "KEY"} & values.keys()


def test_the_credentials_key_is_32_bytes_in_hex():
    key = filled()["HUB_CREDENTIALS_KEY"]
    assert len(bytes.fromhex(key)) == 32


@pytest.mark.parametrize(
    "name",
    [
        "OPENARGA_AI_KEY",
        "OPENARGA_BRAVE_KEY",
        "GOOGLE_CLIENT_SECRET",
        "OPENARGA_OIDC_CLIENT_SECRET",
    ],
)
def test_outside_provider_keys_stay_empty(name):
    assert filled()[name] == ""


def test_values_that_are_not_secrets_are_copied_as_they_are():
    values = filled()
    assert values["POSTGRES_DB"] == "openarga"
    assert values["OPENARGA_ADMIN_USERNAME"] == "admin"


def test_every_variable_the_compose_file_requires_ends_up_with_a_value():
    values = filled()
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z0-9_]+)\}", text))
    assert required
    assert [name for name in sorted(required) if not values.get(name)] == []


def test_the_version_comes_from_the_git_tag_or_stays_empty_for_the_default():
    value = filled()["OPENARGA_VERSION"]
    assert value == "" or value[0].isdigit()
