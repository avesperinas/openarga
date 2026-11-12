from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from kernel.provision import MODULE_ID_PATTERN, role_for

MANIFEST_GLOB = "[a-z]*/manifest.yaml"

RESERVED_IDS = frozenset({"kernel", "login", "logout"})
RESERVED_VIEWS = RESERVED_IDS | frozenset(
    {"api", "auth", "mcp", "healthz", "readyz", "version", "static", "_next"}
    | {"search", "badges", "envelopes", "panels"}
)
VIEW_PATTERN = r"^/[a-z][a-z0-9_]{1,30}$"

NAME_PATTERN = r"^[a-z][a-z0-9_]{1,60}$"
VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
SCOPE_VERBS = ("read", "write")
SIZE_PATTERN = r"^(1x1|2x1|4x1|1x2|2x2|2x4|4x2|4x4|4x6)$"
EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
CAPABILITY_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"

HUB = "hub"
CATEGORIES = frozenset(
    {
        "finance",
        "ai",
        "food",
        "health",
        "places",
        "books",
        "calendar",
        "notes",
        "economy",
        "leisure",
        "weather",
    }
)

SOURCE_CONTRACTS = frozenset(
    {
        "calendar.event",
        "calendar.feed",
        "calendar.holidays",
        "finance.account",
        "finance.movement",
        "finance.movement_detail",
        "finance.balance",
        "finance.holding",
        "finance.price",
        "finance.trade",
        "health.steps",
        "health.daily",
        "health.profile",
        "health.sleep",
        "health.heart",
        "health.exercise",
        "health.ecg",
        "health.irn",
        "health.device",
        "ai.claude.ping",
        "ai.claude.usage",
        "economy.cpi",
        "leisure.event",
    }
)
INLET_SETTING_KINDS = ("text", "tone", "choice")

CONTRACTS = frozenset(
    {
        "activity",
        "agenda",
        "body_weight",
        "custody",
        "linkable",
        "mention",
        "metric",
        "record",
        "trip",
        "workout",
    }
)
SERVICES = frozenset(
    {
        "shopping.add",
        "notes.list",
        "notes.read",
        "notes.create",
        "notes.write",
        "notes.trash",
        "agenda.move",
        "pantry.search",
        "pantry.import",
        "pantry.nutrients",
        "recipes.search",
        "recipes.nutrients",
        "recipes.create",
        "weight.log",
        "trips.idea",
        "workout.heart",
        "intake.replace_food",
        "books.want",
    }
)
PLATFORM_SERVICES = frozenset({"notify.schedule", "notify.cancel", "notify.sync"})
NOTIFICATION_KIND_PATTERN = r"^[a-z][a-z0-9_]{0,40}$"
ADDRESSED = {"agenda.move": "agenda"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Database(Strict):
    db_schema: str = Field(alias="schema")
    role: str
    reads: list[Annotated[str, Field(pattern=MODULE_ID_PATTERN)]] = []


class Credential(Strict):
    key: Annotated[str, Field(pattern=NAME_PATTERN)]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    help: Annotated[str, Field(min_length=10, max_length=300)]


class Connector(Strict):
    id: Annotated[str, Field(pattern=NAME_PATTERN)]
    schedule: str
    emits: list[Annotated[str, Field(pattern=EVENT_TYPE_PATTERN)]]
    credential: Credential | None = None


class Api(Strict):
    prefix: str


class Published(Strict):
    type: Annotated[str, Field(pattern=EVENT_TYPE_PATTERN)]
    contract: str


class InletChoice(Strict):
    value: Annotated[str, Field(min_length=1, max_length=60)]
    label: Annotated[str, Field(min_length=1, max_length=60)]


class InletSetting(Strict):
    key: Annotated[str, Field(pattern=NAME_PATTERN)]
    kind: Literal["text", "tone", "choice"]
    label: Annotated[str, Field(min_length=1, max_length=40)]
    default: str | int | None = None
    choices: list[InletChoice] = []


class Inlet(Strict):
    id: Annotated[str, Field(pattern=NAME_PATTERN)]
    title: Annotated[str, Field(min_length=1, max_length=40)]
    contracts: Annotated[list[str], Field(min_length=1)]
    settings: list[InletSetting] = []


class Tool(Strict):
    name: Annotated[str, Field(pattern=NAME_PATTERN)]
    scope: str
    description: Annotated[str, Field(min_length=10)]


class WidgetOption(Strict):
    label: Annotated[str, Field(min_length=1, max_length=40)]
    endpoint: str


class Widget(Strict):
    id: Annotated[str, Field(pattern=NAME_PATTERN)]
    title: Annotated[str, Field(min_length=1)]
    kind: Literal[
        "kpi",
        "kpi-delta",
        "chart",
        "bars",
        "heatmap",
        "progress",
        "ring",
        "streak",
        "stats",
        "list",
        "calendar",
        "upnext",
        "shortcuts",
        "agenda",
        "week",
        "tasks",
    ] = "kpi"
    sizes: Annotated[list[Annotated[str, Field(pattern=SIZE_PATTERN)]], Field(min_length=1)]
    endpoint: str
    refresh: Annotated[int, Field(ge=0)] = 0
    link: str | None = None
    option: WidgetOption | None = None


Family = Literal[
    "calendar",
    "health",
    "goals",
    "growth",
    "wellbeing",
    "finance",
    "system",
    "companion",
    "body",
    "home",
    "work",
    "world",
]


class Ui(Strict):
    widgets: list[Widget] = []
    view: str
    hue: Annotated[int, Field(ge=1, le=8)] | None = None
    family: Family | None = None
    badge: str | None = None
    search: str | None = None


class Notification(Strict):
    kind: Annotated[str, Field(pattern=NOTIFICATION_KIND_PATTERN)]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    default: bool = False


Locale = Literal["en", "es"]
LOCALES: tuple[Locale, ...] = ("en", "es")


class Manifest(Strict):
    id: Annotated[str, Field(pattern=MODULE_ID_PATTERN)]
    name: Annotated[str, Field(min_length=1)]
    names: dict[Locale, Annotated[str, Field(min_length=1, max_length=24)]] = {}
    summary: dict[Locale, Annotated[str, Field(min_length=1, max_length=160)]] = {}
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]
    database: Database
    connectors: list[Connector] = []
    consumes: list[Annotated[str, Field(pattern=EVENT_TYPE_PATTERN)]] = []
    inlets: list[Inlet] = []
    uses: list[Annotated[str, Field(pattern=CAPABILITY_PATTERN)]] = []
    publishes: list[Published] = []
    receives: list[str] = []
    provides: list[Annotated[str, Field(pattern=CAPABILITY_PATTERN)]] = []
    notifications: list[Notification] = []
    api: Api
    tools: list[Tool] = []
    ui: Ui

    @property
    def scopes(self) -> list[str]:
        return sorted({tool.scope for tool in self.tools})

    @model_validator(mode="after")
    def _names_start_in_english(self) -> Self:
        for field in ("names", "summary"):
            value = getattr(self, field)
            if value and "en" not in value:
                raise ValueError(f"{field} must include 'en', the source language")
        return self

    @model_validator(mode="after")
    def _the_id_is_not_reserved(self) -> Self:
        if self.id in RESERVED_IDS:
            raise ValueError(f"id: '{self.id}' is reserved by the system")
        return self

    @model_validator(mode="after")
    def _isolation_matches_the_module(self) -> Self:
        if self.database.db_schema != self.id:
            raise ValueError(
                f"database.schema must be '{self.id}', not '{self.database.db_schema}'"
            )
        if self.database.role != role_for(self.id):
            raise ValueError(f"database.role must be '{role_for(self.id)}'")
        if self.id in self.database.reads:
            raise ValueError("database.reads must not list the module itself")
        if len(set(self.database.reads)) != len(self.database.reads):
            raise ValueError("database.reads has duplicates")
        return self

    @model_validator(mode="after")
    def _surfaces_live_under_the_module(self) -> Self:
        if self.api.prefix != f"/api/{self.id}":
            raise ValueError(f"api.prefix must be '/api/{self.id}'")
        if not re.match(VIEW_PATTERN, self.ui.view):
            raise ValueError(f"ui.view must be '/{self.id}' or another single segment like it")
        if self.ui.view[1:] in RESERVED_VIEWS:
            raise ValueError(f"ui.view: '{self.ui.view}' is reserved by the system")
        if self.ui.badge is not None and not self.ui.badge.startswith(f"{self.api.prefix}/"):
            raise ValueError(f"ui.badge must start with '{self.api.prefix}/'")
        if self.ui.search is not None and not self.ui.search.startswith(f"{self.api.prefix}/"):
            raise ValueError(f"ui.search must start with '{self.api.prefix}/'")
        for index, widget in enumerate(self.ui.widgets):
            if not widget.endpoint.startswith(f"{self.api.prefix}/"):
                raise ValueError(
                    f"ui.widgets.{index}.endpoint must start with '{self.api.prefix}/'"
                )
            if widget.option is not None and not widget.option.endpoint.startswith(
                f"{self.api.prefix}/"
            ):
                raise ValueError(
                    f"ui.widgets.{index}.option.endpoint must start with '{self.api.prefix}/'"
                )
            if widget.link is not None and not (
                widget.link == self.ui.view or widget.link.startswith(f"{self.ui.view}/")
            ):
                raise ValueError(f"ui.widgets.{index}.link must be under '{self.ui.view}'")
        return self

    @model_validator(mode="after")
    def _scopes_name_the_module(self) -> Self:
        allowed = [f"{self.id}:{verb}" for verb in SCOPE_VERBS]
        for index, tool in enumerate(self.tools):
            if tool.scope not in allowed:
                raise ValueError(f"tools.{index}.scope must be one of {allowed}")
        return self

    @model_validator(mode="after")
    def _connectors_emit_their_own_domain(self) -> Self:
        for index, connector in enumerate(self.connectors):
            if len(connector.schedule.split()) != 5:
                raise ValueError(
                    f"connectors.{index}.schedule must be a five-field cron expression"
                )
            for position, event_type in enumerate(connector.emits):
                if not event_type.startswith(f"{self.id}."):
                    raise ValueError(
                        f"connectors.{index}.emits.{position} must start with '{self.id}.'"
                    )
        return self

    @model_validator(mode="after")
    def _consumes_what_the_hub_brings(self) -> Self:
        allowed = sorted(CATEGORIES | {HUB})
        for index, event_type in enumerate(self.consumes):
            if event_type.split(".", 1)[0] not in allowed:
                raise ValueError(f"consumes.{index} must start with one of {allowed}")
            if event_type.startswith(f"{self.id}."):
                raise ValueError(f"consumes.{index}: a module already reads its own events")
        return self

    @model_validator(mode="after")
    def _inlets_take_source_contracts(self) -> Self:
        known = sorted(SOURCE_CONTRACTS)
        seen: dict[str, str] = {}
        for index, inlet in enumerate(self.inlets):
            for position, contract in enumerate(inlet.contracts):
                if contract not in SOURCE_CONTRACTS:
                    raise ValueError(f"inlets.{index}.contracts.{position} must be one of {known}")
                if contract in seen:
                    raise ValueError(
                        f"inlets.{index}.contracts.{position}: '{contract}' is already taken by "
                        f"inlet '{seen[contract]}'"
                    )
                seen[contract] = inlet.id
            keys = [setting.key for setting in inlet.settings]
            if len(set(keys)) != len(keys):
                raise ValueError(f"inlets.{index}.settings has duplicate keys")
            for position, setting in enumerate(inlet.settings):
                if setting.kind == "choice" and not setting.choices:
                    raise ValueError(f"inlets.{index}.settings.{position}: a choice needs choices")
        self.consumes = [*self.consumes, *(c for c in seen if c not in self.consumes)]
        return self

    @model_validator(mode="after")
    def _shares_through_contracts(self) -> Self:
        known = sorted(CONTRACTS)
        for index, published in enumerate(self.publishes):
            if not published.type.startswith(f"{self.id}."):
                raise ValueError(f"publishes.{index}.type must start with '{self.id}.'")
            if published.contract not in CONTRACTS:
                raise ValueError(f"publishes.{index}.contract must be one of {known}")
        for index, contract in enumerate(self.receives):
            if contract not in CONTRACTS:
                raise ValueError(f"receives.{index} must be one of {known}")
        for index, service in enumerate(self.provides):
            if service not in SERVICES:
                raise ValueError(f"provides.{index} must be one of {sorted(SERVICES)}")
            if service in self.uses:
                raise ValueError(f"provides.{index}: a module does not ask itself")
            contract = ADDRESSED.get(service)
            if contract and contract not in {one.contract for one in self.publishes}:
                raise ValueError(f"provides.{index}: '{service}' needs publishing '{contract}'")
        return self

    @model_validator(mode="after")
    def _identifiers_are_unique(self) -> Self:
        for field, values in (
            ("connectors", [connector.id for connector in self.connectors]),
            ("tools", [tool.name for tool in self.tools]),
            ("ui.widgets", [widget.id for widget in self.ui.widgets]),
            ("consumes", list(self.consumes)),
            ("inlets", [inlet.id for inlet in self.inlets]),
            ("uses", list(self.uses)),
            ("publishes", [f"{one.type}:{one.contract}" for one in self.publishes]),
            ("receives", list(self.receives)),
            ("provides", list(self.provides)),
            ("notifications", [one.kind for one in self.notifications]),
        ):
            duplicated = sorted({value for value in values if values.count(value) > 1})
            if duplicated:
                raise ValueError(f"{field} has duplicate ids: {duplicated}")
        return self


class InvalidManifest(Exception):
    def __init__(self, path: Path, problems: list[str]) -> None:
        self.path = path
        self.problems = problems
        super().__init__(f"{path}: " + "; ".join(problems))


def _problems(error: ValidationError) -> list[str]:
    problems = []
    for detail in error.errors():
        location = ".".join(str(part) for part in detail["loc"]) or "<root>"
        problems.append(f"{location}: {detail['msg']}")
    return problems


def load_manifest(path: Path) -> Manifest:
    try:
        raw: Any = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise InvalidManifest(path, [f"<root>: invalid YAML: {error}"]) from error
    if not isinstance(raw, dict):
        raise InvalidManifest(path, ["<root>: the manifest must be a mapping"])

    try:
        manifest = Manifest.model_validate(raw)
    except ValidationError as error:
        raise InvalidManifest(path, _problems(error)) from error

    if manifest.id != path.parent.name:
        raise InvalidManifest(
            path, [f"id: '{manifest.id}' does not match the directory '{path.parent.name}'"]
        )
    return manifest


def load_all(root: Path) -> list[Manifest]:
    manifests = [load_manifest(path) for path in sorted(root.glob(MANIFEST_GLOB))]
    identifiers = [manifest.id for manifest in manifests]
    repeated = sorted({value for value in identifiers if identifiers.count(value) > 1})
    if repeated:
        raise InvalidManifest(root, [f"id: repeated across modules: {repeated}"])
    served = [
        service
        for manifest in manifests
        for service in manifest.provides
        if service not in ADDRESSED
    ]
    twice = sorted({value for value in served if served.count(value) > 1})
    if twice:
        raise InvalidManifest(root, [f"provides: served by more than one module: {twice}"])
    return manifests


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    root = Path(arguments[0] if arguments else "modules")

    try:
        manifests = load_all(root)
    except InvalidManifest as error:
        print(f"manifiesto inválido · {error}", file=sys.stderr)
        return 1

    for manifest in manifests:
        print(f"ok  {manifest.id} {manifest.version}  scopes={manifest.scopes or '[]'}")
    print(f"{len(manifests)} manifiesto(s) válido(s) en {root}/{MANIFEST_GLOB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
