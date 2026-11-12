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
import { ScreenHeader } from "./Header";
import { kcal, macroLine, pantryLine, sourceLabel } from "./macros";
import { closeness, ranked } from "./search";

export const FOODS = "foods";

export function PantryScreen() {
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
      setProblem("No se pudo buscar fuera. Inténtalo en un momento.");
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
      <ScreenHeader title="Despensa" />
      <OfflineNotice />

      <TextField
        label="Buscar un alimento"
        type="search"
        value={query}
        onChange={setQuery}
        placeholder="puerro, yogur, 8410128750121…"
        onSubmit={() => query.trim().length >= 2 && void lookOutside()}
        hint="Un código de barras también vale."
      />

      <div className="recipes-actions">
        {query.trim().length >= 2 && (
          <Button variant="tinted" disabled={searching} onClick={() => void lookOutside()}>
            {searching ? "Buscando fuera…" : "Buscar fuera"}
          </Button>
        )}
        <Button variant="plain" icon="plus" onClick={() => setByHand(true)}>
          Crear a mano
        </Button>
      </div>

      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}

      {found && <Outside found={found} onAdd={setAdding} />}

      {read.loading && <Skeleton label="Cargando la despensa" />}
      {foods === null && read.error && (
        <ErrorState title="No se pudo leer la despensa" detail={read.error.message} onRetry={read.refresh} />
      )}
      {foods !== null && foods.length === 0 && (
        <EmptyState
          title="La despensa está vacía"
          action={{ label: "Crear uno a mano", icon: "plus", onClick: () => setByHand(true) }}
        >
          Las macros no se teclean: se buscan fuera una vez y se quedan aquí. A partir de entonces, cocinar no necesita
          internet. Escribe arriba qué buscas y pulsa «Buscar fuera».
        </EmptyState>
      )}

      {needle && foods !== null && foods.length > 0 && (
        <section className="recipes-group">
          <GroupLabel count={mine.length}>En tu despensa</GroupLabel>
          {mine.length > 0 ? (
            <List>
              {mine.map((food) => (
                <ListRow
                  key={food.id}
                  title={labelOf(food)}
                  subtitle={pantryLine(food.macros)}
                  value={`${kcal(food.macros.kcal)} kcal`}
                  accessory="chevron-right"
                  onClick={() => setOpen(food)}
                />
              ))}
            </List>
          ) : (
            <Hint>Nada con «{needle}» en tu despensa. Pulsa «Buscar fuera».</Hint>
          )}
        </section>
      )}

      {grouped.map(({ category, items }) => (
        <section key={category.id} className="recipes-group">
          <GroupLabel>
            <span aria-hidden="true">{category.emoji}</span> {category.name}
          </GroupLabel>
          <List>
            {items.map((food) => (
              <ListRow
                key={food.id}
                title={labelOf(food)}
                subtitle={pantryLine(food.macros)}
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
        .sort((a, b) => labelOf(a).localeCompare(labelOf(b), "es")),
    }))
    .filter(({ items }) => items.length > 0);
}

export function Outside({ found, onAdd }: { found: SearchOut; onAdd: (c: Candidate) => void }) {
  return (
    <section className="recipes-group">
      <GroupLabel>De fuera</GroupLabel>
      {found.failed.map((failure) => (
        <Hint key={failure.source} tone="warning">
          {failure.reason}
        </Hint>
      ))}
      {(found.discarded ?? []).length > 0 && (
        <Hint>
          {found.discarded!.length === 1
            ? "Uno venía con cifras imposibles y no sale"
            : `${found.discarded!.length} venían con cifras imposibles y no salen`}
          : {found.discarded!.map((one) => `${one.name} (${one.reason})`).join(", ")}.
        </Hint>
      )}
      {found.candidates.length === 0 && (
        <Hint>Ninguna fuente lo tiene. Puedes crearlo a mano.</Hint>
      )}
      <List>
        {found.candidates.map((candidate) => (
          <ListRow
            key={`${candidate.source}:${candidate.source_ref}`}
            title={candidate.brand ? `${candidate.name} · ${candidate.brand}` : candidate.name}
            detail={`${macroLine(candidate.macros)} · ${sourceLabel(candidate.source, false)}${
              candidate.known_id ? " · ya la tienes" : ""
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
      setProblem(error instanceof Error ? error.message : "No se pudo añadir.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet
      title="Añadir a la despensa"
      onClose={onClose}
      action={{ label: saving ? "Guardando…" : "Añadir", onClick: () => void save(), disabled: saving }}
    >
      <TextField
        label="Cómo lo llamas"
        value={alias}
        onChange={setAlias}
        placeholder={candidate.name}
        hint="Vacío, se queda como lo llama la fuente."
      />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      <Hint>
        {macroLine(candidate.macros)} por 100 g, según {sourceLabel(candidate.source, false)}.
      </Hint>
      <ChoiceChips
        label="Categoría"
        value={category}
        onChange={setCategory}
        options={categories.map((one) => ({ value: one.id, label: `${one.emoji} ${one.name}` }))}
      />
    </Sheet>
  );
}

export function perLabel(food: Food): string {
  return food.nutrients_per === "unit" ? (food.unit_name ?? "unidad") : "100 g";
}

export function foodDetails(food: Food): string[] {
  const lines: string[] = [];
  if (food.provenance) lines.push(`Cifras de: ${food.provenance}.`);
  if (food.micros_from && (food.borrowed ?? []).length > 0) {
    const count = food.borrowed!.length;
    lines.push(
      `${count} ${count === 1 ? "nutriente prestado" : "nutrientes prestados"} de ` +
        `«${food.micros_from_label ?? "otro alimento"}».`,
    );
  }
  const portions = food.portions ?? [];
  if (portions.length > 0) {
    lines.push(`Medidas: ${portions.map((one) => `${one.name}, ${one.grams} g`).join(" · ")}.`);
  }
  if (food.edible_fraction != null && food.edible_fraction < 1) {
    lines.push(`Se come el ${Math.round(food.edible_fraction * 100)} % de lo que se pesa entero.`);
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
  const [alias, setAlias] = useState(food.alias ?? "");
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");
  const [target, setTarget] = useState("");
  const candidates = replacements(food, others);

  async function replace() {
    const chosen = candidates.find((one) => one.id === target);
    if (!chosen) return;
    const sure = window.confirm(
      `¿Sustituir «${labelOf(food)}» por «${labelOf(chosen)}» en tus recetas y en lo apuntado en Macros? ` +
        "Las recetas guardan una versión nueva y lo de antes se queda en su historial.",
    );
    if (!sure) return;
    setSaving(true);
    setProblem("");
    try {
      const done = await replaceFood(food.id, chosen.id);
      if (!done.macros.done) {
        setProblem(`Hecho en las recetas, pero Macros no se ha actualizado: ${done.macros.note}. Vuelve a sustituir.`);
        return;
      }
      onReplaced(food);
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : "No se pudo sustituir.");
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
      setProblem(error instanceof Error ? error.message : "No se pudo guardar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet
      title={labelOf(food)}
      onClose={onClose}
      action={{ label: saving ? "Guardando…" : "Guardar", onClick: () => void save(), disabled: saving }}
    >
      <TextField
        label="Cómo lo llamas"
        value={alias}
        onChange={setAlias}
        placeholder={food.name}
        hint="Es el nombre que sale en tus recetas. Vacío, se ve el de la fuente."
      />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      <Hint>
        {sourceLabel(food.source, food.corrected)}: «{food.name}»
      </Hint>
      <Hint>
        {macroLine(food.macros)} por {perLabel(food)}.
      </Hint>
      {foodDetails(food).map((line) => (
        <Hint key={line}>{line}</Hint>
      ))}
      {candidates.length > 0 && (
        <>
          <SelectField
            label="Sustituir por"
            value={target}
            onChange={setTarget}
            options={[
              { value: "", label: "—" },
              ...candidates.map((one) => ({ value: one.id, label: labelOf(one) })),
            ]}
          />
          {target && (
            <Button variant="destructive" disabled={saving} onClick={() => void replace()}>
              Sustituir en recetas y registros
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
    .sort((a, b) => labelOf(a).localeCompare(labelOf(b), "es"));
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
      title="Crear un alimento"
      onClose={onClose}
      action={{ label: saving ? "Guardando…" : "Crear", onClick: () => void save(), disabled: !complete || saving }}
    >
      <TextField label="Nombre" value={name} onChange={setName} placeholder="Sofrito de casa" />
      <Hint>Por 100 g, que es como se suman.</Hint>
      <div className="recipes-macro-fields">
        <TextField label="kcal" inputMode="decimal" value={values.kcal} onChange={(v) => setValues({ ...values, kcal: v })} />
        <TextField label="Proteína (g)" inputMode="decimal" value={values.protein} onChange={(v) => setValues({ ...values, protein: v })} />
        <TextField label="Grasa (g)" inputMode="decimal" value={values.fat} onChange={(v) => setValues({ ...values, fat: v })} />
        <TextField label="Hidratos (g)" inputMode="decimal" value={values.carbs} onChange={(v) => setValues({ ...values, carbs: v })} />
      </div>
      <ChoiceChips
        label="Categoría"
        value={category}
        onChange={setCategory}
        options={categories.map((one) => ({ value: one.id, label: `${one.emoji} ${one.name}` }))}
      />
    </Sheet>
  );
}
