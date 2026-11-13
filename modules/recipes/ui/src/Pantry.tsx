import { mutate, useResource } from "@openarga/app";
import {
  Button,
  ChoiceChips,
  EmptyState,
  ErrorState,
  GroupLabel,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  Screen,
  SelectField,
  Sheet,
  Skeleton,
  TextField,
  type Translate,
  useT,
} from "@openarga/ui";
import { useMemo, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Candidate,
  type Category,
  type Food,
  type SearchOut,
  Unauthorised,
  createManualFood,
  importFood,
  labelOf,
  readCategories,
  readFoods,
  replaceFood,
  searchFoods,
  setFoodAlias,
  signIn,
  changed,
} from "./api";
import { categoryName } from "./categories";
import { ScreenHeader } from "./Header";
import { kcal, macroLine, pantryLine, sourceLabel } from "./macros";
import { closeness, ranked } from "./search";

export const FOODS = "foods";

export function PantryScreen() {
  const t = useT();
  const read = useResource(FOODS, readFoods, { persist: true });
  const foods = read.data ?? null;
  const categories = useResource("categories", readCategories, { persist: true }).data ?? [];
  const setFoods = (next: (current: Food[] | undefined) => Food[]) => void mutate(FOODS, next);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<SearchOut | null>(null);
  const [searching, setSearching] = useState(false);
  const [problem, setProblem] = useState("");
  const [adding, setAdding] = useState<Candidate | null>(null);
  const [byHand, setByHand] = useState(false);
  const [open, setOpen] = useState<Food | null>(null);

  const needle = query.trim();
  const mine = useMemo(
    () => (needle ? ranked(foods ?? [], needle, (food) => [food.alias, food.name], labelOf) : (foods ?? [])),
    [foods, needle],
  );
  const grouped = useMemo(() => (needle ? [] : groupByCategory(mine, categories)), [mine, categories, needle]);

  async function lookOutside() {
    setSearching(true);
    setProblem("");
    try {
      setFound(await searchFoods(query.trim()));
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(t("pantry.search_failed"));
    } finally {
      setSearching(false);
    }
  }

  function remember(food: Food) {
    setFoods((current) => [...(current ?? []).filter((one) => one.id !== food.id), food]);
    changed();
    setFound(null);
    setAdding(null);
    setByHand(false);
    setOpen(null);
  }

  return (
    <Screen>
      <ScreenHeader title={t("tabs.pantry")} />
      <OfflineNotice />

      <TextField
        label={t("pantry.search")}
        type="search"
        value={query}
        onChange={setQuery}
        placeholder={t("pantry.search_placeholder")}
        onSubmit={() => query.trim().length >= 2 && void lookOutside()}
        hint={t("pantry.barcode")}
      />

      <div className="recipes-actions">
        {query.trim().length >= 2 && (
          <Button variant="tinted" disabled={searching} onClick={() => void lookOutside()}>
            {searching ? t("pantry.searching_outside") : t("pantry.search_outside")}
          </Button>
        )}
        <Button variant="plain" icon="plus" onClick={() => setByHand(true)}>
          {t("pantry.by_hand")}
        </Button>
      </div>

      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}

      {found && <Outside found={found} onAdd={setAdding} />}

      {read.loading && <Skeleton label={t("pantry.loading")} />}
      {foods === null && read.error && (
        <ErrorState title={t("pantry.read_failed")} detail={read.error.message} onRetry={read.refresh} />
      )}
      {foods !== null && foods.length === 0 && (
        <EmptyState
          title={t("pantry.empty")}
          action={{ label: t("pantry.create_one"), icon: "plus", onClick: () => setByHand(true) }}
        >
          {t("pantry.empty_detail")}
        </EmptyState>
      )}

      {needle && foods !== null && foods.length > 0 && (
        <section className="recipes-group">
          <GroupLabel count={mine.length}>{t("pantry.in_yours")}</GroupLabel>
          {mine.length > 0 ? (
            <List>
              {mine.map((food) => (
                <ListRow
                  key={food.id}
                  title={labelOf(food)}
                  subtitle={pantryLine(food.macros, t)}
                  value={`${kcal(food.macros.kcal)} kcal`}
                  accessory="chevron-right"
                  onClick={() => setOpen(food)}
                />
              ))}
            </List>
          ) : (
            <Hint>{t("pantry.nothing_with", { needle })}</Hint>
          )}
        </section>
      )}

      {grouped.map(({ category, items }) => (
        <section key={category.id} className="recipes-group">
          <GroupLabel>
            <span aria-hidden="true">{category.emoji}</span> {categoryName(t, category.id, category.name)}
          </GroupLabel>
          <List>
            {items.map((food) => (
              <ListRow
                key={food.id}
                title={labelOf(food)}
                subtitle={pantryLine(food.macros, t)}
                value={`${kcal(food.macros.kcal)} kcal`}
                accessory="chevron-right"
                onClick={() => setOpen(food)}
              />
            ))}
          </List>
        </section>
      ))}

      {adding && (
        <AddSheet
          candidate={adding}
          categories={categories}
          onClose={() => setAdding(null)}
          onAdded={remember}
        />
      )}
      {byHand && (
        <ManualSheet categories={categories} onClose={() => setByHand(false)} onAdded={remember} />
      )}
      {open && (
        <FoodSheet
          food={open}
          others={foods ?? []}
          onClose={() => setOpen(null)}
          onSaved={remember}
          onReplaced={(old) => {
            setFoods((current) => (current ?? []).filter((one) => one.id !== old.id));
            changed();
            setOpen(null);
          }}
        />
      )}
      <AppVersion />
    </Screen>
  );
}

export function matches(food: Food, needle: string): boolean {
  return closeness(needle, food.alias, food.name) !== null;
}

export function groupByCategory(
  foods: Food[],
  categories: Category[],
): { category: Category; items: Food[] }[] {
  return categories
    .map((category) => ({
      category,
      items: foods
        .filter((food) => food.category_id === category.id)
        .sort((a, b) => labelOf(a).localeCompare(labelOf(b))),
    }))
    .filter(({ items }) => items.length > 0);
}

export function Outside({ found, onAdd }: { found: SearchOut; onAdd: (c: Candidate) => void }) {
  const t = useT();
  return (
    <section className="recipes-group">
      <GroupLabel>{t("pantry.outside")}</GroupLabel>
      {found.failed.map((failure) => (
        <Hint key={failure.source} tone="warning">
          {failure.reason}
        </Hint>
      ))}
      {(found.discarded ?? []).length > 0 && (
        <Hint>
          {t(found.discarded!.length === 1 ? "pantry.discarded.one" : "pantry.discarded.other", {
            count: found.discarded!.length,
            names: found.discarded!.map((one) => `${one.name} (${one.reason})`).join(", "),
          })}
        </Hint>
      )}
      {found.candidates.length === 0 && (
        <Hint>{t("pantry.no_source")}</Hint>
      )}
      <List>
        {found.candidates.map((candidate) => (
          <ListRow
            key={`${candidate.source}:${candidate.source_ref}`}
            title={candidate.brand ? `${candidate.name} · ${candidate.brand}` : candidate.name}
            detail={`${macroLine(candidate.macros, t)} · ${sourceLabel(candidate.source, false, t)}${
              candidate.known_id ? ` · ${t("pantry.already_have")}` : ""
            }`}
            accessory={candidate.known_id ? "done" : "plus"}
            onClick={() => onAdd(candidate)}
          />
        ))}
      </List>
    </section>
  );
}

function AddSheet({
  candidate,
  categories,
  onClose,
  onAdded,
}: {
  candidate: Candidate;
  categories: Category[];
  onClose: () => void;
  onAdded: (food: Food) => void;
}) {
  const t = useT();
  const [alias, setAlias] = useState("");
  const [category, setCategory] = useState(candidate.category_hint);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");

  async function save() {
    setSaving(true);
    setProblem("");
    try {
      onAdded(
        await importFood({
          source: candidate.source,
          source_ref: candidate.source_ref,
          name: candidate.name,
          category_id: category,
          macros: candidate.macros,
          alias: alias.trim() || null,
        }),
      );
    } catch (error) {
      setProblem(error instanceof Error ? error.message : t("pantry.add_failed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet
      title={t("pantry.add_title")}
      onClose={onClose}
      action={{ label: saving ? t("common.saving") : t("common.add"), onClick: () => void save(), disabled: saving }}
    >
      <TextField
        label={t("pantry.alias")}
        value={alias}
        onChange={setAlias}
        placeholder={candidate.name}
        hint={t("pantry.alias_empty")}
      />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      <Hint>
        {t("pantry.per_100_from", {
          line: macroLine(candidate.macros, t),
          source: sourceLabel(candidate.source, false, t),
        })}
      </Hint>
      <ChoiceChips
        label={t("pantry.category")}
        value={category}
        onChange={setCategory}
        options={categories.map((one) => ({ value: one.id, label: `${one.emoji} ${categoryName(t, one.id, one.name)}` }))}
      />
    </Sheet>
  );
}

export function perLabel(food: Food, t: Translate): string {
  return food.nutrients_per === "unit" ? (food.unit_name ?? t("pantry.unit")) : "100 g";
}

export function foodDetails(food: Food, t: Translate): string[] {
  const lines: string[] = [];
  if (food.provenance) lines.push(t("food.figures_from", { provenance: food.provenance }));
  if (food.micros_from && (food.borrowed ?? []).length > 0) {
    const count = food.borrowed!.length;
    lines.push(
      t(count === 1 ? "food.borrowed.one" : "food.borrowed.other", {
        count,
        from: food.micros_from_label ?? t("food.another"),
      }),
    );
  }
  const portions = food.portions ?? [];
  if (portions.length > 0) {
    lines.push(t("food.measures", { list: portions.map((one) => `${one.name}, ${one.grams} g`).join(" · ") }));
  }
  if (food.edible_fraction != null && food.edible_fraction < 1) {
    lines.push(t("food.edible", { pct: Math.round(food.edible_fraction * 100) }));
  }
  return lines;
}

export function FoodSheet({
  food,
  others = [],
  onClose,
  onSaved,
  onReplaced = () => undefined,
}: {
  food: Food;
  others?: Food[];
  onClose: () => void;
  onSaved: (food: Food) => void;
  onReplaced?: (old: Food) => void;
}) {
  const t = useT();
  const [alias, setAlias] = useState(food.alias ?? "");
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");
  const [target, setTarget] = useState("");
  const candidates = replacements(food, others);

  async function replace() {
    const chosen = candidates.find((one) => one.id === target);
    if (!chosen) return;
    const sure = window.confirm(
      t("food.replace_confirm", { old: labelOf(food), new: labelOf(chosen) }),
    );
    if (!sure) return;
    setSaving(true);
    setProblem("");
    try {
      const done = await replaceFood(food.id, chosen.id);
      if (!done.macros.done) {
        setProblem(t("food.replace_partial", { note: done.macros.note ?? "" }));
        return;
      }
      onReplaced(food);
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : t("food.replace_failed"));
    } finally {
      setSaving(false);
    }
  }

  async function save() {
    setSaving(true);
    setProblem("");
    try {
      onSaved(await setFoodAlias(food.id, alias.trim() || null));
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : t("editor.save_failed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet
      title={labelOf(food)}
      onClose={onClose}
      action={{ label: saving ? t("common.saving") : t("common.save"), onClick: () => void save(), disabled: saving }}
    >
      <TextField
        label={t("pantry.alias")}
        value={alias}
        onChange={setAlias}
        placeholder={food.name}
        hint={t("food.alias_hint")}
      />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      <Hint>
        {t("food.source_name", { source: sourceLabel(food.source, food.corrected, t), name: food.name })}
      </Hint>
      <Hint>
        {t("food.per", { line: macroLine(food.macros, t), per: perLabel(food, t) })}
      </Hint>
      {foodDetails(food, t).map((line) => (
        <Hint key={line}>{line}</Hint>
      ))}
      {candidates.length > 0 && (
        <>
          <SelectField
            label={t("food.replace_with")}
            value={target}
            onChange={setTarget}
            options={[
              { value: "", label: "—" },
              ...candidates.map((one) => ({ value: one.id, label: labelOf(one) })),
            ]}
          />
          {target && (
            <Button variant="destructive" disabled={saving} onClick={() => void replace()}>
              {t("food.replace")}
            </Button>
          )}
        </>
      )}
    </Sheet>
  );
}

export function replacements(food: Food, others: Food[]): Food[] {
  const per = food.nutrients_per ?? "100g";
  return others
    .filter((one) => one.id !== food.id && (one.nutrients_per ?? "100g") === per)
    .sort((a, b) => labelOf(a).localeCompare(labelOf(b)));
}

function ManualSheet({
  categories,
  onClose,
  onAdded,
}: {
  categories: Category[];
  onClose: () => void;
  onAdded: (food: Food) => void;
}) {
  const t = useT();
  const [name, setName] = useState("");
  const [category, setCategory] = useState("other");
  const [values, setValues] = useState({ kcal: "", protein: "", fat: "", carbs: "" });
  const [saving, setSaving] = useState(false);

  const numbers = {
    kcal: Number(values.kcal.replace(",", ".")),
    protein: Number(values.protein.replace(",", ".")),
    fat: Number(values.fat.replace(",", ".")),
    carbs: Number(values.carbs.replace(",", ".")),
  };
  const complete =
    name.trim().length > 0 && Object.values(numbers).every((value) => Number.isFinite(value) && value >= 0);

  async function save() {
    setSaving(true);
    try {
      onAdded(
        await createManualFood({
          name: name.trim(),
          category_id: category,
          macros: { ...numbers, fiber: null, salt: null },
        }),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet
      title={t("manual.title")}
      onClose={onClose}
      action={{ label: saving ? t("common.saving") : t("manual.create"), onClick: () => void save(), disabled: !complete || saving }}
    >
      <TextField label={t("editor.name")} value={name} onChange={setName} placeholder={t("manual.placeholder")} />
      <Hint>{t("manual.per_100")}</Hint>
      <div className="recipes-macro-fields">
        <TextField label="kcal" inputMode="decimal" value={values.kcal} onChange={(v) => setValues({ ...values, kcal: v })} />
        <TextField label={t("manual.protein")} inputMode="decimal" value={values.protein} onChange={(v) => setValues({ ...values, protein: v })} />
        <TextField label={t("manual.fat")} inputMode="decimal" value={values.fat} onChange={(v) => setValues({ ...values, fat: v })} />
        <TextField label={t("manual.carbs")} inputMode="decimal" value={values.carbs} onChange={(v) => setValues({ ...values, carbs: v })} />
      </div>
      <ChoiceChips
        label={t("pantry.category")}
        value={category}
        onChange={setCategory}
        options={categories.map((one) => ({ value: one.id, label: `${one.emoji} ${categoryName(t, one.id, one.name)}` }))}
      />
    </Sheet>
  );
}
