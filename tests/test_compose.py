import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import compose  # noqa: E402

EXAMPLE = yaml.safe_load((ROOT / "openarga.example.yaml").read_text(encoding="utf-8"))


def with_changes(**changes):
    config = yaml.safe_load(yaml.safe_dump(EXAMPLE))
    config.update(changes)
    return config


def test_the_committed_compose_file_is_generated_from_the_example():
    assert compose.main(["--config", str(ROOT / "openarga.example.yaml"), "--check"]) == 0


def test_every_module_with_an_image_gets_a_service_and_publishers_get_a_worker():
    services = compose.generate(EXAMPLE)["services"]
    for module_id, folder in compose.module_folders(ROOT).items():
        assert services[module_id]["build"]["dockerfile"] == f"{folder}/Dockerfile"
    assert services["vitals-worker"]["command"] == ["python", "-m", "vitals.publisher"]
    assert "hub-worker" not in services
    assert "_template" not in services


def test_a_fork_module_in_custom_joins_the_stack(tmp_path):
    for folder in ("modules/money", "modules/custom/garden/src/garden"):
        (tmp_path / folder).mkdir(parents=True)
    (tmp_path / "modules/money/manifest.yaml").write_text("id: money\n")
    (tmp_path / "modules/money/Dockerfile").write_text("")
    (tmp_path / "modules/custom/garden/manifest.yaml").write_text("id: garden\n")
    (tmp_path / "modules/custom/garden/Dockerfile").write_text("")
    (tmp_path / "modules/custom/garden/src/garden/publisher.py").write_text("")
    services = compose.generate(EXAMPLE, tmp_path)["services"]
    assert services["garden"]["build"]["dockerfile"] == "modules/custom/garden/Dockerfile"
    assert services["garden-worker"]["command"] == ["python", "-m", "garden.publisher"]
    assert services["money"]["build"]["dockerfile"] == "modules/money/Dockerfile"


def test_disabling_two_modules_leaves_them_out_of_the_stack():
    config = with_changes(modules={"enabled": "all", "disabled": ["travel", "study"]})
    services = compose.generate(config)["services"]
    for gone in ("travel", "travel-worker", "study", "study-worker"):
        assert gone not in services
    assert "TRAVEL_DB_PASSWORD" not in services["roles"]["environment"]
    assert {"planner", "planner-worker", "kernel", "gateway", "mcp", "auth"} <= set(services)


def test_an_explicit_list_enables_only_those_modules():
    services = compose.generate(with_changes(modules={"enabled": ["hub", "money"]}))["services"]
    modules = set(services) & set(compose.available_modules(ROOT))
    assert modules == {"hub", "money"}


def test_an_unknown_module_or_provider_is_refused():
    with pytest.raises(compose.InvalidConfig, match="nope"):
        compose.generate(with_changes(modules={"disabled": ["nope"]}))
    with pytest.raises(compose.InvalidConfig, match="facebook"):
        compose.generate(with_changes(auth={"providers": ["local", "facebook"]}))


def test_instance_defaults_reach_every_application_service():
    config = with_changes(defaults={"locale": "es-ES", "timezone": "Europe/Madrid"})
    services = compose.generate(config)["services"]
    for name in ("kernel", "gateway", "shell", "money", "money-worker"):
        assert services[name]["environment"]["OPENARGA_LOCALE"] == "es-ES"
        assert "OPENARGA_REGION" not in services[name]["environment"]


def test_a_domain_sets_the_public_urls():
    services = compose.generate(with_changes(domain="arga.example.org"))["services"]
    gateway = services["gateway"]["environment"]
    assert gateway["PUBLIC_URL"] == "https://arga.example.org"
    assert gateway["MCP_RESOURCE_URL"] == "https://arga.example.org/mcp"
    assert services["auth"]["environment"]["KC_HOSTNAME"] == "https://arga.example.org/auth"


def test_login_providers_only_bring_their_own_settings():
    sync = compose.generate(EXAMPLE)["services"]["auth-sync"]["environment"]
    assert "OPENARGA_ADMIN_PASSWORD" in sync and "GOOGLE_CLIENT_ID" not in sync
    config = with_changes(auth={"providers": ["google", "oidc"]})
    sync = compose.generate(config)["services"]["auth-sync"]["environment"]
    assert "GOOGLE_CLIENT_ID" in sync and "OPENARGA_OIDC_ISSUER" in sync
    assert "OPENARGA_ADMIN_PASSWORD" not in sync


def test_every_variable_the_stack_reads_is_in_the_env_example():
    text = compose.render(compose.generate(EXAMPLE))
    used = set(re.findall(r"\$\{([A-Z0-9_]+)", text))
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = set(re.findall(r"^([A-Z0-9_]+)=", example, re.MULTILINE))
    assert used - declared == set()


def test_a_demo_instance_tells_the_gateway_and_mcp():
    assert "OPENARGA_DEMO" not in compose.generate(EXAMPLE)["services"]["gateway"]["environment"]
    services = compose.generate(with_changes(demo=True))["services"]
    for name in ("gateway", "mcp", "kernel"):
        assert services[name]["environment"].get("OPENARGA_DEMO") == "true", name


def test_copies_per_visitor_are_switched_on_from_the_env_file():
    plain = compose.generate(EXAMPLE)["services"]
    services = compose.generate(with_changes(demo=True))["services"]

    assert "OPENARGA_DEMO_COPIES" not in plain["kernel"]["environment"]
    for name in ("gateway", "kernel"):
        environment = services[name]["environment"]
        assert environment["OPENARGA_DEMO_COPIES"] == "${OPENARGA_DEMO_COPIES:-false}", name
        assert environment["OPENARGA_DEMO_COPY_MINUTES"] == "${OPENARGA_DEMO_COPY_MINUTES:-120}"


def test_keycloak_gets_the_public_url_the_realm_import_needs():
    services = compose.generate(EXAMPLE)["services"]
    assert services["auth"]["environment"]["PUBLIC_URL"] == "http://localhost:8000"
    assert "${PUBLIC_URL}" in (ROOT / "auth/realm.json").read_text(encoding="utf-8")
    domain = compose.generate(with_changes(domain="arga.example.org"))["services"]
    assert domain["auth"]["environment"]["PUBLIC_URL"] == "https://arga.example.org"


def test_the_hub_gets_its_credentials_key_from_the_env_file():
    services = compose.generate(EXAMPLE)["services"]
    assert services["hub"]["environment"]["HUB_CREDENTIALS_KEY"] == "${HUB_CREDENTIALS_KEY}"
    assert "HUB_CREDENTIALS_KEY=\n" in (ROOT / ".env.example").read_text(encoding="utf-8")
    for name, service in services.items():
        if name != "hub":
            assert "HUB_CREDENTIALS_KEY" not in service.get("environment", {})


def test_the_services_that_call_the_ai_can_reach_a_model_on_the_docker_host():
    services = compose.generate(EXAMPLE)["services"]
    assert services["hub"]["extra_hosts"] == ["host.docker.internal:host-gateway"]
    assert "extra_hosts" not in services["kernel"]


def test_every_service_reports_the_release_it_runs():
    services = compose.generate(EXAMPLE)["services"]
    for name in ("kernel", "gateway", "shell", "mcp", "money", "money-worker"):
        assert services[name]["environment"]["APP_VERSION"] == "${OPENARGA_VERSION:-0.1.0}"


def test_the_apps_wait_for_the_hub_so_its_capabilities_answer_from_the_first_call():
    services = compose.generate(EXAMPLE)["services"]
    assert services["money"]["depends_on"]["hub"] == {"condition": "service_healthy"}
    assert "hub" not in services["hub"]["depends_on"]
    assert services["hub"]["healthcheck"] == {"interval": "2s"}


def test_without_the_hub_nothing_waits_for_it():
    config = with_changes(modules={"disabled": ["hub"]})
    services = compose.generate(config)["services"]
    assert "hub" not in services
    assert all("hub" not in service.get("depends_on", {}) for service in services.values())
