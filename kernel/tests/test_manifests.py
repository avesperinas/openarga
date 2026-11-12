import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel import modules
from kernel.db import engine
from kernel.main import app
from kernel.manifests import InvalidManifest, load_all, load_manifest
from kernel.modules import sync

VALID = {
    "id": "health",
    "name": "Salud",
    "version": "0.1.0",
    "database": {"schema": "health", "role": "mod_health", "reads": []},
    "connectors": [
        {"id": "withings", "schedule": "0 */6 * * *", "emits": ["health.weight"]},
    ],
    "api": {"prefix": "/api/health"},
    "tools": [
        {
            "name": "get_body_metrics",
            "scope": "health:read",
            "description": "Peso y composición corporal en un rango de fechas.",
        },
    ],
    "ui": {
        "widgets": [
            {
                "id": "weight_trend",
                "title": "Peso",
                "kind": "chart",
                "sizes": ["2x2", "4x2"],
                "endpoint": "/api/health/widgets/weight-trend",
                "refresh": 300,
            },
        ],
        "view": "/health",
    },
}


def write(root: Path, manifest: dict, directory: str | None = None) -> Path:
    module = root / (directory or manifest.get("id", "health"))
    module.mkdir(parents=True, exist_ok=True)
    path = module / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    return path


def without(*keys: str) -> dict:
    manifest = json.loads(json.dumps(VALID))
    for key in keys:
        target = manifest
        *parents, leaf = key.split(".")
        for parent in parents:
            target = target[parent]
        del target[leaf]
    return manifest


def test_a_complete_manifest_is_valid(tmp_path: Path) -> None:
    manifest = load_manifest(write(tmp_path, VALID))

    assert manifest.id == "health"
    assert manifest.scopes == ["health:read"]
    assert manifest.database.db_schema == "health"


@pytest.mark.parametrize(
    "missing", ["id", "name", "version", "database", "api", "ui", "database.role", "api.prefix"]
)
def test_a_missing_required_field_is_named_in_the_error(tmp_path: Path, missing: str) -> None:
    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, without(missing)))

    assert missing in str(failure.value)
    assert "manifest.yaml" in str(failure.value)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"database": {"schema": "salud", "role": "mod_health"}}, "database.schema"),
        ({"database": {"schema": "health", "role": "health_role"}}, "database.role"),
        ({"database": {"schema": "health", "role": "mod_health", "reads": ["health"]}}, "itself"),
        ({"api": {"prefix": "/health"}}, "api.prefix"),
        ({"ui": {"widgets": [], "view": "/salud/hoy"}}, "ui.view"),
        ({"ui": {"widgets": [], "view": "/Salud"}}, "ui.view"),
        ({"ui": {"widgets": [], "view": "/api"}}, "reserved"),
        ({"ui": {"widgets": [], "view": "/login"}}, "reserved"),
        ({"version": "0.1"}, "version"),
        ({"id": "Health"}, "id"),
    ],
)
def test_the_manifest_must_agree_with_the_module_it_declares(
    tmp_path: Path, change: dict, expected: str
) -> None:
    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, VALID | change))

    assert expected in str(failure.value)


def test_an_app_can_live_at_another_address(tmp_path: Path) -> None:
    widget = {
        "id": "main",
        "title": "Salud",
        "kind": "kpi",
        "sizes": ["2x2"],
        "endpoint": "/api/health/widgets/main",
        "refresh": 60,
        "link": "/salud/hoy",
    }
    manifest = load_manifest(
        write(tmp_path, VALID | {"ui": {"widgets": [widget], "view": "/salud"}})
    )
    assert manifest.ui.view == "/salud"
    with pytest.raises(InvalidManifest):
        load_manifest(
            write(
                tmp_path,
                VALID | {"ui": {"widgets": [widget | {"link": "/health"}], "view": "/salud"}},
            )
        )


def test_a_tool_cannot_claim_a_scope_of_another_module(tmp_path: Path) -> None:
    manifest = VALID | {
        "tools": [{**VALID["tools"][0], "scope": "finance:read"}],
    }

    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, manifest))

    assert "tools.0.scope" in str(failure.value)


def test_a_connector_cannot_emit_events_of_another_module(tmp_path: Path) -> None:
    manifest = VALID | {
        "connectors": [{**VALID["connectors"][0], "emits": ["finance.transaction"]}],
    }

    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, manifest))

    assert "connectors.0.emits.0" in str(failure.value)


def test_an_unknown_key_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, VALID | {"tolls": []}))

    assert "tolls" in str(failure.value)


def test_a_widget_must_hang_from_the_module_api(tmp_path: Path) -> None:
    widget = {**VALID["ui"]["widgets"][0], "endpoint": "/api/finance/widgets/weight-trend"}

    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, VALID | {"ui": {"widgets": [widget], "view": "/health"}}))

    assert "ui.widgets.0.endpoint" in str(failure.value)


def test_a_widget_can_only_lead_to_the_app_of_its_module(tmp_path: Path) -> None:
    ok = {**VALID["ui"]["widgets"][0], "link": "/health/semana"}
    assert load_manifest(write(tmp_path, VALID | {"ui": {"widgets": [ok], "view": "/health"}}))

    for wrong in ("/finance", "/healthy", "https://example.org/health"):
        widget = {**VALID["ui"]["widgets"][0], "link": wrong}
        with pytest.raises(InvalidManifest) as failure:
            load_manifest(write(tmp_path, VALID | {"ui": {"widgets": [widget], "view": "/health"}}))
        assert "ui.widgets.0.link" in str(failure.value)


def test_the_directory_has_to_be_the_module_id(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, VALID, directory="salud"))

    assert "does not match the directory" in str(failure.value)


def test_the_template_is_not_picked_up_as_a_module(tmp_path: Path) -> None:
    write(tmp_path, VALID)
    template = tmp_path / "_template"
    template.mkdir()
    (template / "manifest.yaml").write_text("id: __MODULE_ID__\n")

    assert [manifest.id for manifest in load_all(tmp_path)] == ["health"]


def test_the_repo_manifests_are_valid() -> None:
    root = Path(__file__).resolve().parents[2] / "modules"

    manifests = load_all(root)
    ids = [manifest.id for manifest in manifests]

    assert ids == sorted(set(ids))


@pytest.fixture
async def api(database_url: str):
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.modules"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.modules"))
    await engine().dispose()


async def test_the_registry_lists_what_the_manifests_declare(api, tmp_path: Path) -> None:
    async with engine().begin() as connection:
        await sync(connection, load_all(write(tmp_path, VALID).parent.parent))

    listed = (await api.get("/modules")).json()

    assert len(listed) == 1
    assert listed[0]["id"] == "health"
    assert listed[0]["version"] == "0.1.0"
    assert listed[0]["enabled"] is True
    assert listed[0]["schema"] == "health"
    assert listed[0]["role"] == "mod_health"
    assert listed[0]["api_prefix"] == "/api/health"
    assert listed[0]["view"] == "/health"
    assert listed[0]["scopes"] == ["health:read"]
    assert listed[0]["uses"] == []


async def test_the_catalogue_says_where_a_module_widget_leads(api, tmp_path: Path) -> None:
    linked = {**VALID["ui"]["widgets"][0], "link": "/health"}
    plain = {**VALID["ui"]["widgets"][0], "id": "plain"}
    manifest = VALID | {"ui": {"widgets": [linked, plain], "view": "/health"}}
    async with engine().begin() as connection:
        await sync(connection, load_all(write(tmp_path, manifest).parent.parent))

    catalogue = {w["id"]: w for w in (await api.get("/ui/widgets")).json()}

    assert catalogue[linked["id"]]["link"] == "/health"
    assert catalogue["plain"]["link"] is None
    assert catalogue["events"]["link"] is None


async def test_the_catalogue_paints_each_module_in_its_hue(api, tmp_path: Path) -> None:
    manifest = VALID | {"ui": {**VALID["ui"], "hue": 6}}
    async with engine().begin() as connection:
        await sync(connection, load_all(write(tmp_path, manifest).parent.parent))

    catalogue = {w["id"]: w for w in (await api.get("/ui/widgets")).json()}

    assert catalogue[VALID["ui"]["widgets"][0]["id"]]["hue"] == 6
    assert catalogue["events"]["hue"] == 1


async def test_the_launcher_learns_each_module_family(api, tmp_path: Path) -> None:
    async with engine().begin() as connection:
        await sync(connection, load_all(write(tmp_path, VALID).parent.parent))
    assert (await api.get("/modules")).json()[0]["family"] is None

    manifest = VALID | {"ui": {**VALID["ui"], "family": "body"}}
    async with engine().begin() as connection:
        await sync(connection, load_all(write(tmp_path, manifest).parent.parent))
    assert (await api.get("/modules")).json()[0]["family"] == "body"


def test_work_is_a_family(tmp_path: Path) -> None:
    found = load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "family": "work"}}))

    assert found.ui.family == "work"


@pytest.mark.parametrize("family", ["health", "goals", "growth", "wellbeing", "finance"])
def test_the_new_families_are_families(tmp_path: Path, family: str) -> None:
    found = load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "family": family}}))

    assert found.ui.family == family


def test_the_old_families_still_load(tmp_path: Path) -> None:
    for family in ["body", "home", "work", "world"]:
        found = load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "family": family}}))
        assert found.ui.family == family


def test_the_companion_goes_by_the_calendar(tmp_path: Path) -> None:
    found = load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "family": "companion"}}))

    assert found.ui.family == "companion"


async def test_the_launcher_learns_where_a_module_says_what_is_unseen(api, tmp_path: Path) -> None:
    manifest = VALID | {"ui": {**VALID["ui"], "badge": f"{VALID['api']['prefix']}/badge"}}
    async with engine().begin() as connection:
        await sync(connection, load_all(write(tmp_path, manifest).parent.parent))

    assert (await api.get("/modules")).json()[0]["badge"] == f"{VALID['api']['prefix']}/badge"


def test_a_badge_outside_the_module_api_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest):
        load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "badge": "/api/kernel/x"}}))


async def test_the_shell_learns_where_a_module_searches(api, tmp_path: Path) -> None:
    manifest = VALID | {"ui": {**VALID["ui"], "search": f"{VALID['api']['prefix']}/search"}}
    async with engine().begin() as connection:
        await sync(connection, load_all(write(tmp_path, manifest).parent.parent))

    assert (await api.get("/modules")).json()[0]["search"] == f"{VALID['api']['prefix']}/search"


def test_a_search_outside_the_module_api_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest):
        load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "search": "/api/kernel/x"}}))


def test_the_shell_paths_are_not_an_app_view(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest):
        load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "view": "/search"}}))


def test_a_family_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest):
        load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "family": "salud"}}))


@pytest.mark.parametrize("hue", [0, 9])
def test_a_hue_outside_the_palette_is_refused(hue: int, tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest):
        load_manifest(write(tmp_path, VALID | {"ui": {**VALID["ui"], "hue": hue}}))


async def test_a_module_that_disappears_is_disabled_not_deleted(api, tmp_path: Path) -> None:
    async with engine().begin() as connection:
        await sync(connection, load_all(write(tmp_path, VALID).parent.parent))
        await sync(connection, [])

    listed = (await api.get("/modules")).json()

    assert [item["id"] for item in listed] == ["health"]
    assert listed[0]["enabled"] is False


async def test_syncing_twice_updates_the_version(api, tmp_path: Path) -> None:
    root = write(tmp_path, VALID).parent.parent
    async with engine().begin() as connection:
        await sync(connection, load_all(root))
        write(tmp_path, VALID | {"version": "0.2.0"})
        await sync(connection, load_all(root))

    listed = (await api.get("/modules")).json()

    assert [(item["id"], item["version"]) for item in listed] == [("health", "0.2.0")]


async def test_the_registry_is_empty_until_there_is_a_module(api) -> None:
    assert (await api.get("/modules")).json() == []


def test_the_sync_command_refuses_an_invalid_manifest(
    tmp_path: Path, database_url: str, capsys
) -> None:
    write(tmp_path, without("api.prefix"))

    assert modules.main([str(tmp_path)]) == 1
    assert "api.prefix" in capsys.readouterr().err


def test_a_module_cannot_claim_the_kernel_id(tmp_path: Path) -> None:
    reserved = {
        **VALID,
        "id": "kernel",
        "database": {"schema": "kernel", "role": "mod_kernel", "reads": []},
        "api": {"prefix": "/api/kernel"},
        "connectors": [],
        "tools": [],
        "ui": {"widgets": [], "view": "/kernel"},
    }

    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, reserved))

    assert "reserved by the system" in str(failure.value)


@pytest.mark.parametrize("module_id", ["login", "logout"])
def test_a_module_cannot_claim_the_login_of_the_gateway(tmp_path: Path, module_id: str) -> None:
    reserved = {
        **VALID,
        "id": module_id,
        "database": {"schema": module_id, "role": f"mod_{module_id}", "reads": []},
        "api": {"prefix": f"/api/{module_id}"},
        "connectors": [],
        "tools": [],
        "ui": {"widgets": [], "view": f"/{module_id}"},
    }

    with pytest.raises(InvalidManifest) as failure:
        load_manifest(write(tmp_path, reserved))

    assert "reserved by the system" in str(failure.value)


def test_a_widget_cannot_declare_a_size_the_grid_cannot_draw(tmp_path: Path) -> None:
    manifest = deepcopy(VALID)
    manifest["ui"]["widgets"][0]["sizes"] = ["7x9"]

    with pytest.raises(InvalidManifest) as raised:
        load_manifest(write(tmp_path, manifest))

    assert "ui.widgets.0.sizes.0" in str(raised.value)


def test_the_strips_are_sizes_the_grid_draws(tmp_path: Path) -> None:
    manifest = deepcopy(VALID)
    manifest["ui"]["widgets"][0]["sizes"] = ["2x1", "4x1", "4x4"]

    assert load_manifest(write(tmp_path, manifest)).ui.widgets[0].sizes == ["2x1", "4x1", "4x4"]


def test_a_widget_cannot_declare_a_body_the_shell_cannot_paint(tmp_path: Path) -> None:
    manifest = deepcopy(VALID)
    manifest["ui"]["widgets"][0]["kind"] = "inventado"

    with pytest.raises(InvalidManifest) as raised:
        load_manifest(write(tmp_path, manifest))

    assert "ui.widgets.0.kind" in str(raised.value)


def test_a_manifest_written_before_kind_existed_still_validates(tmp_path: Path) -> None:
    manifest = deepcopy(VALID)
    del manifest["ui"]["widgets"][0]["kind"]

    loaded = load_manifest(write(tmp_path, manifest))

    assert loaded.ui.widgets[0].kind == "kpi"


def test_a_connector_can_declare_the_credential_each_person_gives_it(tmp_path: Path) -> None:
    credential = {
        "key": "withings_token",
        "label": "Token de Withings",
        "help": "Lo generas en la web de Withings.",
    }
    manifest = load_manifest(
        write(
            tmp_path,
            {**VALID, "connectors": [{**VALID["connectors"][0], "credential": credential}]},
        )
    )

    assert manifest.connectors[0].credential.key == "withings_token"


@pytest.mark.parametrize(
    "credential",
    [
        {"key": "Con Espacios", "label": "Token", "help": "Lo generas en la web."},
        {"key": "token", "label": "", "help": "Lo generas en la web."},
        {"key": "token", "label": "Token", "help": "corta"},
        {"key": "token", "label": "Token", "help": "Lo generas en la web.", "value": "no"},
    ],
    ids=["clave", "etiqueta", "ayuda", "campo-de-mas"],
)
def test_a_credential_that_cannot_be_shown_is_refused(tmp_path: Path, credential: dict) -> None:
    with pytest.raises(InvalidManifest):
        load_manifest(
            write(
                tmp_path,
                {**VALID, "connectors": [{**VALID["connectors"][0], "credential": credential}]},
            )
        )


def with_fields(**fields) -> dict:
    manifest = deepcopy(VALID)
    manifest.update(fields)
    return manifest


def test_a_module_can_consume_what_the_hub_brings(tmp_path: Path) -> None:
    manifest = load_manifest(
        write(
            tmp_path,
            with_fields(consumes=["finance.balance", "hub.run"], uses=["claude.ping"]),
        )
    )

    assert manifest.consumes == ["finance.balance", "hub.run"]
    assert manifest.uses == ["claude.ping"]


def test_health_places_and_books_can_be_consumed(tmp_path: Path) -> None:
    vitals = json.loads(json.dumps(VALID).replace("health", "vitals"))
    consumes = ["health.steps", "places.place", "books.book"]
    manifest = load_manifest(write(tmp_path, {**vitals, "consumes": consumes}))

    assert manifest.consumes == consumes


def test_a_calendar_can_be_consumed_and_subscribed(tmp_path: Path) -> None:
    manifest = load_manifest(
        write(
            tmp_path,
            with_fields(
                consumes=["calendar.event", "calendar.feed", "hub.run"],
                uses=["calendar.subscribe", "calendar.search"],
            ),
        )
    )

    assert manifest.consumes == ["calendar.event", "calendar.feed", "hub.run"]
    assert manifest.uses == ["calendar.subscribe", "calendar.search"]


def test_an_invented_category_cannot_be_consumed(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match=r"consumes\.0 must start with one of"):
        load_manifest(write(tmp_path, with_fields(consumes=["astrology.forecast"])))


def test_a_manifest_without_consumes_or_uses_is_still_valid(tmp_path: Path) -> None:
    manifest = load_manifest(write(tmp_path, VALID))

    assert manifest.consumes == []
    assert manifest.uses == []


def test_a_module_cannot_consume_another_module_events(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match=r"consumes\.0 must start with one of"):
        load_manifest(write(tmp_path, with_fields(consumes=["money.movement"])))


def test_consumes_does_not_repeat(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match="consumes has duplicate ids"):
        load_manifest(write(tmp_path, with_fields(consumes=["finance.balance"] * 2)))


@pytest.mark.parametrize("capability", ["claude", "Claude.ping", "claude.ping.now", "claude-ping"])
def test_uses_names_a_capability(tmp_path: Path, capability: str) -> None:
    with pytest.raises(InvalidManifest, match="uses.0"):
        load_manifest(write(tmp_path, with_fields(uses=[capability])))


def test_a_module_publishes_its_own_types_under_a_known_contract(tmp_path: Path) -> None:
    manifest = load_manifest(
        write(
            tmp_path,
            with_fields(
                publishes=[{"type": "health.weight", "contract": "body_weight"}],
                receives=["agenda"],
            ),
        )
    )

    assert [(one.type, one.contract) for one in manifest.publishes] == [
        ("health.weight", "body_weight")
    ]
    assert manifest.receives == ["agenda"]


def test_a_module_cannot_publish_another_module_type(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match=r"publishes\.0\.type must start with 'health\.'"):
        load_manifest(
            write(
                tmp_path,
                with_fields(publishes=[{"type": "money.movement", "contract": "agenda"}]),
            )
        )


@pytest.mark.parametrize("field", ["publishes", "receives"])
def test_a_contract_is_one_the_system_knows(tmp_path: Path, field: str) -> None:
    value = (
        [{"type": "health.weight", "contract": "weight"}] if field == "publishes" else ["weight"]
    )
    with pytest.raises(InvalidManifest, match=f"{field}.0"):
        load_manifest(write(tmp_path, with_fields(**{field: value})))


def test_a_module_never_receives_by_naming_another(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match="receives.0 must be one of"):
        load_manifest(write(tmp_path, with_fields(receives=["training"])))


def test_a_module_provides_only_a_known_service(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match="provides.0 must be one of"):
        load_manifest(write(tmp_path, with_fields(provides=["shopping.remove"])))


def test_a_module_does_not_ask_itself(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match="does not ask itself"):
        load_manifest(
            write(tmp_path, with_fields(provides=["shopping.add"], uses=["shopping.add"]))
        )


def test_two_modules_cannot_serve_the_same_thing(tmp_path: Path) -> None:
    for module in ("health", "diet"):
        manifest = deepcopy(with_fields(provides=["shopping.add"]))
        manifest.update(
            id=module,
            database={"schema": module, "role": f"mod_{module}", "reads": []},
            api={"prefix": f"/api/{module}"},
            connectors=[],
            tools=[],
            ui={"widgets": [], "view": f"/{module}"},
        )
        write(tmp_path, manifest, module)

    with pytest.raises(InvalidManifest, match="served by more than one module"):
        load_all(tmp_path)


def test_each_app_serves_moving_what_it_publishes(tmp_path: Path) -> None:
    for module in ("health", "diet"):
        manifest = deepcopy(
            with_fields(
                provides=["agenda.move"],
                publishes=[{"type": f"{module}.session", "contract": "agenda"}],
            )
        )
        manifest.update(
            id=module,
            database={"schema": module, "role": f"mod_{module}", "reads": []},
            api={"prefix": f"/api/{module}"},
            connectors=[],
            tools=[],
            ui={"widgets": [], "view": f"/{module}"},
        )
        write(tmp_path, manifest, module)

    assert len(load_all(tmp_path)) == 2


def test_moving_is_only_for_who_publishes_something_with_a_date(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match="needs publishing 'agenda'"):
        load_manifest(write(tmp_path, with_fields(provides=["agenda.move"])))


def test_an_app_publishes_its_figures_and_another_receives_them(tmp_path: Path) -> None:
    publisher = load_manifest(
        write(tmp_path, with_fields(publishes=[{"type": "health.metric", "contract": "metric"}]))
    )
    receiver = load_manifest(write(tmp_path, with_fields(receives=["metric"])))

    assert [(one.type, one.contract) for one in publisher.publishes] == [
        ("health.metric", "metric")
    ]
    assert receiver.receives == ["metric"]


def test_a_widget_can_ask_something_when_placed(tmp_path: Path) -> None:
    widget = {
        **VALID["ui"]["widgets"][0],
        "option": {"label": "Cuenta", "endpoint": "/api/health/widgets/x/options"},
    }
    manifest = load_manifest(
        write(tmp_path, VALID | {"ui": {"widgets": [widget], "view": "/health"}})
    )
    assert manifest.ui.widgets[0].option.label == "Cuenta"
    foreign = {**widget, "option": {"label": "Cuenta", "endpoint": "/api/finance/options"}}
    with pytest.raises(InvalidManifest):
        load_manifest(write(tmp_path, VALID | {"ui": {"widgets": [foreign], "view": "/health"}}))
    sloppy = {**widget, "option": {"label": "Cuenta", "endpoint": "/api/health/o", "extra": 1}}
    with pytest.raises(InvalidManifest):
        load_manifest(write(tmp_path, VALID | {"ui": {"widgets": [sloppy], "view": "/health"}}))


CALENDAR_INLET = {
    "id": "calendar",
    "title": "Calendario",
    "contracts": ["calendar.event", "calendar.feed"],
    "settings": [
        {"key": "name", "kind": "text", "label": "Nombre"},
        {"key": "tone", "kind": "tone", "label": "Color"},
    ],
}


def test_an_inlet_accepts_source_contracts_and_the_app_reads_them(tmp_path: Path) -> None:
    manifest = load_manifest(
        write(
            tmp_path,
            with_fields(consumes=["calendar.feed", "hub.run"], inlets=[CALENDAR_INLET]),
        )
    )

    assert manifest.inlets[0].contracts == ["calendar.event", "calendar.feed"]
    assert [setting.kind for setting in manifest.inlets[0].settings] == ["text", "tone"]
    assert manifest.consumes == ["calendar.feed", "hub.run", "calendar.event"]


def test_an_inlet_only_takes_contracts_the_system_knows(tmp_path: Path) -> None:
    with pytest.raises(InvalidManifest, match=r"inlets\.0\.contracts\.0 must be one of"):
        load_manifest(
            write(tmp_path, with_fields(inlets=[{**CALENDAR_INLET, "contracts": ["calendar.x"]}]))
        )


def test_a_contract_enters_by_one_inlet_only(tmp_path: Path) -> None:
    second = {"id": "other", "title": "Otro", "contracts": ["calendar.feed"]}
    with pytest.raises(InvalidManifest, match="already taken by inlet 'calendar'"):
        load_manifest(write(tmp_path, with_fields(inlets=[CALENDAR_INLET, second])))


def test_an_inlet_setting_is_of_a_kind_the_ui_can_draw(tmp_path: Path) -> None:
    odd = {**CALENDAR_INLET, "settings": [{"key": "mode", "kind": "slider", "label": "X"}]}
    with pytest.raises(InvalidManifest, match="inlets.0.settings.0.kind"):
        load_manifest(write(tmp_path, with_fields(inlets=[odd])))


def test_a_choice_setting_has_its_choices(tmp_path: Path) -> None:
    empty = {**CALENDAR_INLET, "settings": [{"key": "mode", "kind": "choice", "label": "X"}]}
    with pytest.raises(InvalidManifest, match="a choice needs choices"):
        load_manifest(write(tmp_path, with_fields(inlets=[empty])))


def test_inlets_do_not_repeat(tmp_path: Path) -> None:
    again = {"id": "calendar", "title": "Otra", "contracts": ["finance.balance"]}
    with pytest.raises(InvalidManifest, match="inlets has duplicate ids"):
        load_manifest(write(tmp_path, with_fields(inlets=[CALENDAR_INLET, again])))


def test_every_app_that_reads_a_source_takes_it_through_an_inlet() -> None:
    from kernel.manifests import SOURCE_CONTRACTS, load_all

    root = Path(__file__).resolve().parents[2] / "modules"
    for manifest in load_all(root):
        taken = {contract for inlet in manifest.inlets for contract in inlet.contracts}
        loose = sorted(set(manifest.consumes) & SOURCE_CONTRACTS - taken)
        assert not loose, f"{manifest.id} lee {loose} sin una toma"


async def test_the_registry_lists_each_app_inlet_for_the_hub(api, tmp_path: Path) -> None:
    async with engine().begin() as connection:
        await sync(
            connection,
            load_all(write(tmp_path, with_fields(inlets=[CALENDAR_INLET])).parent.parent),
        )
        stored = await connection.scalar(
            text("select manifest->'consumes' from kernel.modules where id = 'health'")
        )

    listed = (await api.get("/inlets")).json()

    assert stored == ["calendar.event", "calendar.feed"]
    assert len(listed) == 1
    assert listed[0]["key"] == "health.calendar"
    assert listed[0]["module"] == "health"
    assert listed[0]["contracts"] == ["calendar.event", "calendar.feed"]
    assert [one["key"] for one in listed[0]["settings"]] == ["name", "tone"]


async def test_the_registry_says_what_each_app_asks_for(api, tmp_path: Path) -> None:
    async with engine().begin() as connection:
        await sync(
            connection,
            load_all(write(tmp_path, with_fields(uses=["books.search"])).parent.parent),
        )

    [listed] = (await api.get("/modules")).json()

    assert listed["uses"] == ["books.search"]
