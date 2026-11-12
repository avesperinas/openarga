import { useResource } from "@openarga/app";
import {
  Button,
  ChoiceChips,
  GroupLabel,
  Hint,
  List,
  ListRow,
  Notice,
  SearchField,
  Sheet,
  Stepper,
  TextField,
} from "@openarga/ui";
import { useEffect, useMemo, useState } from "react";

import {
  type Candidate,
  type Day,
  type Entry,
  type Found,
  type ItemIn,
  type MealKey,
  type PantryFood,
  type RecipeRef,
  type Unit,
  type UsualItem,
  logEntry,
  logTemplate,
  readUsualOf,
  search,
} from "./api";
import { amount, mealOfTime, measureCount, nowTime, quantityLabel, todayIso, withThis } from "./words";

type Per = { kcal: number; protein: number | null } | null;

export interface Choice {
  key: string;
  name: string;
  units: { value: Unit; label: string; per: Per }[];
  unit: Unit;
  quantity: number;
  measures: { name: string; grams: number }[];
  make: (quantity: number, unit: Unit, portion?: string) => ItemIn;
}

export interface Picked {
  key: string;
  name: string;
  label: string;
  item: ItemIn;
  kcal: number | null;
  protein: number | null;
}

const STEP: Record<Unit, number> = { g: 10, ml: 25, unit: 1, serving: 0.5, kcal: 50 };
const UNIT_LABEL: Record<Unit, string> = { g: "g", ml: "ml", unit: "ud", serving: "rac.", kcal: "kcal" };

function per100(food: { nutrients: Record<string, number> }, grams: number): Per {
  if (food.nutrients.kcal === undefined) return null;
  return { kcal: (food.nutrients.kcal * grams) / 100, protein: food.nutrients.protein === undefined ? null : (food.nutrients.protein * grams) / 100 };
}

export function foodChoice(food: PantryFood): Choice {
  if (food.nutrients_per === "unit") {
    const one: Per = { kcal: food.nutrients.kcal ?? 0, protein: food.nutrients.protein ?? null };
    return {
      key: `food:${food.id}`,
      name: food.label,
      units: [{ value: "unit", label: food.unit_name ?? "unidad", per: one }],
      unit: "unit",
      quantity: 1,
      measures: [],
      make: (quantity) => ({ kind: "food", food_id: food.id, quantity, unit: "unit" }),
    };
  }
  const units: Choice["units"] = [
    { value: "g", label: "g", per: per100(food, 1) },
    { value: "ml", label: "ml", per: per100(food, food.density_g_ml ?? 1) },
  ];
  if (food.grams_per_unit) units.push({ value: "unit", label: "ud", per: per100(food, food.grams_per_unit) });
  const measures = Object.entries(food.portions ?? {})
    .filter(([, grams]) => grams > 0)
    .map(([name, grams]) => ({ name, grams }))
    .sort((a, b) => a.grams - b.grams);
  return {
    key: `food:${food.id}`,
    name: food.label,
    units,
    unit: "g",
    quantity: measures[0]?.grams ?? 100,
    measures,
    make: (quantity, unit, portion) =>
      portion
        ? { kind: "food", food_id: food.id, quantity, unit: "unit", portion }
        : { kind: "food", food_id: food.id, quantity, unit },
  };
}

export function recipeChoice(recipe: RecipeRef): Choice {
  return {
    key: `recipe:${recipe.id}`,
    name: recipe.name,
    units: [
      { value: "serving", label: "rac.", per: null },
      { value: "g", label: "g", per: null },
    ],
    unit: "serving",
    quantity: 1,
    measures: [],
    make: (quantity, unit) => ({ kind: "recipe", recipe_id: recipe.id, quantity, unit: unit === "g" ? "g" : "serving" }),
  };
}

export function outsideChoice(candidate: Candidate): Choice {
  return {
    key: `outside:${candidate.source}:${candidate.source_ref}`,
    name: candidate.name,
    units: [
      { value: "g", label: "g", per: per100(candidate, 1) },
      { value: "ml", label: "ml", per: per100(candidate, 1) },
    ],
    unit: "g",
    quantity: 100,
    measures: [],
    make: (quantity, unit) => ({ kind: "food", source: candidate.source, source_ref: candidate.source_ref, quantity, unit }),
  };
}

export function usualChoice(one: UsualItem): Choice {
  const per: Per = one.kcal === null || one.quantity <= 0 ? null : { kcal: one.kcal / one.quantity, protein: null };
  const make = (quantity: number, unit: Unit): ItemIn => {
    if (one.kind === "recipe") return { kind: "recipe", recipe_id: one.recipe_id ?? "", quantity, unit };
    if (one.kind === "quick") return { kind: "quick", name: one.name, quantity, unit: "kcal" };
    if (one.kind === "water") return { kind: "water", quantity, unit: "ml" };
    return {
      kind: "food",
      food_id: one.food_id ?? "",
      quantity,
      unit,
      ...(one.portion && unit === "unit" ? { portion: one.portion } : {}),
    };
  };
  return {
    key: one.kind === "food" ? `food:${one.food_id}` : one.kind === "recipe" ? `recipe:${one.recipe_id}` : `${one.kind}:${one.name}`,
    name: one.name,
    units: [{ value: one.unit, label: one.portion && one.unit === "unit" ? one.portion : UNIT_LABEL[one.unit], per }],
    unit: one.unit,
    quantity: one.quantity,
    measures: [],
    make,
  };
}

export const WATER: Choice = {
  key: "water",
  name: "Agua",
  units: [{ value: "ml", label: "ml", per: { kcal: 0, protein: 0 } }],
  unit: "ml",
  quantity: 250,
  measures: [{ name: "vaso", grams: 250 }, { name: "botella", grams: 500 }],
  make: (quantity) => ({ kind: "water", quantity, unit: "ml" }),
};

export function preview(choice: Choice, quantity: number, unit: Unit): Per {
  const per = choice.units.find((one) => one.value === unit)?.per ?? null;
  if (!per) return null;
  return { kcal: per.kcal * quantity, protein: per.protein === null ? null : per.protein * quantity };
}

export function picked(choice: Choice, quantity: number, unit: Unit, portion?: string): Picked {
  const item = choice.make(quantity, unit, portion);
  const sum = portion
    ? preview(choice, quantity * (choice.measures.find((one) => one.name === portion)?.grams ?? 0), "g")
    : preview(choice, quantity, unit);
  const label = portion
    ? measureCount(quantity, portion)
    : quantityLabel({ quantity, unit: item.unit, estimated: false });
  return { key: `${choice.key}:${Date.now()}`, name: choice.name, label, item, kcal: sum?.kcal ?? null, protein: sum?.protein ?? null };
}

export function byUse(foods: PantryFood[], uses: Map<string, number>): PantryFood[] {
  return [...foods].sort((a, b) => (uses.get(b.id) ?? 0) - (uses.get(a.id) ?? 0));
}

type Step = "list" | "amount" | "quick";

export function AddSheet({
  day,
  meal: initialMeal,
  today: dayData,
  onClose,
  onSaved,
}: {
  day: string;
  meal?: MealKey;
  today?: Day;
  onClose: () => void;
  onSaved: (entry: Entry, what: string) => void;
}) {
  const meals = dayData?.meals ?? [];
  const startMeal = initialMeal ?? meals.find((one) => one.current)?.meal ?? mealOfTime(nowTime());
  const usualAt = (key: MealKey) => {
    const found = meals.find((one) => one.meal === key);
    if (found?.current && day === todayIso()) return nowTime();
    return found?.usual_at ?? nowTime();
  };
  const [meal, setMeal] = useState<MealKey>(startMeal);
  const [time, setTime] = useState(() => usualAt(startMeal));
  const [timeTouched, setTimeTouched] = useState(false);
  const [step, setStep] = useState<Step>("list");
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Found | null>(null);
  const [outside, setOutside] = useState(false);
  const [busy, setBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [basket, setBasket] = useState<Picked[]>([]);
  const [dishName, setDishName] = useState("");
  const [choice, setChoice] = useState<Choice | null>(null);
  const [quantity, setQuantity] = useState<number | null>(null);
  const [unit, setUnit] = useState<Unit>("g");
  const [portion, setPortion] = useState<string | null>(null);
  const [quickName, setQuickName] = useState("");
  const [quickKcal, setQuickKcal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const usual = useResource(`usual:${day}:${meal}`, () => readUsualOf(meal, day)).data;
  const uses = useMemo(() => {
    const counted = new Map<string, number>();
    for (const one of [...(usual?.items ?? []), ...(usual?.recent ?? [])]) {
      if (one.food_id) counted.set(one.food_id, one.times);
    }
    return counted;
  }, [usual]);
  const label = meals.find((one) => one.meal === meal)?.label ?? "la comida";

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setFound(null);
      setOutside(false);
      return;
    }
    setBusy(true);
    const timer = window.setTimeout(() => {
      search(text, outside)
        .then((next) => {
          setFound(next);
          setSearchError(null);
        })
        .catch((reason: unknown) => setSearchError(reason instanceof Error ? reason.message : "No se ha podido buscar"))
        .finally(() => setBusy(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, outside]);

  const choose = (next: Choice) => {
    setChoice(next);
    setQuantity(next.quantity);
    setUnit(next.unit);
    setPortion(null);
    setStep("amount");
  };
  const add = (next: Picked) => setBasket((current) => [...current, next]);
  const addChoice = () => {
    if (!choice || !quantity) return;
    add(portion ? picked(choice, quantity, "unit", portion) : picked(choice, quantity, unit));
    setChoice(null);
    setQuery("");
    setStep("list");
  };
  const addQuick = () => {
    if (!quickName.trim() || !quickKcal) return;
    add({
      key: `quick:${Date.now()}`,
      name: quickName.trim(),
      label: `≈ ${amount(quickKcal, 0)} kcal`,
      item: { kind: "quick", name: quickName.trim(), quantity: quickKcal, unit: "kcal" },
      kcal: quickKcal,
      protein: null,
    });
    setQuickName("");
    setQuickKcal(null);
    setStep("list");
  };

  const at = () => {
    if (timeTouched) return { eatenAt: `${day}T${time}`, meal: undefined };
    return { eatenAt: day === todayIso() ? undefined : `${day}T${time}`, meal };
  };
  const save = () => {
    if (basket.length === 0) return;
    setSaving(true);
    const when = at();
    const dish = basket.length > 1 ? dishName.trim() : "";
    logEntry(
      basket.map((one) => (dish ? { ...one.item, dish } : one.item)),
      when.eatenAt,
      when.meal,
    )
      .then((entry) => onSaved(entry, dish || basket.map((one) => one.name).join(" + ")))
      .catch((reason: unknown) => {
        setSaving(false);
        setError(reason instanceof Error ? reason.message : "No se ha podido apuntar");
      });
  };
  const logMenu = (id: string, name: string) => {
    const when = at();
    void logTemplate(id, when.meal, when.eatenAt)
      .then((entry) => onSaved(entry, name))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "No se ha podido apuntar"));
  };

  const kcalNow = dayData?.nutrients.kcal ?? 0;
  const proteinNow = dayData?.nutrients.protein ?? 0;
  const amountPreview = choice && quantity ? (portion ? preview(choice, quantity * (choice.measures.find((one) => one.name === portion)?.grams ?? 0), "g") : preview(choice, quantity, unit)) : null;
  const basketKcal = basket.reduce((total, one) => total + (one.kcal ?? 0), 0) + (step === "amount" ? amountPreview?.kcal ?? 0 : 0);
  const basketProtein = basket.reduce((total, one) => total + (one.protein ?? 0), 0) + (step === "amount" ? amountPreview?.protein ?? 0 : 0);
  const kcalGoal = dayData?.target?.kcal ?? null;
  const proteinGoal = dayData?.target?.protein ?? null;
  const foot = withThis(kcalNow + basketKcal, proteinNow + basketProtein, { kcal: kcalGoal, protein: proteinGoal });

  const action =
    step === "amount"
      ? { label: "Añadir a la cesta", onClick: addChoice, disabled: !quantity }
      : step === "quick"
        ? { label: "Añadir a la cesta", onClick: addQuick, disabled: !quickName.trim() || !quickKcal }
        : {
            label: saving ? "Apuntando…" : basket.length ? `Apuntar ${basket.length === 1 ? "1 cosa" : `${basket.length} cosas`}` : "Apuntar",
            onClick: save,
            disabled: basket.length === 0 || saving,
          };

  const usualRow = (one: UsualItem, note: string) => (
    <ListRow
      key={`${note}:${one.item_id}`}
      title={one.name}
      subtitle={`${one.portion && one.unit === "unit" ? measureCount(one.quantity, one.portion) : quantityLabel({ quantity: one.quantity, unit: one.unit, estimated: false })}, ${note}`}
      value={one.kcal === null ? undefined : `${amount(one.kcal, 0)} kcal`}
      onClick={() => choose(usualChoice(one))}
      action={{ icon: "plus", label: `Añadir ${one.name} a la cesta`, onClick: () => add(picked(usualChoice(one), one.quantity, one.unit)) }}
    />
  );

  return (
    <Sheet
      title={step === "list" ? `Añadir a ${label.toLowerCase()}` : step === "quick" ? "A ojo" : (choice?.name ?? "")}
      onClose={onClose}
      back={step === "list" ? undefined : () => setStep("list")}
      action={action}
      foot={foot}
    >
      {error && <Notice tone="warning">{error}</Notice>}

      {step === "list" && (
        <>
          <div className="macros-when">
            <ChoiceChips<MealKey>
              label="Comida"
              value={meal}
              onChange={(next) => {
                setMeal(next);
                setTime(usualAt(next));
                setTimeTouched(false);
              }}
              options={(meals.length ? meals : []).map((one) => ({ value: one.meal, label: one.label }))}
            />
            <TextField
              label="Hora"
              type="time"
              value={time}
              onChange={(next) => {
                setTime(next);
                setTimeTouched(true);
                if (/^\d\d:\d\d$/.test(next)) setMeal(mealOfTime(next));
              }}
            />
          </div>

          {basket.length > 0 && (
            <section aria-label="La cesta">
              <GroupLabel>La cesta</GroupLabel>
              <List>
                {basket.map((one) => (
                  <ListRow
                    key={one.key}
                    title={one.name}
                    subtitle={one.label}
                    value={one.kcal === null ? undefined : `${amount(one.kcal, 0)} kcal`}
                    action={{
                      icon: "close",
                      label: `Quitar ${one.name}`,
                      onClick: () => setBasket((current) => current.filter((other) => other.key !== one.key)),
                    }}
                  />
                ))}
              </List>
              {basket.length > 1 && (
                <TextField
                  label="Nombre del plato"
                  value={dishName}
                  onChange={setDishName}
                  placeholder="Ensalada de pasta con atún"
                  hint="Si es un plato, ponle nombre: se verá como una sola fila."
                />
              )}
            </section>
          )}

          <SearchField label="Buscar qué apuntar" value={query} onChange={setQuery} placeholder="yogur, café, lentejas…" busy={busy} />
          {searchError && <Notice tone="warning">{searchError}</Notice>}

          {query.trim().length >= 2 ? (
            <>
              {found && (
                <List>
                  {byUse(found.foods, uses).map((food) => (
                    <ListRow
                      key={food.id}
                      title={food.label}
                      subtitle={uses.get(food.id) ? `Despensa · ${uses.get(food.id)} veces` : "Despensa"}
                      value={`${amount(food.nutrients.kcal ?? 0, 0)} kcal/${food.nutrients_per === "unit" ? (food.unit_name ?? "ud") : "100 g"}`}
                      onClick={() => choose(foodChoice(food))}
                    />
                  ))}
                  {found.recipes.map((recipe) => (
                    <ListRow key={recipe.id} title={recipe.name} subtitle={`Receta · ${recipe.servings} raciones`} onClick={() => choose(recipeChoice(recipe))} />
                  ))}
                  {found.candidates.map((candidate) => (
                    <ListRow
                      key={`${candidate.source}:${candidate.source_ref}`}
                      title={candidate.name}
                      subtitle={[candidate.source === "usda" ? "USDA" : "Open Food Facts", candidate.brand].filter(Boolean).join(" · ")}
                      value={`${amount(candidate.nutrients.kcal ?? 0, 0)} kcal/100 g`}
                      onClick={() => choose(outsideChoice(candidate))}
                    />
                  ))}
                </List>
              )}
              {found?.failed.map((one) => (
                <Hint key={one.source}>{one.reason}</Hint>
              ))}
              {found && !outside && found.foods.length + found.recipes.length === 0 && <Hint>No está en tu despensa.</Hint>}
              {!outside && (
                <Button variant="tinted" icon="search" onClick={() => setOutside(true)}>
                  Buscar fuera de tu despensa
                </Button>
              )}
              {outside && found && found.candidates.length === 0 && <Hint>Tampoco fuera. Apúntalo a ojo.</Hint>}
            </>
          ) : (
            <>
              <GroupLabel>Para {label.toLowerCase()}</GroupLabel>
              <List>
                {usual?.yesterday.map((one) => usualRow(one, "ayer"))}
                {usual?.items
                  .filter((one) => !usual.yesterday.some((other) => other.name === one.name))
                  .map((one) => usualRow(one, one.times > 1 ? `${one.times} veces` : "la última vez"))}
                {usual?.recent.map((one) => usualRow(one, "la última vez"))}
                {usual?.menus.map((menu) => (
                  <ListRow
                    key={menu.id}
                    title={menu.name}
                    subtitle={`Menú · ${menu.items.length} ${menu.items.length === 1 ? "cosa" : "cosas"}`}
                    accessory="plus"
                    onClick={() => logMenu(menu.id, menu.name)}
                  />
                ))}
                <ListRow title="Agua" subtitle="Un vaso, una botella" icon="cup" hue={6} onClick={() => choose(WATER)} />
                <ListRow title="A ojo" subtitle="Unas kcal, sin buscar" icon="edit" hue={4} onClick={() => setStep("quick")} />
              </List>
            </>
          )}
        </>
      )}

      {step === "amount" && choice && (
        <>
          <Stepper
            label="Cantidad"
            value={quantity}
            step={portion ? 1 : STEP[unit]}
            min={0}
            unit={portion ?? choice.units.find((one) => one.value === unit)?.label ?? unit}
            onChange={setQuantity}
          />
          {(choice.units.length > 1 || choice.measures.length > 0) && (
            <ChoiceChips
              label="Medida"
              value={portion ? `portion:${portion}` : unit}
              onChange={(next) => {
                if (next.startsWith("portion:")) {
                  setPortion(next.slice("portion:".length));
                  setQuantity(1);
                } else {
                  setPortion(null);
                  setUnit(next as Unit);
                  setQuantity(choice.units.find((one) => one.value === next)?.value === "unit" ? 1 : choice.quantity);
                }
              }}
              options={[
                ...choice.units.map((one) => ({ value: one.value as string, label: one.label })),
                ...choice.measures.map((one) => ({ value: `portion:${one.name}`, label: `${one.name} · ${amount(one.grams, 0)} g` })),
              ]}
            />
          )}
          {amountPreview ? (
            <Hint>
              {amount(amountPreview.kcal, 0)} kcal
              {amountPreview.protein !== null && ` · ${amount(amountPreview.protein)} g de proteína`}
            </Hint>
          ) : (
            <Hint>Lo que suma sale de la despensa al apuntarlo.</Hint>
          )}
        </>
      )}

      {step === "quick" && (
        <>
          <TextField label="Qué era" value={quickName} onChange={setQuickName} placeholder="Un pintxo de tortilla" autoFocus />
          <Stepper label="Kcal, a ojo" value={quickKcal} step={50} min={0} unit="kcal" inputMode="numeric" onChange={setQuickKcal} />
          <Hint>Lo apuntado a ojo solo lleva sus kcal: sus micros quedan sin dato.</Hint>
        </>
      )}
    </Sheet>
  );
}
