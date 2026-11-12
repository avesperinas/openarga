import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REALM = json.loads((ROOT / "auth" / "realm.json").read_text())


def test_the_realm_is_generated_from_the_manifests() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/make_realm.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_the_remote_connector_reaches_every_module_and_nothing_else() -> None:
    (claude,) = [c for c in REALM["clients"] if c["clientId"] == "claude"]
    granted = claude["defaultClientScopes"] + claude["optionalClientScopes"]

    assert "basic" in granted
    assert claude["fullScopeAllowed"] is False
    modules = {path.parent.name for path in (ROOT / "modules").glob("[a-z]*/manifest.yaml")}
    assert {scope for scope in granted if ":" in scope} == {
        f"{module}:{access}" for module in modules for access in ("read", "write")
    }


def test_every_scope_carries_the_audience_of_the_mcp_server() -> None:
    for scope in REALM["clientScopes"]:
        if ":" not in scope["name"]:
            continue
        (audience,) = [
            m for m in scope["protocolMappers"] if m["protocolMapper"] == "oidc-audience-mapper"
        ]
        assert audience["config"]["included.custom.audience"].endswith("/mcp")


def test_nobody_can_register_a_client_or_an_account() -> None:
    assert REALM["registrationAllowed"] is False
    assert [c["clientId"] for c in REALM["clients"] if c.get("publicClient")] == ["claude"]


def test_the_claude_client_needs_pkce_because_it_has_no_secret() -> None:
    (claude,) = [c for c in REALM["clients"] if c["clientId"] == "claude"]

    assert claude["publicClient"] is True
    assert claude["attributes"]["pkce.code.challenge.method"] == "S256"
    assert "secret" not in claude
    assert claude["directAccessGrantsEnabled"] is False
    assert claude["implicitFlowEnabled"] is False


def test_the_sync_file_carries_the_same_scopes_as_the_realm() -> None:
    lines = (ROOT / "auth" / "client-scopes.ndjson").read_text().splitlines()
    synced = [json.loads(line) for line in lines]
    imported = [scope for scope in REALM["clientScopes"] if scope["name"] != "basic"]

    assert synced == imported
    assert all(line.startswith('{"name": "') for line in lines)


def web_client() -> dict:
    (client,) = [c for c in REALM["clients"] if c["clientId"] == "arga-web"]
    return client


def test_the_gateway_logs_people_in_and_nothing_else() -> None:
    client = web_client()

    assert client["publicClient"] is False
    assert client["redirectUris"] == ["${PUBLIC_URL}/login/callback"]
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert client["implicitFlowEnabled"] is False
    assert client["directAccessGrantsEnabled"] is False
    assert client["fullScopeAllowed"] is False
    assert not [
        s for s in client["defaultClientScopes"] + client["optionalClientScopes"] if ":" in s
    ]


def test_the_mail_only_travels_in_the_identity_token() -> None:
    (email,) = [scope for scope in REALM["clientScopes"] if scope["name"] == "email"]

    for mapper in email["protocolMappers"]:
        assert mapper["config"]["id.token.claim"] == "true"
        assert mapper["config"]["access.token.claim"] == "false"
    (claude,) = [c for c in REALM["clients"] if c["clientId"] == "claude"]
    assert "email" not in claude["defaultClientScopes"] + claude["optionalClientScopes"]


def test_the_sync_file_carries_the_same_gateway_client_as_the_realm() -> None:
    synced = json.loads((ROOT / "auth" / "client-arga-web.json").read_text())

    assert synced == web_client()


def test_the_sync_waits_for_keycloak_instead_of_failing_the_deploy() -> None:
    sync = (ROOT / "auth" / "sync.sh").read_text()
    login = sync.split("config credentials")[0]

    assert "for attempt in" in login
    assert 'echo "sync: no se pudo entrar en Keycloak como administrador' in sync
    assert "exit 1" in sync.split("no se pudo entrar en Keycloak")[1]


def test_the_sync_grants_the_same_scopes_the_realm_declares() -> None:
    sync = (ROOT / "auth" / "sync.sh").read_text(encoding="utf-8")
    (claude,) = [c for c in REALM["clients"] if c["clientId"] == "claude"]
    module_scopes = {scope for scope in claude["defaultClientScopes"] if ":" in scope}

    assert module_scopes, "el cliente no declara ningún scope de módulo"
    assert "*:read ]]" not in sync, "el sync concede menos de lo que el realm declara"
    assert '"$name" == *:*' in sync


def run_client() -> dict:
    (client,) = [c for c in REALM["clients"] if c["clientId"] == "claude-run"]
    return client


def test_claude_run_is_confidential_and_asks_for_its_scopes_one_app_at_a_time() -> None:
    client = run_client()

    assert client["publicClient"] is False
    assert client["redirectUris"] == ["${PUBLIC_URL}/api/hub/claude-run/callback"]
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert client["implicitFlowEnabled"] is False
    assert client["directAccessGrantsEnabled"] is False
    assert client["serviceAccountsEnabled"] is False
    assert client["fullScopeAllowed"] is False
    assert client["defaultClientScopes"] == ["basic"]
    assert "outings:write" in client["optionalClientScopes"]
    assert "insights:read" in client["optionalClientScopes"]


def test_the_sync_file_of_claude_run_is_the_realm_one() -> None:
    synced = json.loads((ROOT / "auth" / "client-claude-run.json").read_text())

    assert synced == run_client()
