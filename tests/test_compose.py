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
