import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVICES = {
    "kernel": ROOT / "kernel",
    "gateway": ROOT / "gateway",
}


def declared(path: Path, table: list[str]) -> set[str]:
    data = tomllib.loads(path.read_text())
    for key in table:
        data = data[key]
    return {
        requirement.split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip().lower()
        for requirement in data
    }


def runtime_dependencies(service: str) -> set[str]:
    return declared(SERVICES[service] / "pyproject.toml", ["project", "dependencies"])


def development_dependencies() -> set[str]:
    return declared(ROOT / "pyproject.toml", ["dependency-groups", "dev"])


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def distributions_for(module: str) -> set[str]:
    return {name.lower() for name in packages_distributions().get(module, [])}


def source_files() -> list[tuple[str, Path]]:
    files = [
        (service, path)
        for service, root in SERVICES.items()
        for path in sorted((root / "src" / service).rglob("*.py"))
    ]
    assert files, "no hay fuentes de servicio que comprobar"
    return files


@pytest.mark.parametrize(
    ("service", "path"), source_files(), ids=lambda value: getattr(value, "name", value)
)
def test_a_service_only_imports_what_ships_with_it(service: str, path: Path) -> None:
    runtime = runtime_dependencies(service)
    development = development_dependencies()

    offenders = {}
    for module in imported_modules(path):
        if module in sys.stdlib_module_names or module in SERVICES:
            continue
        distributions = distributions_for(module)
        if distributions and not distributions & runtime and distributions & development:
            offenders[module] = sorted(distributions)

    assert not offenders, (
        f"{path.relative_to(ROOT)} importa {offenders}, que solo está en el grupo `dev`. "
        f"En la imagen no existe: el comando falla al ejecutarse, no al construirse. "
        f"O se declara en {service}/pyproject.toml, o no se usa desde {service}/src."
    )
