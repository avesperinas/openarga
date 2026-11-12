from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

CONTRACT_DIRS = [
    "kernel",
    "gateway",
    "mcp",
    "auth",
    "shell",
    "packages/ui",
    "modules",
    "docs/adr",
    "docs/platform",
    "scripts",
]

CONTRACT_DOCS = [
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "ROADMAP.md",
    "TASKS.md",
    "LICENSE",
    "docs/platform/architecture.md",
    "docs/platform/module-contract.md",
    "docs/platform/design-system.md",
    "docs/platform/ai.md",
]


@pytest.mark.parametrize("relpath", CONTRACT_DIRS)
def test_contract_directory_exists(relpath: str) -> None:
    assert (ROOT / relpath).is_dir()


@pytest.mark.parametrize("relpath", CONTRACT_DOCS)
def test_contract_document_exists(relpath: str) -> None:
    assert (ROOT / relpath).is_file()


def test_adrs_are_numbered_and_unique() -> None:
    numbers = sorted(p.name[:4] for p in (ROOT / "docs/adr").glob("*.md"))
    assert numbers, "no ADRs"
    assert len(numbers) == len(set(numbers)), f"repeated ADR numbers: {numbers}"
    assert all(n.isdigit() for n in numbers), f"ADR without a number: {numbers}"


def test_module_template_is_not_a_module() -> None:
    manifest = (ROOT / "modules/_template/manifest.yaml").read_text()
    assert "__MODULE_ID__" in manifest
