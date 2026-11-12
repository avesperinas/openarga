from __future__ import annotations

import argparse
import sys
from pathlib import Path

from arga_module import demo

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill OpenArga with the demo people.")
    parser.add_argument("--list", action="store_true", help="only list who and which apps")
    arguments = parser.parse_args()
    cast = demo.load(ROOT / "demo" / "personas.yaml")
    seeds = demo.seeds(ROOT / "modules")
    print(f"people: {', '.join(person.name for person in cast.people)}")
    print(f"apps with demo data: {', '.join(seeds) or 'none yet'}")
    if arguments.list:
        return 0
    print("seeding is not wired yet (task P10)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
