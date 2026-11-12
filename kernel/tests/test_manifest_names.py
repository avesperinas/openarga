from pathlib import Path

import pytest
import yaml

from kernel.manifests import LOCALES, Manifest

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = sorted((ROOT / "modules").glob("[a-z]*/manifest.yaml"))


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.parent.name)
def test_every_app_has_its_name_and_summary_in_every_language(path: Path) -> None:
    manifest = Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    assert set(manifest.names) == set(LOCALES)
    assert set(manifest.summary) == set(LOCALES)


def test_names_must_start_in_english() -> None:
    with pytest.raises(ValueError, match="'en'"):
        Manifest.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "names": {"es": "Sonda"},
                "version": "0.1.0",
                "database": {"schema": "probe", "role": "mod_probe"},
                "api": {"prefix": "/api/probe"},
                "ui": {"view": "/probe"},
            }
        )
