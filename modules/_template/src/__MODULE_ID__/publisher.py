from __future__ import annotations

from arga_module.db import engine
from arga_module.publisher import Publisher

MODULE = "__MODULE_ID__"

PUBLISHER = Publisher(MODULE, engine)


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
