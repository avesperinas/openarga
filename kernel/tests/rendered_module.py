from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "modules" / "_template"


def render(root: Path, module_id: str, name: str | None = None) -> Path:
    target = root / module_id
    if target.exists():
        shutil.rmtree(target)
    (target / "schema").mkdir(parents=True)

    def rendered(text: str) -> str:
        return text.replace("__MODULE_ID__", module_id).replace(
            "__MODULE_NAME__", name or module_id.title()
        )

    (target / "manifest.yaml").write_text(
        rendered((TEMPLATE / "manifest.yaml").read_text(encoding="utf-8")), encoding="utf-8"
    )
    for sql in sorted((TEMPLATE / "schema").glob("*.sql")):
        (target / "schema" / sql.name).write_text(
            rendered(sql.read_text(encoding="utf-8")), encoding="utf-8"
        )
    return target
