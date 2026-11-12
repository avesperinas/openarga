from __future__ import annotations

import compileall
import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest
import yaml

from kernel.manifests import InvalidManifest, load_all

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "modules" / "_template"
GENERATOR = ROOT / "scripts" / "new-module.sh"
MODULE = "probe"


@pytest.fixture
def generated(tmp_path: Path) -> Path:
    target = tmp_path / MODULE
    for source in TEMPLATE.rglob("*"):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        relative = str(source.relative_to(TEMPLATE)).replace("__MODULE_ID__", MODULE)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            source.read_bytes()
            .replace(b"__MODULE_ID__", MODULE.encode())
            .replace(b"__MODULE_NAME__", MODULE.title().encode())
        )
    return tmp_path


def test_the_generator_substitutes_both_placeholders() -> None:
    script = GENERATOR.read_text(encoding="utf-8")

    assert "__MODULE_ID__" in script and "__MODULE_NAME__" in script


def test_what_comes_out_is_a_manifest_the_kernel_accepts(generated: Path) -> None:
    manifests = load_all(generated)

    assert [manifest.id for manifest in manifests] == [MODULE]
    manifest = manifests[0]
    assert manifest.database.db_schema == MODULE
    assert manifest.database.role == f"mod_{MODULE}"
    assert manifest.api.prefix == f"/api/{MODULE}"


def test_nothing_is_left_with_a_placeholder(generated: Path) -> None:
    left = [
        path.relative_to(generated)
        for path in generated.rglob("*")
        if path.is_file() and b"__MODULE_" in path.read_bytes()
    ]

    assert left == []


def test_its_python_compiles(generated: Path) -> None:
    with redirect_stdout(io.StringIO()):
        ok = compileall.compile_dir(str(generated), quiet=2, force=True)

    assert ok, "la plantilla genera Python que no compila"


def test_it_brings_its_schema_and_its_first_file_is_the_init(generated: Path) -> None:
    files = sorted(path.name for path in (generated / MODULE / "schema").glob("*.sql"))

    assert files[0] == "0001_init.sql"
    assert all((generated / MODULE / "schema" / name).read_text().strip() for name in files)


def test_it_teaches_that_the_role_decides_the_permission(generated: Path) -> None:
    tools = (generated / MODULE / "src" / MODULE / "tools.py").read_text(encoding="utf-8")

    assert "def role_for_scopes" in tools


def test_it_brings_no_connector(generated: Path) -> None:
    manifest = yaml.safe_load((generated / MODULE / "manifest.yaml").read_text(encoding="utf-8"))

    assert "connectors" not in manifest
    assert not (generated / MODULE / "connectors").exists()
    assert not (generated / MODULE / "src" / MODULE / "connectors").exists()


def test_a_broken_manifest_is_rejected_and_not_quietly_ignored(generated: Path) -> None:
    path = generated / MODULE / "manifest.yaml"
    path.write_text(path.read_text().replace(f"role: mod_{MODULE}", "role: mod_otro"))

    with pytest.raises(InvalidManifest):
        load_all(generated)
