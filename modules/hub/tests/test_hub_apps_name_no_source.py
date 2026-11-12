from __future__ import annotations

import re
from pathlib import Path

import yaml

from hub import catalogue

ROOT = Path(__file__).resolve().parents[3] / "modules"
SUFFIXES = {".py", ".ts", ".tsx", ".sql", ".toml"}

KNOWN: set[tuple[str, str]] = set()


def inlet_contracts(module: Path) -> set[str]:
    manifest = yaml.safe_load((module / "manifest.yaml").read_text())
    return {contract for inlet in manifest.get("inlets") or [] for contract in inlet["contracts"]}


def code_of(module: Path):
    for folder in (module / "src", module / "ui" / "src", module / "schema"):
        for path in sorted(folder.rglob("*")) if folder.exists() else []:
            if path.suffix not in SUFFIXES or "node_modules" in path.parts:
                continue
            if path.name.startswith("test_") or ".test." in path.name:
                continue
            yield path


def test_no_app_names_a_source_that_reaches_it_through_its_inlets() -> None:
    found: set[tuple[str, str]] = set()
    for module in sorted(ROOT.iterdir()):
        if module.name == "hub" or not (module / "manifest.yaml").exists():
            continue
        contracts = inlet_contracts(module)
        feeding = [one.id for one in catalogue.PROVIDERS if contracts & set(one.emits)]
        if not feeding:
            continue
        alternatives = "|".join(map(re.escape, feeding))
        named = re.compile(rf"""["'`]({alternatives})["'`]""")
        for path in code_of(module):
            for hit in named.finditer(path.read_text(errors="ignore")):
                found.add((str(path.relative_to(ROOT)), hit.group(1)))
    new = sorted(found - KNOWN)
    assert not new, f"una app nombra una fuente que le llega por su toma: {new}"


def test_the_known_leftovers_are_still_there() -> None:
    for relative, provider in sorted(KNOWN):
        path = ROOT / relative
        assert path.exists(), f"{relative} ya no existe: quítalo de KNOWN"
        text = path.read_text()
        assert re.search(rf"""["'`]{provider}["'`]""", text), f"{relative} ya no nombra {provider}"
