from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "spanish_baseline.txt"

ALLOWED = (
    "*/i18n/es.json",
    "modules/outings/areas/*.yaml",
    "modules/hub/src/hub/catalogs/*.toml",
    "kernel/src/kernel/catalogs/*.toml",
    "packages/recurrence/phrases.json",
    "packages/ui/src/app-names.ts",
    "packages/ui/geo/*",
    "tests/test_no_spanish.py",
    "tests/spanish_baseline.txt",
    "LICENSE",
    "NOTICE",
    "uv.lock",
    "pnpm-lock.yaml",
)
BINARY = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".pmtiles", ".woff", ".woff2", ".ttf", ".pbf"}

MARKS = re.compile(r"[ñÑ¿¡áéíóúÁÉÍÓÚ]")
WORDS = re.compile(
    r"\b(que|los|las|para|una|del|pero|porque|cuando|también|está|esta|este|hay|sus|"
    r"nada|ningún|ninguna|aquí|ahora|desde|hasta|entre|sobre|tiene|puede)\b"
)
MANIFEST_LOCALE_LINE = re.compile(r"^\s+es: ")


def tracked() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [name for name in listed.split("\0") if name]


def allowed(name: str) -> bool:
    return Path(name).suffix in BINARY or any(fnmatch.fnmatch(name, glob) for glob in ALLOWED)


def spanish(name: str) -> bool:
    if (ROOT / name).is_symlink():
        return False
    try:
        text = (ROOT / name).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    if name.endswith("manifest.yaml"):
        text = "\n".join(line for line in text.splitlines() if not MANIFEST_LOCALE_LINE.match(line))
    if MARKS.search(text):
        return True
    return len(WORDS.findall(text)) >= 3


def offenders() -> set[str]:
    return {name for name in tracked() if not allowed(name) and spanish(name)}


def baseline() -> set[str]:
    lines = BASELINE.read_text(encoding="utf-8").splitlines() if BASELINE.exists() else []
    return {line.strip() for line in lines if line.strip()}


def test_no_new_spanish_outside_the_ui_catalogs() -> None:
    new = sorted(offenders() - baseline())
    assert not new, (
        "Spanish outside the UI catalogs (AGENTS.md, Language). Move UI text to i18n/es.json and "
        f"write everything else in English: {new}"
    )


def test_the_baseline_only_lists_files_that_still_need_work() -> None:
    done = sorted(baseline() - offenders())
    assert not done, f"these files no longer have Spanish: remove them from {BASELINE.name}: {done}"


LITERAL = re.compile(r"""\"([^\"\n]{1,60})\"|'([^'\n]{1,60})'|>([^<>{}\n]{1,60})<""")
UI_WORDS = frozenset(
    "hoy ayer mañana otros otras resto editar cerrar buscar guardar cancelar añadir borrar eliminar "
    "mostrar ocultar nuevo nueva cargando semana año gasto gastos ingreso ingresos tabla leer escuchar "
    "hecha hecho todos todas ninguno ninguna más sí volver siguiente anterior aceptar enviar abrir "
    "copiar pegar deshacer rehacer ajustes inicio ayuda salir entrar continuar listo vacío "
    "desconocido varios resumen detalle grafo evento eventos capa capas contratos compartido apuntado".split()
)
UI_PHRASES = re.compile(r"^(sin|ver|por|no hay|de|desde|para|con) [a-záéíóúñ]+", re.IGNORECASE)
LITERAL_SKIP = ("/i18n/", "/tests/", "/stories/", "/demo", "/areas/", "/geo/", "/catalogs/")
LITERAL_ALLOWED = {
    ("kernel/src/kernel/desktop.py", "hoy"),
    ("modules/notebook/ui/src/routes.ts", "buscar"),
    ("modules/study/ui/src/NoteEditor.tsx", "nuevo"),
    ("modules/insights/src/insights/picks.py", "Todos tus libros"),
}


def spanish_literals(name: str) -> list[str]:
    path = Path(name)
    if path.suffix not in {".ts", ".tsx", ".py"} or ".test." in name or "app-names" in name:
        return []
    if name.startswith("tests/") or any(skip in f"/{name}" for skip in LITERAL_SKIP):
        return []
    if (ROOT / name).is_symlink():
        return []
    try:
        text = (ROOT / name).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    found = []
    for match in LITERAL.finditer(text):
        literal = next(group for group in match.groups() if group is not None).strip()
        words = re.findall(r"[a-záéíóúñ]+", literal.lower())
        if not words or re.search(r"[=:{}_/#.\-]", literal) or (name, literal) in LITERAL_ALLOWED:
            continue
        if words[0] in UI_WORDS or UI_PHRASES.match(literal):
            found.append(literal)
    return found


def test_no_spanish_words_in_ui_strings_of_components() -> None:
    hits = {name: found for name in tracked() if (found := spanish_literals(name))}
    assert not hits, (
        "Spanish text fixed in code. Put it in the i18n catalogs and read it with t() or say(): "
        f"{hits}"
    )
