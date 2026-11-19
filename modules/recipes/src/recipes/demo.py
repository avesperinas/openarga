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


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    space = next(iter(current_spaces.get()), None)
    chosen = [recipe for group in PERSONAL[persona.key] for recipe in (EVERYONE[n] for n in group)]
    seen = set()
    for recipe in (*MINE.get(persona.key, ()), *chosen):
        if recipe.name in seen:
            continue
        seen.add(recipe.name)
        found = await connection.scalar(EXISTS, {"name": recipe.name})
        recipe_id = found or await recipes.create(connection, recipe)
        if space is not None and recipe in SHARED.get(persona.key, ()):
            await recipes.share(connection, recipe_id, str(space))
