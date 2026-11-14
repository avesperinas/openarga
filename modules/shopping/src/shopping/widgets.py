from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from shopping import lists, shopping
from shopping.catalog import t

KINDS = {"list": "tasks", "due": "list"}

ROWS = 14


async def shopping_list(connection: AsyncConnection) -> dict:
    found = await shopping.read(connection, space=await lists.chosen(connection))
    pending = [one for group in found.groups for one in group.items]
    if not pending and not found.cart:
        return envelope(KINDS["list"], "empty", {"detail": t("list.empty")})
    items = [_item(one, done=False) for one in pending] + [
        _item(one, done=True) for one in found.cart
    ]
    return envelope(
        KINDS["list"],
        "ready",
        {"tasks": items[:ROWS], "count": len(pending), "checkable": True},
    )


def _item(one: shopping.Item, *, done: bool) -> dict:
    item: dict = {"id": one.id, "title": one.name}
    if one.quantity:
        item["detail"] = one.quantity
    if done:
        item["done"] = True
    return item


async def act(connection: AsyncConnection, verb: str, item_id: str) -> None:
    if verb == "add":
        space = await lists.chosen(connection)
        await shopping.add(connection, [shopping.Entry(name=item_id[:80])], space=space)
        return
    await shopping.set_cart(connection, item_id, shopping.CartIn(in_cart=verb == "complete"))


async def due(connection: AsyncConnection) -> dict:
    space = await lists.chosen(connection)
    found = await shopping.read(connection, space=space)
    if not found.due:
        known = any(
            one.every_days is not None for one in await shopping.products(connection, space=space)
        )
        detail = t("due.empty") if known else t("due.unknown")
        return envelope(KINDS["due"], "empty", {"detail": detail})
    return envelope(
        KINDS["due"],
        "ready",
        {"rows": [{"label": one.name, "value": one.since or ""} for one in found.due[:ROWS]]},
    )


RENDERERS = {"list": shopping_list, "due": due}
