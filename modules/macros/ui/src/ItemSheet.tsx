import {
  Button,
  ChoiceChips,
  ConfirmPanel,
  Hint,
  List,
  ListRow,
  Notice,
  SearchField,
  Sheet,
  Stepper,
  type Locale,
  type Translate,
  useLocale,
  useT,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import {
  type Candidate,
  type Entry,
  type Found,
  type Item,
  type Meal,
  type MealKey,
  type Measure,
  type PantryFood,
  type RecipeRef,
  changeItem,
  duplicateItem,
  itemIsSure,
  moveItem,
  readMeasures,
  removeItem,
  search,
  swapItem,
} from "./api";
import { amount, quantityLabel } from "./words";

const STEP: Record<Item["unit"], number> = { g: 10, ml: 25, unit: 1, serving: 0.5, kcal: 50 };

type Step = "main" | "food" | "confirm" | "delete";
type Replacement =
  | { kind: "food"; food: PantryFood }
  | { kind: "outside"; candidate: Candidate }
  | { kind: "recipe"; recipe: RecipeRef };

export function scaled(item: Pick<Item, "quantity" | "nutrients">, quantity: number) {
  const factor = item.quantity > 0 ? quantity / item.quantity : 0;
  return { kcal: (item.nutrients.kcal ?? 0) * factor, protein: (item.nutrients.protein ?? 0) * factor };
}

export function summaryOf(
  item: Pick<Item, "quantity" | "unit" | "estimated" | "kind" | "nutrients">,
  t: Translate,
  locale: Locale,
): string {
  if (item.kind === "water") return quantityLabel(item, t, locale);
  return `${quantityLabel(item, t, locale)} · ${amount(item.nutrients.kcal ?? 0, 0)} kcal`;
}

export function measureLabel(measure: Measure): string {
  return `${measure.name} · ${amount(measure.grams, 0)} g`;
}

function replacementName(next: Replacement): string {
  if (next.kind === "food") return next.food.label;
  if (next.kind === "recipe") return next.recipe.name;
  return next.candidate.name;
}

export function ItemSheet({
  entry,
  item,
  meals = [],
  onClose,
  onChanged,
}: {
  entry: Entry;
  item: Item;
  meals?: Meal[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const [step, setStep] = useState<Step>("main");
  const [quantity, setQuantity] = useState<number | null>(item.quantity);
  const [meal, setMeal] = useState<MealKey>(entry.meal);
  const [measures, setMeasures] = useState<Measure[]>([]);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Found | null>(null);
  const [busy, setBusy] = useState(false);
  const [replacement, setReplacement] = useState<Replacement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (item.kind !== "food" && item.kind !== "recipe") return;
    readMeasures(item.id)
      .then((next) => setMeasures(item.unit === "g" ? next.measures : []))
      .catch(() => setMeasures([]));
  }, [item.id, item.kind, item.unit]);

  useEffect(() => {
    const text = query.trim();
    if (step !== "food" || text.length < 2) {
      setFound(null);
      return;
    }
    setBusy(true);
    const timer = window.setTimeout(() => {
      search(text, false)
        .then(setFound)
        .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : t("item.search_failed")))
        .finally(() => setBusy(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, step]);

  const changedQuantity = quantity !== null && quantity > 0 && quantity !== item.quantity;
  const changedMeal = meal !== entry.meal;
  const after = quantity === null ? null : scaled(item, quantity);
  const unit = item.portion && item.unit === "unit" ? item.portion : t(`short.${item.unit}`);
  const mealName = (key: MealKey) => meals.find((one) => one.meal === key)?.label ?? key;
  const fail = (reason: unknown) => {
    setError(reason instanceof Error ? reason.message : t("common.failed"));
    throw reason;
  };

  const confirmChanges = () => {
    const changes = [];
    if (replacement) {
      changes.push({ label: t("item.food"), from: item.name, to: replacementName(replacement) });
      changes.push({ label: t("item.quantity"), to: t("item.same", { quantity: quantityLabel(item, t, locale) }) });
    } else {
      if (changedQuantity && after) {
        changes.push({ label: t("item.quantity"), from: summaryOf(item, t, locale), to: `${amount(quantity)} ${unit} · ${amount(after.kcal, 0)} kcal` });
      }
      if (changedMeal) changes.push({ label: t("item.meal"), from: mealName(entry.meal), to: mealName(meal) });
    }
    return changes;
  };

  const save = async () => {
    if (replacement) {
      const to =
        replacement.kind === "food"
          ? { food_id: replacement.food.id }
          : replacement.kind === "recipe"
            ? { recipe_id: replacement.recipe.id }
            : { source: replacement.candidate.source, source_ref: replacement.candidate.source_ref };
      await swapItem(entry.id, item.id, to).catch(fail);
    } else {
      if (changedQuantity && quantity !== null) await changeItem(entry.id, item.id, quantity).catch(fail);
      if (changedMeal) await moveItem(item.id, meal).catch(fail);
    }
    onChanged();
  };

  const pick = (next: Replacement) => {
    setReplacement(next);
    setStep("confirm");
  };

  return (
    <Sheet
      title={item.name}
      onClose={onClose}
      action={
        step === "main"
          ? { label: t("common.save"), disabled: !changedQuantity && !changedMeal, onClick: () => setStep("confirm") }
          : undefined
      }
    >
      {error && <Notice tone="warning">{error}</Notice>}

      {step === "main" && item.doubt && (
        <Notice
          tone="warning"
          title={t("item.is_it", { name: item.name })}
          action={{
            label: t("item.yes_it_is"),
            onClick: () =>
              void itemIsSure(item.id)
                .then(onChanged)
                .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : t("common.save_failed"))),
          }}
        >
          {item.doubt === "first" ? t("item.first") : t("item.unsure")} {t("item.change_below")}
        </Notice>
      )}
      {step === "main" && (
        <>
          <Hint>
            {t("item.now", { summary: summaryOf(item, t, locale) })}
            {item.kind !== "water" && ` · ${t("with_this.protein", { value: amount(item.nutrients.protein ?? 0) })}`}
          </Hint>
          {item.estimated && <Hint>{t("item.estimated")}</Hint>}
          {item.kind !== "quick" && (
            <Stepper label={t("item.quantity")} value={quantity} step={STEP[item.unit]} min={0} unit={unit} onChange={setQuantity} />
          )}
          {item.kind === "quick" && (
            <Stepper label="Kcal" value={quantity} step={STEP.kcal} min={0} unit="kcal" onChange={setQuantity} />
          )}
          {measures.length > 0 && (
            <ChoiceChips
              label={t("item.measures")}
              value={measures.find((one) => one.grams === quantity)?.name ?? null}
              onChange={(name) => setQuantity(measures.find((one) => one.name === name)?.grams ?? quantity)}
              options={measures.map((one) => ({ value: one.name, label: measureLabel(one) }))}
            />
          )}
          {changedQuantity && after && (
            <Hint>
              {t("item.after", {
                quantity: `${amount(quantity)} ${unit}`,
                kcal: amount(after.kcal, 0),
                protein: amount(after.protein),
              })}
            </Hint>
          )}
          {meals.length > 0 && (
            <ChoiceChips<MealKey>
              label={t("item.meal")}
              value={meal}
              onChange={setMeal}
              options={meals.map((one) => ({ value: one.meal, label: one.label }))}
            />
          )}
          <div className="macros-item-actions">
            {(item.kind === "food" || item.kind === "recipe") && (
              <Button variant="tinted" icon="search" onClick={() => setStep("food")}>
                {t("item.change_food")}
              </Button>
            )}
            <Button variant="tinted" icon="copy" onClick={() => void duplicateItem(item.id).then(onChanged).catch(fail)}>
              {t("item.duplicate")}
            </Button>
            <Button variant="destructive" icon="trash" onClick={() => setStep("delete")}>
              {t("common.delete")}
            </Button>
          </div>
        </>
      )}

      {step === "food" && (
        <>
          <SearchField label={t("item.search")} value={query} onChange={setQuery} placeholder={item.name} />
          <Hint>{t("item.keeps", { quantity: quantityLabel(item, t, locale) })}</Hint>
          {busy && !found && <Hint>{t("common.searching")}</Hint>}
          {found && (
            <List>
              {found.foods.map((food) => (
                <ListRow key={food.id} title={food.label} subtitle={t("source.pantry")} onClick={() => pick({ kind: "food", food })} />
              ))}
              {found.recipes.map((recipe) => (
                <ListRow key={recipe.id} title={recipe.name} subtitle={t("source.recipe")} onClick={() => pick({ kind: "recipe", recipe })} />
              ))}
              {found.candidates.map((candidate) => (
                <ListRow
                  key={`${candidate.source}:${candidate.source_ref}`}
                  title={candidate.name}
                  subtitle={candidate.source === "usda" ? "USDA" : "Open Food Facts"}
                  onClick={() => pick({ kind: "outside", candidate })}
                />
              ))}
            </List>
          )}
          {found && found.foods.length + found.recipes.length === 0 && found.candidates.length === 0 && (
            <Button
              variant="tinted"
              icon="search"
              onClick={() => {
                setBusy(true);
                void search(query.trim(), true)
                  .then(setFound)
                  .finally(() => setBusy(false));
              }}
            >
              {t("item.search_outside")}
            </Button>
          )}
          <Button onClick={() => setStep("main")}>{t("common.back")}</Button>
        </>
      )}

      {step === "confirm" && (
        <ConfirmPanel
          title={replacement ? t("item.change_food_title") : t("item.save_title")}
          changes={confirmChanges()}
          detail={replacement ? t("item.change_food_detail") : undefined}
          action={replacement ? t("item.change_food") : t("item.save_changes")}
          onCancel={() => {
            setReplacement(null);
            setStep("main");
          }}
          onConfirm={save}
        />
      )}

      {step === "delete" && (
        <ConfirmPanel
          title={t("item.delete_title")}
          detail={
            entry.items.length === 1
              ? t("item.delete_only")
              : t("item.delete_detail")
          }
          action={t("common.delete")}
          destructive
          onCancel={() => setStep("main")}
          onConfirm={() => removeItem(item.id).then(onChanged)}
        />
      )}
    </Sheet>
  );
}
