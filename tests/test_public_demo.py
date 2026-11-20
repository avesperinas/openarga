from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/public-demo.sh"
DOMAIN = "openarga-demo.example.org"
TOKEN = "synthetic-tunnel-token-for-the-test"


def run(*arguments: str, token: str | None = None) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key != "TUNNEL_TOKEN"}
    environment["HOME"] = "/nonexistent-home"
    if token:
        environment["TUNNEL_TOKEN"] = token
    return subprocess.run(
        ["bash", str(SCRIPT), *arguments], capture_output=True, text=True, env=environment
    )


def test_the_dry_run_lists_every_step_and_changes_nothing():
    result = run("--dry-run", DOMAIN, token=TOKEN)
    assert result.returncode == 0, result.stderr
    for step in (
        "scripts/compose.py",
        "docker compose up -d --build --wait",
        "demo seed",
        "cloudflared",
        "/etc/cloudflared/tunnel.env (mode 600, owner root)",
    ):
        assert step in result.stdout, step
    assert f"PUBLIC_URL=https://{DOMAIN}" in result.stdout
    assert f"AUTH_ISSUER=https://{DOMAIN}/auth/realms/arga" in result.stdout
    assert f"MCP_PUBLIC_URL=https://{DOMAIN}/mcp" in result.stdout
    assert "OPENARGA_DEMO=true" in result.stdout
    assert "connections: fake" in result.stdout
    assert not Path("/nonexistent-home").exists()


def test_the_token_is_never_printed_nor_logged():
    for arguments in (("--dry-run", DOMAIN), ("--dry-run", DOMAIN, TOKEN)):
        result = run(*arguments, token=TOKEN if len(arguments) == 2 else None)
        assert result.returncode == 0, result.stderr
        assert TOKEN not in result.stdout + result.stderr


def test_the_cron_runs_a_day_and_a_nightly_reset_on_madrid_time():
    result = run("--dry-run", DOMAIN, token=TOKEN)
    madrid = '[ "$(TZ=Europe/Madrid date +\\%H)" = {hour} ]'
    reset = next(line for line in result.stdout.splitlines() if "demo reset" in line)
    day = next(line for line in result.stdout.splitlines() if "demo day" in line)
    assert reset.strip().startswith("30 * * * *") and madrid.format(hour="04") in reset
    assert day.strip().startswith("0 * * * *") and madrid.format(hour="08") in day
    assert "/scripts/public-demo.sh" in day and "CRON_TZ" not in result.stdout


def test_it_asks_for_what_it_needs():
    assert run().returncode != 0
    missing_token = run(DOMAIN)
    assert missing_token.returncode != 0 and "no tunnel token" in missing_token.stderr
    bad_domain = run("not a domain", "token")
    assert bad_domain.returncode != 0 and "not a host name" in bad_domain.stderr
    bad_command = run("demo", "explode")
    assert bad_command.returncode != 0 and "seed|day|reset" in bad_command.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_shellcheck_is_clean():
    result = subprocess.run(
        ["shellcheck", "-x", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout
