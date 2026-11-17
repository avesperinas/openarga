from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from arga_tenancy import current_spaces
from recipes import recipes
from recipes.recipes import IngredientIn, RecipeIn, StepIn

EXISTS = text("select id::text from recipes.recipes_recipe where name = :name limit 1")


def _g(name: str, grams: float, **fields) -> IngredientIn:
    return IngredientIn(name=name, quantity=grams, unit="g", **fields)


def _u(name: str, units: float) -> IngredientIn:
    return IngredientIn(name=name, quantity=units, unit="unit")


LENTILS = RecipeIn(
    name="Lentil stew",
    servings=4,
    tags=["weekday", "batch cooking"],
    ingredients=[
        _g("Brown lentils", 300),
        _g("Carrot", 150),
        _g("Onion", 120),
        _g("Potato", 300),
        IngredientIn(name="Olive oil", quantity=2, unit="tbsp"),
        IngredientIn(name="Sweet paprika", quantity=1, unit="tsp"),
    ],
    steps=[
        StepIn(action="chop", text="Chop the onion, carrot and potato", minutes=10,
               equipment="board", ingredients=[2, 3, 4]),
        StepIn(action="saute", text="Soften the onion and carrot in the oil", minutes=8,
               equipment="hob", after=[1], ingredients=[2, 3, 5]),
        StepIn(action="simmer", text="Add the lentils, potato, paprika and water", minutes=35,
               attended=False, equipment="hob", after=[2], ingredients=[1, 4, 6]),
        StepIn(action="serve", text="Rest five minutes and serve", minutes=5, after=[3]),
    ],
)  # fmt: skip

OVERNIGHT_OATS = RecipeIn(
    name="Overnight oats",
    servings=1,
    tags=["breakfast"],
    ingredients=[
        _g("Rolled oats", 50),
        IngredientIn(name="Milk", quantity=150, unit="ml"),
        _g("Plain yogurt", 80),
        _u("Banana", 1),
    ],
    steps=[
        StepIn(action="mix", text="Mix the oats, milk and yogurt", minutes=3, equipment="bowl",
               ingredients=[1, 2, 3]),
        StepIn(action="chill", text="Leave in the fridge overnight", minutes=480,
               attended=False, equipment="fridge", after=[1]),
        StepIn(action="serve", text="Top with sliced banana", minutes=2, after=[2],
               ingredients=[4]),
    ],
)  # fmt: skip

SALMON = RecipeIn(
    name="Baked salmon with vegetables",
    servings=2,
    tags=["weekday"],
    ingredients=[
        _g("Salmon fillet", 300),
        _g("Courgette", 200),
        _g("Red pepper", 150),
        IngredientIn(name="Olive oil", quantity=1, unit="tbsp"),
        _u("Lemon", 0.5),
    ],
    steps=[
        StepIn(action="chop", text="Cut the courgette and pepper", minutes=8, equipment="board",
               ingredients=[2, 3]),
        StepIn(action="roast", text="Roast the vegetables with the oil", minutes=15,
               attended=False, equipment="oven", after=[1], ingredients=[4]),
        StepIn(action="bake", text="Add the salmon and bake", minutes=12, attended=False,
               equipment="oven", after=[2], ingredients=[1]),
        StepIn(action="serve", text="Squeeze the lemon over it", minutes=2, after=[3],
               ingredients=[5]),
    ],
)  # fmt: skip

OMELETTE = RecipeIn(
    name="Potato omelette",
    servings=4,
    tags=["weekend"],
    ingredients=[_u("Egg", 6), _g("Potato", 600), _g("Onion", 150), _g("Olive oil", 100)],
    steps=[
        StepIn(action="peel", text="Peel and slice the potatoes and onion", minutes=12,
               equipment="board", ingredients=[2, 3]),
        StepIn(action="fry", text="Fry them slowly in the oil", minutes=25, equipment="hob",
               after=[1], ingredients=[4]),
        StepIn(action="mix", text="Mix with the beaten eggs", minutes=5, equipment="bowl",
               after=[2], ingredients=[1]),
        StepIn(action="fry", text="Set the omelette on both sides", minutes=8, equipment="hob",
               after=[3]),
    ],
)  # fmt: skip

HUMMUS = RecipeIn(
    name="Hummus",
    servings=6,
    tags=["snack"],
    ingredients=[
        _g("Cooked chickpeas", 400),
        _g("Tahini", 60),
        _u("Lemon", 1),
        IngredientIn(name="Olive oil", quantity=3, unit="tbsp"),
        IngredientIn(name="Ground cumin", quantity=1, unit="tsp"),
    ],
    steps=[
        StepIn(action="blend", text="Blend everything with a splash of water", minutes=5,
               ingredients=[1, 2, 3, 4, 5]),
        StepIn(action="chill", text="Chill before serving", minutes=30, attended=False,
               equipment="fridge", after=[1]),
    ],
)  # fmt: skip

PASTA = RecipeIn(
    name="Tomato pasta",
    servings=2,
    tags=["weekday"],
    ingredients=[_g("Spaghetti", 200), _g("Crushed tomato", 400), _u("Garlic clove", 2),
                 _g("Grated cheese", 30)],
    steps=[
        StepIn(action="boil", text="Cook the pasta", minutes=10, attended=False, equipment="hob",
               ingredients=[1]),
        StepIn(action="simmer", text="Simmer the tomato with the garlic", minutes=12,
               equipment="hob", ingredients=[2, 3]),
        StepIn(action="serve", text="Toss together and add the cheese", minutes=3,
               after=[1, 2], ingredients=[4]),
    ],
)  # fmt: skip

MINE = {"alex": (LENTILS, SALMON, OVERNIGHT_OATS, PASTA), "sam": (OMELETTE, HUMMUS, PASTA)}
SHARED = {"alex": (LENTILS,), "sam": (OMELETTE,)}


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    space = next(iter(current_spaces.get()), None)
    for recipe in MINE.get(persona.key, ()):
        found = await connection.scalar(EXISTS, {"name": recipe.name})
        recipe_id = found or await recipes.create(connection, recipe)
        if space is not None and recipe in SHARED.get(persona.key, ()):
            await recipes.share(connection, recipe_id, str(space))
