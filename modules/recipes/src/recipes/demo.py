from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona, localized, localizer
from arga_tenancy import CURRENT_USER_SQL, current_spaces
from recipes import foods, recipes
from recipes.recipes import IngredientIn, RecipeIn, StepIn

say = localizer(Path(__file__).parent / "seed" / "i18n")

EXISTS = text("select id::text from recipes.recipes_recipe where name = :name limit 1")
FOOD_EXISTS = text("select 1 from recipes.recipes_food where lower(name) = lower(:name) limit 1")
FOODS_TO_SPACE = text(
    f"update recipes.recipes_food set space_id = cast(:space as uuid) "
    f"where space_id is null and user_id = {CURRENT_USER_SQL}"
)

PANTRY = (
    ('Arborio rice', 'grain', 350, 6.7, 0.6, 79, 1.0, None, None),
    ('Aubergine', 'vegetable', 25, 1.0, 0.2, 5.9, 3.0, 250, None),
    ('Avocado', 'fruit', 160, 2.0, 14.7, 8.5, 6.7, 170, None),
    ('Banana', 'fruit', 89, 1.1, 0.3, 23, 2.6, 120, None),
    ('Basmati rice', 'grain', 350, 7.5, 0.6, 78, 1.3, None, None),
    ('Beef', 'protein', 190, 20, 12, 0, 0, None, None),
    ('Black olives', 'vegetable', 115, 0.8, 10.7, 6.3, 3.2, None, None),
    ('Bread slice', 'grain', 265, 9, 3.2, 49, 2.7, 30, None),
    ('Broccoli', 'vegetable', 34, 2.8, 0.4, 6.6, 2.6, None, None),
    ('Brown lentils', 'legume', 353, 25, 1.1, 60, 10.7, None, None),
    ('Butter', 'fat', 717, 0.9, 81, 0.1, 0, None, None),
    ('Carrot', 'vegetable', 41, 0.9, 0.2, 9.6, 2.8, 80, None),
    ('Cherry tomato', 'vegetable', 18, 0.9, 0.2, 3.9, 1.2, None, None),
    ('Chicken breast', 'protein', 120, 22.5, 2.6, 0, 0, None, None),
    ('Chicken thigh', 'protein', 177, 18, 11, 0, 0, 110, None),
    ('Chorizo', 'protein', 455, 24, 38, 1.9, 0, None, None),
    ('Coconut milk', 'liquid', 197, 2.0, 21, 2.8, 0, None, None),
    ('Cod', 'fish', 82, 18, 0.7, 0, 0, None, None),
    ('Cooked chickpeas', 'legume', 164, 8.9, 2.6, 27, 7.6, None, None),
    ('Corn tortilla', 'grain', 218, 5.7, 2.9, 44, 6.3, 30, None),
    ('Courgette', 'vegetable', 17, 1.2, 0.3, 3.1, 1.0, 200, None),
    ('Cream', 'dairy', 340, 2.1, 36, 2.8, 0, None, None),
    ('Crushed tomato', 'vegetable', 32, 1.6, 0.3, 7.3, 1.9, None, None),
    ('Cucumber', 'vegetable', 15, 0.7, 0.1, 3.6, 0.5, 300, None),
    ('Curry powder', 'spice', 325, 14, 14, 58, 53, None, None),
    ('Dark chocolate', 'sweet', 546, 5, 31, 61, 7, None, None),
    ('Egg', 'protein', 143, 12.6, 9.5, 0.7, 0, 60, None),
    ('Feta cheese', 'dairy', 264, 14, 21, 4.1, 0, None, None),
    ('Fish stock', 'liquid', 8, 1.0, 0.2, 0.5, 0, None, None),
    ('Flour', 'grain', 364, 10, 1.0, 76, 2.7, None, None),
    ('Garlic clove', 'vegetable', 149, 6.4, 0.5, 33, 2.1, 4, None),
    ('Gnocchi', 'grain', 133, 3.4, 0.4, 29, 1.6, None, None),
    ('Grated cheese', 'dairy', 402, 25, 33, 1.3, 0, None, None),
    ('Ground cumin', 'spice', 375, 18, 22, 44, 10, None, None),
    ('Hake', 'fish', 71, 16, 0.6, 0, 0, None, None),
    ('Lemon', 'fruit', 29, 1.1, 0.3, 9.3, 2.8, 90, None),
    ('Lime', 'fruit', 30, 0.7, 0.2, 10.5, 2.8, 70, None),
    ('Milk', 'dairy', 47, 3.4, 1.6, 4.8, 0, None, None),
    ('Mushrooms', 'vegetable', 22, 3.1, 0.3, 3.3, 1.0, None, None),
    ('Noodles', 'grain', 138, 4.5, 2.1, 25, 1.2, None, None),
    ('Olive oil', 'fat', 884, 0, 100, 0, 0, None, None),
    ('Onion', 'vegetable', 40, 1.1, 0.1, 9.3, 1.7, 110, None),
    ('Parmesan', 'dairy', 431, 38, 29, 4.1, 0, None, None),
    ('Parsley', 'vegetable', 36, 3.0, 0.8, 6.3, 3.3, 10, None),
    ('Peanut butter', 'fat', 588, 25, 50, 20, 6.0, None, None),
    ('Pesto', 'fat', 420, 5, 40, 6, 2, None, None),
    ('Plain yogurt', 'dairy', 61, 3.5, 3.3, 4.7, 0, None, None),
    ('Potato', 'vegetable', 77, 2.0, 0.1, 17, 2.2, None, None),
    ('Pumpkin', 'vegetable', 26, 1.0, 0.1, 6.5, 0.5, None, None),
    ('Red cabbage', 'vegetable', 31, 1.4, 0.2, 7.4, 2.1, None, None),
    ('Red onion', 'vegetable', 40, 1.1, 0.1, 9.3, 1.7, 110, None),
    ('Red pepper', 'vegetable', 31, 1.0, 0.3, 6.0, 2.1, 150, None),
    ('Red wine', 'liquid', 85, 0.1, 0, 2.6, 0, None, None),
    ('Rolled oats', 'grain', 379, 13, 6.5, 68, 10, None, None),
    ('Salmon fillet', 'fish', 208, 20, 13, 0, 0, None, None),
    ('Sesame oil', 'fat', 884, 0, 100, 0, 0, None, None),
    ('Sherry vinegar', 'liquid', 19, 0, 0, 0.9, 0, None, None),
    ('Soy sauce', 'liquid', 53, 8.1, 0.6, 4.9, 0.8, None, None),
    ('Spaghetti', 'grain', 371, 13, 1.5, 75, 3.2, None, None),
    ('Spinach', 'vegetable', 23, 2.9, 0.4, 3.6, 2.2, None, None),
    ('Sugar', 'sweet', 387, 0, 0, 100, 0, None, None),
    ('Sweet paprika', 'spice', 282, 14, 13, 54, 35, None, None),
    ('Tahini', 'fat', 595, 17, 54, 21, 9.3, None, None),
    ('Tofu', 'protein', 76, 8.1, 4.8, 1.9, 0.3, None, None),
    ('Tomato', 'vegetable', 18, 0.9, 0.2, 3.9, 1.2, 120, None),
    ('Tomato paste', 'vegetable', 82, 4.3, 0.5, 19, 4.1, None, None),
    ('Tuna can', 'fish', 116, 26, 1.0, 0, 0, 80, None),
    ('Vegetable stock', 'liquid', 6, 0.3, 0.1, 1.0, 0, None, None),
    ('Whey protein', 'supplement', 400, 80, 6, 8, 0, None, None),
)  # fmt: skip


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


def _parse(line: str) -> IngredientIn:
    amount, unit, name = line.split(" ", 2)
    return IngredientIn(name=name, quantity=float(amount), unit=unit)


def _step(line: str) -> StepIn:
    action, words, minutes, equipment, attended, after, using = line.split("|")
    return StepIn(
        action=action,
        text=words,
        minutes=int(minutes),
        equipment=equipment or "none",
        attended=attended != "no",
        after=[int(one) for one in after.split(",") if one],
        ingredients=[int(one) for one in using.split(",") if one],
    )


def _recipe(name: str, servings: int, tags: str, ingredients: str, steps: str) -> RecipeIn:
    return RecipeIn(
        name=name,
        servings=servings,
        tags=tags.split(","),
        ingredients=[_parse(one) for one in ingredients.split(";")],
        steps=[_step(one) for one in steps.split(";")],
    )


MORE = (
    _recipe(
        "Chicken curry",
        4,
        "weekday,batch cooking",
        "600 g Chicken breast;1 unit Onion;2 unit Garlic clove;400 ml Coconut milk;"
        "2 tbsp Curry powder;300 g Basmati rice",
        "chop|Dice the chicken and onion|10|board|yes||1,2,3;"
        "saute|Brown with garlic and curry powder|10|hob|yes|1|1,2,3,5;"
        "simmer|Pour in the coconut milk and simmer|20|hob|no|2|4;"
        "boil|Cook the rice|15|hob|no||6;serve|Serve over the rice|3||yes|3,4|",
    ),
    _recipe(
        "Greek salad",
        2,
        "lunch,vegetarian",
        "2 unit Tomato;1 unit Cucumber;100 g Feta cheese;50 g Black olives;"
        "1 tbsp Olive oil;0.5 unit Red onion",
        "chop|Chop the vegetables|8|board|yes||1,2,6;"
        "assemble|Add the feta, olives and oil|3|bowl|yes|1|3,4,5",
    ),
    _recipe(
        "Pancakes",
        4,
        "breakfast,weekend,vegetarian",
        "250 g Flour;2 unit Egg;300 ml Milk;1 tbsp Sugar;20 g Butter",
        "mix|Whisk everything into a batter|5|bowl|yes||1,2,3,4;"
        "rest|Let the batter rest|10||no|1|;"
        "fry|Cook the pancakes one by one|15|hob|yes|2|5",
    ),
    _recipe(
        "Mushroom risotto",
        3,
        "dinner,vegetarian",
        "250 g Arborio rice;300 g Mushrooms;1 unit Onion;800 ml Vegetable stock;"
        "40 g Parmesan;1 tbsp Olive oil",
        "chop|Slice mushrooms and chop the onion|8|board|yes||2,3;"
        "saute|Soften the onion and mushrooms|8|hob|yes|1|2,3,6;"
        "simmer|Add rice and stock a ladle at a time|25|hob|yes|2|1,4;"
        "serve|Stir in the parmesan|2||yes|3|5",
    ),
    _recipe(
        "Gazpacho",
        4,
        "summer,vegetarian,lunch",
        "1000 g Tomato;1 unit Cucumber;1 unit Red pepper;1 unit Garlic clove;"
        "3 tbsp Olive oil;1 tbsp Sherry vinegar",
        "chop|Roughly chop the vegetables|10|board|yes||1,2,3,4;"
        "blend|Blend with oil and vinegar|5||yes|1|5,6;"
        "chill|Chill until very cold|120|fridge|no|2|",
    ),
    _recipe(
        "Beef stew",
        6,
        "winter,batch cooking,weekend",
        "800 g Beef;3 unit Carrot;2 unit Onion;400 g Potato;250 ml Red wine;1 tbsp Tomato paste",
        "chop|Cut the beef and vegetables|15|board|yes||1,2,3,4;"
        "fry|Brown the beef in batches|15|hob|yes|1|1;"
        "simmer|Add wine, tomato and vegetables|90|hob|no|2|2,3,4,5,6",
    ),
    _recipe(
        "Veggie stir-fry",
        2,
        "weekday,vegetarian,quick",
        "200 g Tofu;1 unit Red pepper;150 g Broccoli;2 tbsp Soy sauce;1 tbsp Sesame oil;"
        "200 g Noodles",
        "chop|Cut the tofu and vegetables|8|board|yes||1,2,3;"
        "boil|Cook the noodles|5|hob|no||6;"
        "fry|Stir-fry everything with soy sauce|8|hob|yes|1,2|1,2,3,4,5",
    ),
    _recipe(
        "Banana bread",
        8,
        "baking,breakfast,vegetarian",
        "3 unit Banana;250 g Flour;100 g Sugar;2 unit Egg;80 g Butter",
        "mix|Mash the bananas and mix everything|10|bowl|yes||1,2,3,4,5;"
        "bake|Bake until golden|50|oven|no|1|",
    ),
    _recipe(
        "Fish tacos",
        3,
        "dinner,quick",
        "400 g Cod;6 unit Corn tortilla;1 unit Lime;100 g Red cabbage;1 tbsp Olive oil",
        "season|Season the cod with lime|5|bowl|yes||1,3;"
        "fry|Pan-fry the cod|8|hob|yes|1|1,5;"
        "assemble|Fill the tortillas with fish and cabbage|5||yes|2|2,4",
    ),
    _recipe(
        "Chickpea curry",
        4,
        "weekday,vegetarian,batch cooking",
        "400 g Cooked chickpeas;400 g Crushed tomato;1 unit Onion;2 tbsp Curry powder;"
        "200 g Spinach",
        "saute|Soften the onion with the spices|8|hob|yes||3,4;"
        "simmer|Add chickpeas and tomato|20|hob|no|1|1,2;"
        "mix|Stir in the spinach until it wilts|3|hob|yes|2|5",
    ),
    _recipe(
        "Shakshuka",
        2,
        "breakfast,weekend,vegetarian",
        "4 unit Egg;400 g Crushed tomato;1 unit Red pepper;1 unit Onion;1 tsp Ground cumin",
        "chop|Chop the pepper and onion|6|board|yes||3,4;"
        "simmer|Cook with tomato and cumin|15|hob|yes|1|1,3,4,5;"
        "fry|Poach the eggs in the sauce|8|hob|no|2|2",
    ),
    _recipe(
        "Lemon chicken traybake",
        4,
        "dinner,weekday",
        "8 unit Chicken thigh;600 g Potato;2 unit Lemon;1 tbsp Olive oil;2 unit Garlic clove",
        "chop|Cut the potatoes and lemons|10|board|yes||2,3,5;"
        "roast|Roast everything on one tray|50|oven|no|1|1,2,3,4,5",
    ),
    _recipe(
        "Tuna salad",
        2,
        "lunch,quick",
        "2 unit Tuna can;200 g Cooked chickpeas;1 unit Red onion;2 unit Tomato;1 tbsp Olive oil",
        "chop|Chop the onion and tomato|5|board|yes||3,4;"
        "mix|Toss with the tuna and chickpeas|3|bowl|yes|1|1,2,5",
    ),
    _recipe(
        "Pumpkin soup",
        4,
        "winter,vegetarian",
        "800 g Pumpkin;1 unit Onion;500 ml Vegetable stock;100 ml Cream",
        "chop|Cube the pumpkin and onion|10|board|yes||1,2;"
        "simmer|Cook in the stock until soft|25|hob|no|1|1,2,3;"
        "blend|Blend smooth and add the cream|5||yes|2|4",
    ),
    _recipe(
        "Oat cookies",
        12,
        "baking,snack,vegetarian",
        "200 g Rolled oats;100 g Butter;80 g Sugar;1 unit Egg;50 g Dark chocolate",
        "mix|Mix all the ingredients|8|bowl|yes||1,2,3,4,5;bake|Bake small mounds|14|oven|no|1|",
    ),
    _recipe(
        "Spanish lentils with chorizo",
        4,
        "winter,batch cooking",
        "300 g Brown lentils;120 g Chorizo;1 unit Onion;2 unit Carrot;1 tsp Sweet paprika",
        "chop|Chop everything|10|board|yes||2,3,4;"
        "saute|Fry the chorizo and onion|8|hob|yes|1|2,3;"
        "simmer|Cook with lentils and carrot|40|hob|no|2|1,4,5",
    ),
    _recipe(
        "Avocado toast",
        1,
        "breakfast,quick,vegetarian",
        "2 unit Bread slice;1 unit Avocado;1 unit Egg;1 unit Lemon",
        "toast|Toast the bread|3|hob|yes||1;"
        "fry|Fry the egg|4|hob|yes||3;"
        "assemble|Mash the avocado with lemon and top|3||yes|1,2|2,4",
    ),
    _recipe(
        "Hake in green sauce",
        2,
        "dinner,spanish",
        "400 g Hake;2 unit Garlic clove;1 unit Parsley;200 ml Fish stock;1 tbsp Olive oil",
        "saute|Fry the garlic in the oil|3|hob|yes||2,5;"
        "simmer|Add stock and parsley, then the hake|10|hob|no|1|1,3,4",
    ),
    _recipe(
        "Gnocchi with pesto",
        2,
        "quick,weekday,vegetarian",
        "400 g Gnocchi;60 g Pesto;50 g Cherry tomato",
        "boil|Cook the gnocchi until they float|4|hob|no||1;"
        "assemble|Toss with pesto and tomato|3||yes|1|2,3",
    ),
    _recipe(
        "Ratatouille",
        4,
        "summer,vegetarian,batch cooking",
        "2 unit Courgette;1 unit Aubergine;2 unit Tomato;1 unit Red pepper;1 unit Onion;"
        "2 tbsp Olive oil",
        "chop|Dice all the vegetables|15|board|yes||1,2,3,4,5;"
        "simmer|Stew slowly with the oil|40|hob|no|1|1,2,3,4,5,6",
    ),
    _recipe(
        "Protein smoothie",
        1,
        "breakfast,quick,snack",
        "250 ml Milk;1 unit Banana;30 g Whey protein;20 g Peanut butter",
        "blend|Blend everything|2||yes||1,2,3,4",
    ),
)

PERSONAL = {
    "alex": (
        ("Chicken curry", "Greek salad", "Beef stew", "Veggie stir-fry", "Fish tacos"),
        ("Tuna salad", "Lemon chicken traybake", "Protein smoothie", "Avocado toast"),
        ("Gnocchi with pesto", "Chickpea curry", "Gazpacho", "Mushroom risotto"),
    ),
    "sam": (
        ("Pancakes", "Banana bread", "Shakshuka", "Pumpkin soup", "Oat cookies"),
        ("Spanish lentils with chorizo", "Hake in green sauce", "Ratatouille", "Avocado toast"),
        ("Greek salad", "Chickpea curry", "Gazpacho", "Mushroom risotto"),
    ),
}
EVERYONE = {recipe.name: recipe for recipe in MORE}

MINE = {"alex": (LENTILS, SALMON, OVERNIGHT_OATS, PASTA), "sam": (OMELETTE, HUMMUS, PASTA)}
SHARED = {
    "alex": (LENTILS, EVERYONE["Chicken curry"], EVERYONE["Greek salad"]),
    "sam": (OMELETTE, EVERYONE["Pancakes"], EVERYONE["Shakshuka"]),
}


async def _pantry(connection: AsyncConnection, space) -> None:
    for name, category, kcal, protein, fat, carbs, fiber, grams, density in PANTRY:
        if await connection.scalar(FOOD_EXISTS, {"name": name}):
            continue
        await foods.create_manual(
            connection,
            foods.ManualIn(
                name=name,
                category_id=category,
                macros=foods.MacrosIn(
                    kcal=kcal, protein=protein, fat=fat, carbs=carbs, fiber=fiber
                ),
                grams_per_unit=grams,
                density_g_ml=density,
            ),
        )
    if space is not None:
        await connection.execute(FOODS_TO_SPACE, {"space": str(space)})


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    space = next(iter(current_spaces.get()), None)
    await _pantry(connection, space)
    chosen = [recipe for group in PERSONAL[persona.key] for recipe in (EVERYONE[n] for n in group)]
    seen = set()
    for original in (*MINE.get(persona.key, ()), *chosen):
        if original.name in seen:
            continue
        seen.add(original.name)
        recipe = localized(say, persona, original)
        found = await connection.scalar(EXISTS, {"name": original.name}) or await connection.scalar(
            EXISTS, {"name": recipe.name}
        )
        recipe_id = found or await recipes.create(connection, recipe)
        if space is not None and original in SHARED.get(persona.key, ()):
            await recipes.share(connection, recipe_id, str(space))
