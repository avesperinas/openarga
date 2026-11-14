from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "auth" / "realm.json"
SCOPES_OUTPUT = ROOT / "auth" / "client-scopes.ndjson"
WEB_CLIENT_OUTPUT = ROOT / "auth" / "client-arga-web.json"
RUN_CLIENT_OUTPUT = ROOT / "auth" / "client-claude-run.json"
PUBLIC_URL = "${PUBLIC_URL}"
RESOURCE = f"{PUBLIC_URL}/mcp"
REDIRECTS = ["https://claude.ai/api/mcp/auth_callback", "https://claude.com/api/mcp/auth_callback"]
WEB_CLIENT = "arga-web"
RUN_CLIENT = "claude-run"
DAY = 86400


def declared_scopes() -> list[str]:
    scopes: set[str] = set()
    for manifest in sorted((ROOT / "modules").glob("[a-z]*/manifest.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        module_id = data.get("id")
        if module_id:
            scopes.update({f"{module_id}:read", f"{module_id}:write"})
    return sorted(scopes)


def client_scope(name: str) -> dict:
    return {
        "name": name,
        "protocol": "openid-connect",
        "attributes": {"include.in.token.scope": "true", "display.on.consent.screen": "false"},
        "protocolMappers": [
            {
                "name": "audiencia del servidor MCP",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "config": {
                    "included.custom.audience": RESOURCE,
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                    "introspection.token.claim": "true",
                },
            }
        ],
    }


BASIC = {
    "name": "basic",
    "protocol": "openid-connect",
    "attributes": {"include.in.token.scope": "false", "display.on.consent.screen": "false"},
    "protocolMappers": [
        {
            "name": "sub",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-sub-mapper",
            "config": {"access.token.claim": "true", "introspection.token.claim": "true"},
        }
    ],
}


EMAIL = {
    "name": "email",
    "protocol": "openid-connect",
    "attributes": {"include.in.token.scope": "true", "display.on.consent.screen": "false"},
    "protocolMappers": [
        {
            "name": "email",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {
                "user.attribute": "email",
                "claim.name": "email",
                "jsonType.label": "String",
                "id.token.claim": "true",
                "access.token.claim": "false",
                "userinfo.token.claim": "true",
            },
        },
        {
            "name": "email verified",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-property-mapper",
            "config": {
                "user.attribute": "emailVerified",
                "claim.name": "email_verified",
                "jsonType.label": "boolean",
                "id.token.claim": "true",
                "access.token.claim": "false",
                "userinfo.token.claim": "true",
            },
        },
    ],
}


def web_client() -> dict:
    return {
        "clientId": WEB_CLIENT,
        "name": "arga",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-secret",
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "consentRequired": False,
        "fullScopeAllowed": False,
        "frontchannelLogout": False,
        "redirectUris": [f"{PUBLIC_URL}/login/callback"],
        "webOrigins": [],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "post.logout.redirect.uris": f"{PUBLIC_URL}/",
        },
        "defaultClientScopes": ["basic", "email"],
        "optionalClientScopes": [],
    }


def run_client() -> dict:
    return {
        "clientId": RUN_CLIENT,
        "name": "Tu Claude, lanzado por arga",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-secret",
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "consentRequired": False,
        "fullScopeAllowed": False,
        "frontchannelLogout": False,
        "redirectUris": [f"{PUBLIC_URL}/api/hub/claude-run/callback"],
        "webOrigins": [],
        "attributes": {"pkce.code.challenge.method": "S256"},
        "defaultClientScopes": ["basic"],
        "optionalClientScopes": declared_scopes(),
    }


def optional(name: str, validations: dict) -> dict:
    return {
        "name": name,
        "displayName": "${" + name + "}",
        "validations": validations,
        "permissions": {"view": ["admin"], "edit": ["admin"]},
        "multivalued": False,
    }


USER_PROFILE = {
    "attributes": [
        {
            "name": "username",
            "displayName": "${username}",
            "validations": {
                "length": {"min": 3, "max": 255},
                "username-prohibited-characters": {},
                "up-username-not-idn-homograph": {},
            },
            "permissions": {"view": ["admin", "user"], "edit": ["admin"]},
            "multivalued": False,
        },
        optional("email", {"email": {}, "length": {"max": 255}}),
        optional("firstName", {"length": {"max": 255}}),
        optional("lastName", {"length": {"max": 255}}),
    ],
    "groups": [],
}


def realm() -> dict:
    scopes = declared_scopes()
    return {
        "realm": "arga",
        "enabled": True,
        "displayName": "OpenArga",
        "internationalizationEnabled": True,
        "supportedLocales": ["en", "es"],
        "defaultLocale": "en",
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "loginWithEmailAllowed": False,
        "rememberMe": True,
        "bruteForceProtected": True,
        "passwordPolicy": "length(12) and notUsername",
        "accessTokenLifespan": 900,
        "ssoSessionIdleTimeout": 14 * DAY,
        "ssoSessionMaxLifespan": 90 * DAY,
        "defaultDefaultClientScopes": [],
        "defaultOptionalClientScopes": [],
        "components": {
            "org.keycloak.userprofile.UserProfileProvider": [
                {
                    "providerId": "declarative-user-profile",
                    "subComponents": {},
                    "config": {"kc.user.profile.config": [json.dumps(USER_PROFILE)]},
                }
            ]
        },
        "roles": {
            "realm": [{"name": "admin", "description": "Administers this OpenArga instance"}]
        },
        "clientScopes": [BASIC, EMAIL, *(client_scope(scope) for scope in scopes)],
        "clients": [
            {
                "clientId": "claude",
                "name": "Claude",
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": True,
                "standardFlowEnabled": True,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": False,
                "consentRequired": False,
                "fullScopeAllowed": False,
                "redirectUris": REDIRECTS,
                "webOrigins": [],
                "attributes": {"pkce.code.challenge.method": "S256"},
                "defaultClientScopes": ["basic", *scopes],
                "optionalClientScopes": [],
            },
            web_client(),
            run_client(),
        ],
    }


def rendered() -> str:
    return json.dumps(realm(), indent=2, ensure_ascii=False) + "\n"


def rendered_scopes() -> str:
    scopes = [EMAIL, *(client_scope(scope) for scope in declared_scopes())]
    lines = [json.dumps(scope, ensure_ascii=False) for scope in scopes]
    return "".join(f"{line}\n" for line in lines)


def rendered_web_client() -> str:
    return json.dumps(web_client(), indent=2, ensure_ascii=False) + "\n"


def rendered_run_client() -> str:
    return json.dumps(run_client(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    outputs = {
        OUTPUT: rendered(),
        SCOPES_OUTPUT: rendered_scopes(),
        WEB_CLIENT_OUTPUT: rendered_web_client(),
        RUN_CLIENT_OUTPUT: rendered_run_client(),
    }
    if "--check" in argv:
        stale = [
            path.name
            for path, body in outputs.items()
            if not path.exists() or path.read_text(encoding="utf-8") != body
        ]
        if stale:
            regenerate = "uv run python scripts/make_realm.py"
            print(f"{', '.join(stale)} out of date: {regenerate}", file=sys.stderr)
            return 1
        print(f"realm ok · {len(declared_scopes())} scope(s)")
        return 0
    for path, body in outputs.items():
        path.write_text(body, encoding="utf-8")
    print(f"auth/realm.json · scopes: {', '.join(declared_scopes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
