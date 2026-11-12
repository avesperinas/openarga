from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_agenda import KEY, dated, uid
from shopping import guess, habits, names

MADRID = ZoneInfo("Europe/Madrid")
USUAL = 12


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def today() -> date:
    return datetime.now(MADRID).date()


class Category(BaseModel):
    id: str
    name: str
    emoji: str
    position: int


class Item(BaseModel):
    id: str
    product_id: str
    name: str
    category_id: str
    quantity: str | None
    note: str | None
    in_cart: bool
    source: str


class Group(BaseModel):
    category_id: str
    name: str
    emoji: str
    items: list[Item]


class Product(BaseModel):
    id: str
    name: str
    category_id: str
    quantity: str | None
    times: int
    last: date | None
    every_days: float | None
    every: str | None
    since: str | None
    due: bool
    on_list: bool


class ShoppingList(BaseModel):
    groups: list[Group]
    cart: list[Item]
    due: list[Product]
    usual: list[Product]
    pending: int
    in_cart: int
    space_id: str | None = None


class TripProduct(BaseModel):
    name: str
    category_id: str
    quantity: str | None


class Trip(BaseModel):
    id: str
    finished_at: datetime
    items: int
    products: list[TripProduct]


CATEGORIES = text(
    "select id, name, emoji, position from shopping.shopping_category order by position"
)

OPEN_ITEMS = text("""
    select i.id, i.product_id, p.name, p.category_id, i.quantity, i.note, i.status, i.source
    from shopping.shopping_item i
    join shopping.shopping_product p on p.id = i.product_id
    where i.status in ('pending', 'in_cart')
      and i.space_id is not distinct from cast(:space as uuid)
    order by coalesce(i.checked_at, i.added_at), lower(p.name)
""")

PRODUCTS = text("""
    select p.id, p.name, p.category_id, p.quantity,
           coalesce(
               array_agg((i.closed_at at time zone 'Europe/Madrid')::date)
                 filter (where i.id is not null),
               '{}'
           ) as days,
           exists (
               select 1 from shopping.shopping_item o
               where o.product_id = p.id and o.status in ('pending', 'in_cart')
           ) as on_list
    from shopping.shopping_product p
    left join shopping.shopping_item i on i.product_id = p.id and i.status = 'bought'
    where p.space_id is not distinct from cast(:space as uuid)
    group by p.id, p.name, p.category_id, p.quantity
""")


def _item(row: Any) -> Item:
    return Item(
        id=str(row.id),
        product_id=str(row.product_id),
        name=row.name,
        category_id=row.category_id,
        quantity=row.quantity,
        note=row.note,
        in_cart=row.status == "in_cart",
        source=row.source,
    )


async def categories(connection: AsyncConnection) -> list[Category]:
    rows = (await connection.execute(CATEGORIES)).all()
    return [Category(id=r.id, name=r.name, emoji=r.emoji, position=r.position) for r in rows]


def _space(space: UUID | None) -> str | None:
    return str(space) if space is not None else None


async def products(
    connection: AsyncConnection,
    query: str | None = None,
    on: date | None = None,
    space: UUID | None = None,
) -> list[Product]:
    day = on or today()
    out = []
    for row in (await connection.execute(PRODUCTS, {"space": _space(space)})).all():
        if query and not names.starts_a_word(query, row.name):
            continue
        found = habits.habit(list(row.days))
        out.append(
            Product(
                id=str(row.id),
                name=row.name,
                category_id=row.category_id,
                quantity=row.quantity,
                times=found.times,
                last=found.last,
                every_days=found.every_days,
                every=habits.every_label(found.every_days),
                since=habits.since_label(found.since(day)),
                due=found.due(day),
                on_list=row.on_list,
            )
        )
    return sorted(out, key=lambda one: (-one.times, names.fold(one.name)))


async def read(
    connection: AsyncConnection, on: date | None = None, space: UUID | None = None
) -> ShoppingList:
    day = on or today()
    rows = (await connection.execute(OPEN_ITEMS, {"space": _space(space)})).all()
    items = [_item(row) for row in rows]
    pending = [one for one in items if not one.in_cart]
    groups = []
    for category in await categories(connection):
        inside = sorted(
            (one for one in pending if one.category_id == category.id),
            key=lambda one: names.fold(one.name),
        )
        if inside:
            groups.append(
                Group(
                    category_id=category.id, name=category.name, emoji=category.emoji, items=inside
                )
            )

    known = [one for one in await products(connection, on=day, space=space) if not one.on_list]
    due = sorted(
        (one for one in known if one.due),
        key=lambda one: -habits.Habit(one.times, one.last, one.every_days).overdue(day),
    )
    return ShoppingList(
        groups=groups,
        cart=[one for one in items if one.in_cart],
        due=due,
        usual=[one for one in known if one.times >= 2 and not one.due][:USUAL],
        pending=len(pending),
        in_cart=len(items) - len(pending),
        space_id=_space(space),
    )


CATEGORY_IDS = (
    "produce",
    "bakery",
    "meat",
    "fish",
    "deli",
    "dairy",
    "pantry",
    "breakfast",
    "frozen",
    "drinks",
    "cleaning",
    "hygiene",
    "other",
)


class Entry(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    quantity: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=120)
    category_id: str | None = Field(default=None, max_length=20)


class Added(BaseModel):
    item_id: str
    product_id: str
    name: str
    category_id: str
    new_product: bool
    already_on_list: bool
    guessed: bool


PRODUCT_BY_KEY = text("""
    select id, name, category_id, quantity from shopping.shopping_product
    where key = :key and space_id is not distinct from cast(:space as uuid)
""")

INSERT_PRODUCT = text("""
    insert into shopping.shopping_product (name, key, category_id, space_id)
    values (:name, :key, :category, cast(:space as uuid))
    on conflict ((coalesce(space_id, user_id)), key) do nothing
    returning id
""")

LEARN_CATEGORY = text("""
    update shopping.shopping_product set category_id = :category where id = cast(:id as uuid)
""")

REMEMBER_QUANTITY = text("""
    update shopping.shopping_product set quantity = :quantity where id = cast(:id as uuid)
""")

UPSERT_ITEM = text("""
    insert into shopping.shopping_item (id, product_id, quantity, note, source, space_id)
    values (
        coalesce(cast(:id as uuid), gen_random_uuid()), cast(:product as uuid),
        coalesce(:quantity, :remembered), :note, :source, cast(:space as uuid)
    )
    on conflict (product_id) where status in ('pending', 'in_cart')
    do update set quantity = coalesce(:quantity, shopping.shopping_item.quantity),
                  note = coalesce(:note, shopping.shopping_item.note)
    returning id, (xmax = 0) as inserted
""")

ITEM_BY_ID = text("""
    select i.id, p.id as product_id, p.name, p.category_id
    from shopping.shopping_item i join shopping.shopping_product p on p.id = i.product_id
    where i.id = cast(:id as uuid)
""")

CATEGORY_EXISTS = text("select 1 from shopping.shopping_category where id = :id")


def _text(value: str | None) -> str | None:
    return (value or "").strip() or None


async def _check_category(connection: AsyncConnection, category_id: str) -> None:
    if (await connection.execute(CATEGORY_EXISTS, {"id": category_id})).first() is None:
        raise NotFound(f"la sección '{category_id}'")


async def _product(
    connection: AsyncConnection, entry: Entry, space: UUID | None
) -> tuple[Any, bool, bool]:
    key = names.key(entry.name)
    if not key:
        raise Conflict("un producto necesita un nombre")
    if entry.category_id is not None:
        await _check_category(connection, entry.category_id)

    found = (await connection.execute(PRODUCT_BY_KEY, {"key": key, "space": _space(space)})).first()
    if found is not None:
        if entry.category_id and entry.category_id != found.category_id:
            await connection.execute(
                LEARN_CATEGORY, {"id": str(found.id), "category": entry.category_id}
            )
        return (
            (await connection.execute(PRODUCT_BY_KEY, {"key": key, "space": _space(space)})).one(),
            False,
            False,
        )

    category = entry.category_id or guess.category(entry.name)
    await connection.execute(
        INSERT_PRODUCT,
        {
            "name": names.clean(entry.name),
            "key": key,
            "category": category,
            "space": _space(space),
        },
    )
    row = (await connection.execute(PRODUCT_BY_KEY, {"key": key, "space": _space(space)})).one()
    return row, True, entry.category_id is None


async def add(
    connection: AsyncConnection,
    entries: list[Entry],
    source: str = "app",
    space: UUID | None = None,
) -> list[Added]:
    out = []
    for entry in entries:
        if entry.id is not None:
            seen = (await connection.execute(ITEM_BY_ID, {"id": str(entry.id)})).first()
            if seen is not None:
                out.append(
                    Added(
                        item_id=str(seen.id),
                        product_id=str(seen.product_id),
                        name=seen.name,
                        category_id=seen.category_id,
                        new_product=False,
                        already_on_list=True,
                        guessed=False,
                    )
                )
                continue
        product, new, guessed = await _product(connection, entry, space)
        quantity = _text(entry.quantity)
        row = (
            await connection.execute(
                UPSERT_ITEM,
                {
                    "id": str(entry.id) if entry.id else None,
                    "product": str(product.id),
                    "quantity": quantity,
                    "remembered": product.quantity,
                    "note": _text(entry.note),
                    "source": source,
                    "space": _space(space),
                },
            )
        ).one()
        if quantity:
            await connection.execute(
                REMEMBER_QUANTITY, {"id": str(product.id), "quantity": quantity}
            )
        out.append(
            Added(
                item_id=str(row.id),
                product_id=str(product.id),
                name=product.name,
                category_id=product.category_id,
                new_product=new,
                already_on_list=not row.inserted,
                guessed=guessed,
            )
        )
    return out


SET_CART = text("""
    update shopping.shopping_item
       set status = case when :in_cart then 'in_cart' else 'pending' end,
           checked_at = case when :in_cart then now() end
     where id = cast(:id as uuid) and status in ('pending', 'in_cart')
     returning product_id
""")

UPDATE_ITEM = text("""
    update shopping.shopping_item set quantity = :quantity, note = :note
     where id = cast(:id as uuid) and status in ('pending', 'in_cart')
     returning product_id
""")

DROP_ITEM = text("""
    update shopping.shopping_item set status = 'dropped', closed_at = now(), checked_at = null
     where id = cast(:id as uuid) and status in ('pending', 'in_cart')
     returning product_id
""")


class CartIn(BaseModel):
    in_cart: bool


class ItemIn(BaseModel):
    quantity: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=120)


async def set_cart(connection: AsyncConnection, item_id: str, request: CartIn) -> None:
    params = {"id": item_id, "in_cart": request.in_cart}
    if (await connection.execute(SET_CART, params)).first() is None:
        raise NotFound(f"el artículo {item_id} en la lista")


async def update_item(connection: AsyncConnection, item_id: str, request: ItemIn) -> None:
    quantity = _text(request.quantity)
    params = {"id": item_id, "quantity": quantity, "note": _text(request.note)}
    row = (await connection.execute(UPDATE_ITEM, params)).first()
    if row is None:
        raise NotFound(f"el artículo {item_id} en la lista")
    if quantity:
        await connection.execute(
            REMEMBER_QUANTITY, {"id": str(row.product_id), "quantity": quantity}
        )


ITEM_EXISTS = text("select 1 from shopping.shopping_item where id = cast(:id as uuid)")


async def drop(connection: AsyncConnection, item_id: str) -> None:
    dropped = (await connection.execute(DROP_ITEM, {"id": item_id})).first()
    if dropped is None and (await connection.execute(ITEM_EXISTS, {"id": item_id})).first() is None:
        raise NotFound(f"el artículo {item_id} en la lista")


class CategoryIn(BaseModel):
    category_id: str = Field(min_length=2, max_length=20)


PRODUCT_BY_ID = text("""
    select id from shopping.shopping_product where id = cast(:id as uuid)
""")


async def set_category(connection: AsyncConnection, product_id: str, request: CategoryIn) -> None:
    await _check_category(connection, request.category_id)
    if (await connection.execute(PRODUCT_BY_ID, {"id": product_id})).first() is None:
        raise NotFound(f"el producto {product_id}")
    await connection.execute(LEARN_CATEGORY, {"id": product_id, "category": request.category_id})


IN_CART = text("""
    select i.id, p.name, p.category_id, i.quantity
    from shopping.shopping_item i
    join shopping.shopping_product p on p.id = i.product_id
    where i.status = 'in_cart' and i.space_id is not distinct from cast(:space as uuid)
    order by i.checked_at
    for update of i
""")

INSERT_TRIP = text("""
    insert into shopping.shopping_trip (id, items, space_id)
    values (coalesce(cast(:id as uuid), gen_random_uuid()), :items, cast(:space as uuid))
    returning id, finished_at
""")

TRIP_BY_ID = text("""
    select t.id, t.finished_at, t.items from shopping.shopping_trip t where t.id = cast(:id as uuid)
""")

TRIP_PRODUCTS = text("""
    select p.name, p.category_id, i.quantity
    from shopping.shopping_item i join shopping.shopping_product p on p.id = i.product_id
    where i.trip_id = cast(:id as uuid)
    order by i.checked_at
""")

CLOSE_CART = text("""
    update shopping.shopping_item
       set status = 'bought', trip_id = cast(:trip as uuid), closed_at = :at
     where status = 'in_cart' and space_id is not distinct from cast(:space as uuid)
""")

ENQUEUE = text("""
    insert into shopping.shopping_outbox (type, payload, dedup_hash)
    values (:type, cast(:payload as jsonb), :dedup)
    on conflict do nothing
""")


async def finish(
    connection: AsyncConnection, space: UUID | None = None, trip_id: UUID | None = None
) -> Trip:
    if trip_id is not None:
        done = (await connection.execute(TRIP_BY_ID, {"id": str(trip_id)})).first()
        if done is not None:
            rows = (await connection.execute(TRIP_PRODUCTS, {"id": str(trip_id)})).all()
            return Trip(
                id=str(done.id),
                finished_at=done.finished_at,
                items=done.items,
                products=[
                    TripProduct(name=row.name, category_id=row.category_id, quantity=row.quantity)
                    for row in rows
                ],
            )
    cart = (await connection.execute(IN_CART, {"space": _space(space)})).all()
    if not cart:
        raise Conflict("no hay nada en el carro: marca lo que hayas cogido")
    trip = (
        await connection.execute(
            INSERT_TRIP,
            {"id": str(trip_id) if trip_id else None, "items": len(cart), "space": _space(space)},
        )
    ).one()
    await connection.execute(
        CLOSE_CART, {"trip": str(trip.id), "at": trip.finished_at, "space": _space(space)}
    )
    bought = [
        TripProduct(name=row.name, category_id=row.category_id, quantity=row.quantity)
        for row in cart
    ]
    await connection.execute(
        ENQUEUE,
        {
            "type": "shopping.trip_finished",
            "payload": json.dumps(
                {
                    "trip_id": str(trip.id),
                    "finished_at": trip.finished_at.isoformat(),
                    "items": len(bought),
                    "products": [one.model_dump() for one in bought],
                }
            ),
            "dedup": f"trip:{trip.id}",
        },
    )
    await publish_trip(connection, str(trip.id), trip.finished_at, len(bought))
    return Trip(id=str(trip.id), finished_at=trip.finished_at, items=len(bought), products=bought)


async def publish_trip(
    connection: AsyncConnection, trip_id: str, finished_at: datetime, items: int
) -> None:
    await connection.execute(
        ENQUEUE,
        {
            "type": "shopping.trip",
            "payload": json.dumps(
                {
                    KEY: dated(
                        uid=uid("shopping", "trip", trip_id),
                        title=f"Compra de {items} producto{'' if items == 1 else 's'}",
                        start=finished_at.astimezone(MADRID),
                        end=finished_at.astimezone(MADRID),
                        tz="Europe/Madrid",
                        href="/shopping/historial",
                    ),
                    "trip_id": trip_id,
                    "items": items,
                }
            ),
            "dedup": f"trip:{trip_id}:agenda",
        },
    )


MY_TRIPS = text("""
    select id::text as id, finished_at, items from shopping.shopping_trip
    where user_id = nullif(current_setting('arga.user_id', true), '')::uuid
""")


async def backfill(connection: AsyncConnection) -> int:
    rows = (await connection.execute(MY_TRIPS)).all()
    for row in rows:
        await publish_trip(connection, row.id, row.finished_at, row.items)
    return len(rows)


TRIPS = text("""
    select t.id, t.finished_at, t.items,
           json_agg(
               json_build_object(
                   'name', p.name, 'category_id', p.category_id, 'quantity', i.quantity
               )
               order by c.position, lower(p.name)
           ) as products
    from shopping.shopping_trip t
    join shopping.shopping_item i on i.trip_id = t.id
    join shopping.shopping_product p on p.id = i.product_id
    join shopping.shopping_category c on c.id = p.category_id
    where t.space_id is not distinct from cast(:space as uuid)
    group by t.id, t.finished_at, t.items
    order by t.finished_at desc
    limit :limit
""")


async def trips(
    connection: AsyncConnection, limit: int = 20, space: UUID | None = None
) -> list[Trip]:
    rows = (await connection.execute(TRIPS, {"limit": limit, "space": _space(space)})).all()
    return [
        Trip(
            id=str(row.id),
            finished_at=row.finished_at,
            items=row.items,
            products=[TripProduct(**one) for one in row.products],
        )
        for row in rows
    ]
