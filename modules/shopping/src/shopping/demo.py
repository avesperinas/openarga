from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from arga_tenancy import current_spaces
from shopping import names

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-0000005b0b00")
WEEKS = 78

SETTING = text("""
    insert into shopping.shopping_setting (list_space_id) values (:space)
    on conflict (user_id) do nothing
""")

PRODUCT = text("""
    insert into shopping.shopping_product
        (id, name, key, category_id, quantity, space_id, created_at)
    values (:id, :name, :key, :category_id, :quantity, :space_id, :created_at)
    on conflict do nothing
""")

TRIP = text("""
    insert into shopping.shopping_trip (id, finished_at, items, space_id)
    values (:id, :finished_at, :items, :space_id)
    on conflict do nothing
""")

ITEM = text("""
    insert into shopping.shopping_item
        (id, product_id, quantity, status, added_at, checked_at, closed_at, trip_id, space_id)
    values (:id, :product_id, :quantity, :status, :added_at, :checked_at, :closed_at, :trip_id,
            :space_id)
    on conflict do nothing
""")

PRODUCTS = (
    ("Milk", "dairy", "2 l"),
    ("Eggs", "dairy", "12"),
    ("Bread", "bakery", None),
    ("Tomatoes", "produce", "1 kg"),
    ("Bananas", "produce", None),
    ("Apples", "produce", "1 kg"),
    ("Chicken breast", "meat", None),
    ("Salmon", "fish", None),
    ("Cheese", "deli", None),
    ("Rice", "pantry", "1 kg"),
    ("Pasta", "pantry", None),
    ("Olive oil", "pantry", "1 l"),
    ("Coffee", "breakfast", None),
    ("Yogurt", "dairy", "4"),
    ("Frozen peas", "frozen", None),
    ("Sparkling water", "drinks", "6"),
    ("Washing-up liquid", "cleaning", None),
    ("Toothpaste", "hygiene", None),
    ("Onions", "produce", "1 kg"),
    ("Potatoes", "produce", "2 kg"),
    ("Carrots", "produce", "1 kg"),
    ("Lemons", "produce", None),
    ("Spinach", "produce", "200 g"),
    ("Baguette", "bakery", None),
    ("Minced beef", "meat", "500 g"),
    ("Chorizo", "deli", None),
    ("Mozzarella", "deli", None),
    ("Butter", "dairy", None),
    ("Orange juice", "drinks", "1 l"),
    ("Beer", "drinks", "6"),
    ("Red wine", "drinks", None),
    ("Cereal", "breakfast", None),
    ("Dark chocolate", "breakfast", None),
    ("Ice cream", "frozen", None),
    ("Chickpeas", "pantry", "2 jars"),
    ("Tuna cans", "pantry", "3"),
    ("Toilet paper", "hygiene", "12"),
    ("Shampoo", "hygiene", None),
    ("Dishwasher tablets", "cleaning", None),
    ("Hake", "fish", None),
)
WEEKLY = (0, 2, 3, 4, 13)
PENDING = (0, 2, 5, 9, 16, 18, 22, 24, 27, 34, 36, 39)
IN_CART = (1, 13, 28)


def _id(key: str) -> UUID:
    return uuid5(NAMESPACE, key)


def _product(scope: str, index: int) -> UUID:
    return _id(f"{scope}:product-{names.key(PRODUCTS[index][0])}")


async def _products(connection: AsyncConnection, scope: str, space: UUID | None, today: date):
    for index, (name, category, quantity) in enumerate(PRODUCTS):
        await connection.execute(
            PRODUCT,
            {
                "id": _product(scope, index),
                "name": name,
                "key": names.key(name),
                "category_id": category,
                "quantity": quantity,
                "space_id": space,
                "created_at": datetime.combine(
                    today - timedelta(weeks=WEEKS + 1), time(10), ZoneInfo("UTC")
                ),
            },
        )


def _bought(week: int) -> list[int]:
    extra = [(week * 5 + n * 7) % len(PRODUCTS) for n in range(3)]
    return sorted(set(WEEKLY) | set(extra))


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    zone = ZoneInfo(persona.timezone)
    space = next(iter(current_spaces.get()), None)
    scope = str(space) if space is not None else str(persona.id)
    await connection.execute(SETTING, {"space": space})
    await _products(connection, scope, space, today)
    mine = 0 if persona.key == "alex" else 1
    for week in range(1, WEEKS + 1):
        if space is not None and week % 2 != mine:
            continue
        day = today - timedelta(days=week * 7 - 1 - mine)
        finished = datetime.combine(day, time(11 if mine else 19, 30), zone)
        bought = _bought(week)
        trip = _id(f"{scope}:trip-{week}")
        await connection.execute(
            TRIP, {"id": trip, "finished_at": finished, "items": len(bought), "space_id": space}
        )
        for index in bought:
            await connection.execute(
                ITEM,
                {
                    "id": _id(f"{scope}:item-{week}-{index}"),
                    "product_id": _product(scope, index),
                    "quantity": PRODUCTS[index][2],
                    "status": "bought",
                    "added_at": finished - timedelta(days=3),
                    "checked_at": finished - timedelta(minutes=20),
                    "closed_at": finished,
                    "trip_id": trip,
                    "space_id": space,
                },
            )
    if persona.key != "alex" and space is not None:
        return
    now = datetime.combine(today, time(9), zone)
    for index in PENDING:
        await connection.execute(
            ITEM,
            {
                "id": _id(f"{scope}:pending-{index}"),
                "product_id": _product(scope, index),
                "quantity": PRODUCTS[index][2],
                "status": "pending",
                "added_at": now - timedelta(days=index % 3),
                "checked_at": None,
                "closed_at": None,
                "trip_id": None,
                "space_id": space,
            },
        )
    for index in IN_CART:
        await connection.execute(
            ITEM,
            {
                "id": _id(f"{scope}:cart-{index}"),
                "product_id": _product(scope, index),
                "quantity": PRODUCTS[index][2],
                "status": "in_cart",
                "added_at": now - timedelta(days=1),
                "checked_at": now,
                "closed_at": None,
                "trip_id": None,
                "space_id": space,
            },
        )
