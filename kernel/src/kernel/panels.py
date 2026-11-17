from collections.abc import Iterable

# Until every manifest declares ui.panels; a module that declares them is never read from here.
UNDECLARED: dict[str, tuple[str, ...]] = {
    "planner": ("day",),
    "goals": ("day",),
    "money": ("money",),
    "vitals": ("health",),
    "training": ("health",),
    "macros": ("health",),
    "study": ("work",),
    "shopping": ("home",),
    "recipes": ("home",),
    "travel": ("leisure",),
    "outings": ("leisure",),
    "library": ("leisure",),
    "notebook": ("mind",),
    "insights": ("mind",),
}


def panels_of(module_id: str, declared: Iterable[str] | None) -> list[str]:
    if declared is not None:
        return list(declared)
    return list(UNDECLARED.get(module_id, ()))
