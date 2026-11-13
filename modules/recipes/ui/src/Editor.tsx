import {
  Button,
  CheckChips,
  ChoiceChips,
  ErrorState,
  GroupLabel,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  Screen,
  SegmentedControl,
  Sheet,
  Skeleton,
  Stepper,
  Switch,
  TextField,
  type Translate,
  useT,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Food,
  type IngredientIn,
  type Recipe,
  type StepIn,
  type Unit,
  Unauthorised,
  changed,
  createRecipe,
  labelOf,
  readFoods,
  readRecipe,
  signIn,
  updateRecipe,
} from "./api";
import { ScreenHeader } from "./Header";
import { macroLine } from "./macros";
import { ACTIONS, EQUIPMENT, USUALLY_UNATTENDED, actionName, equipmentName } from "./steps";
import { UNITS, quantityLabel, unitName, unitShort } from "./units";

interface Draft {
  name: string;
  servings: number;
  tags: string;
  ingredients: (IngredientIn & { label: string })[];
  steps: StepIn[];
}

const EMPTY: Draft = { name: "", servings: 4, tags: "", ingredients: [], steps: [] };

export function draftOf(recipe: Recipe): Draft {
  return {
    name: recipe.name,
    servings: recipe.servings,
    tags: recipe.tags.map((tag) => tag.name).join(", "),
    ingredients: recipe.groups
      .flatMap((group) => group.ingredients)
      .sort((a, b) => a.position - b.position)
      .map((one) => ({
        food_id: one.food_id,
        name: one.food_id ? null : one.name,
        quantity: (one.quantity * recipe.servings) / recipe.requested_servings,
        unit: one.unit,
        note: one.note,
        optional: one.optional,
        portion: one.portion ?? null,
        as_purchased: one.as_purchased ?? false,
        label: one.name,
      })),
    steps: recipe.kitchen.steps.map((step) => ({
      action: step.action,
      text: step.text,
      minutes: step.minutes,
      attended: step.attended,
      equipment: step.equipment,
      after: [...step.after],
      ingredients: [...step.uses],
    })),
  };
}

export function toRequest(draft: Draft) {
  return {
    name: draft.name.trim(),
    servings: draft.servings,
    tags: draft.tags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
    ingredients: draft.ingredients.map((one) => ({
      food_id: one.food_id,
      name: one.name,
      quantity: one.quantity,
      unit: one.unit,
      note: one.note,
      optional: one.optional,
      portion: one.unit === "unit" ? (one.portion ?? null) : null,
      as_purchased: one.as_purchased ?? false,
    })),
    steps: draft.steps,
  };
}

export function canSave(draft: Draft): boolean {
  return draft.name.trim().length > 0 && draft.ingredients.length > 0;
}

export function EditorScreen({
  id,
  onDone,
  onCancel,
}: {
  id?: string;
  onDone: (id: string) => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [pantry, setPantry] = useState<Food[]>([]);
  const [adding, setAdding] = useState(false);
  const [addingStep, setAddingStep] = useState(false);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");
  const [loaded, setLoaded] = useState(!id);
  const [unread, setUnread] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    void readFoods()
      .then(setPantry)
      .catch((error: unknown) => error instanceof Unauthorised && signIn());
  }, []);

  useEffect(() => {
    if (!id) return;
    setUnread(null);
    void readRecipe(id)
      .then((recipe) => {
        setDraft(draftOf(recipe));
        setLoaded(true);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setUnread(error instanceof Error ? error.message : "");
      });
  }, [id, attempt]);

  async function save() {
    setSaving(true);
    setProblem("");
    try {
      const body = toRequest(draft);
      const saved = id ? await updateRecipe(id, body) : await createRecipe(body);
      changed();
      onDone(saved.id);
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : t("editor.save_failed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Screen>
      <ScreenHeader
        back={{ label: id ? t("recipe.title") : t("tabs.recipes"), onClick: onCancel }}
        title={id ? t("editor.edit") : t("editor.new")}
      />
      <OfflineNotice />
      {!loaded && unread !== null && (
        <ErrorState
          title={t("recipe.read_failed")}
          detail={unread || undefined}
          onRetry={() => setAttempt((n) => n + 1)}
        />
      )}
      {!loaded && unread === null && <Skeleton label={t("recipe.loading")} />}
      {loaded && (
        <>
          <TextField
            label={t("editor.name")}
            value={draft.name}
            onChange={(name) => setDraft({ ...draft, name })}
            placeholder={t("editor.name_placeholder")}
          />

          <div className="surface recipes-panel">
            <GroupLabel>{t("recipe.how_many")}</GroupLabel>
            <Stepper
              label={t("recipe.how_many")}
              value={draft.servings}
              step={1}
              min={1}
              max={50}
              inputMode="numeric"
              onChange={(servings) => setDraft({ ...draft, servings: servings ?? 1 })}
            />
          </div>

          <TextField
            label={t("recipe.tags")}
            value={draft.tags}
            onChange={(tags) => setDraft({ ...draft, tags })}
            placeholder={t("editor.tags_placeholder")}
            hint={t("editor.tags_hint")}
          />

          <section className="recipes-group">
            <GroupLabel>{t("recipe.ingredients")}</GroupLabel>
            {draft.ingredients.length === 0 && <Hint>{t("editor.no_ingredients")}</Hint>}
            <List>
              {draft.ingredients.map((one, index) => (
                <ListRow
                  key={`${one.label}-${index}`}
                  title={one.label}
                  detail={quantityLabel(one.quantity, one.unit, t)}
                  action={{ icon: "close", label: t("editor.remove", { name: one.label }), onClick: () => setDraft({ ...draft, ...withoutIngredient(draft, index) }) }}
                />
              ))}
            </List>
            <Button icon="plus" onClick={() => setAdding(true)}>
              {t("editor.add_ingredient")}
            </Button>
          </section>

          <section className="recipes-group">
            <GroupLabel>{t("kitchen.steps")}</GroupLabel>
            {draft.steps.length === 0 && (
              <Hint>{t("editor.no_steps")}</Hint>
            )}
            <List>
              {draft.steps.map((step, index) => (
                <ListRow
                  key={`${step.text}-${index}`}
                  title={`${index + 1}. ${step.text}`}
                  subtitle={stepLine(step, index, draft.ingredients, t)}
                  action={{ icon: "close", label: t("editor.remove_step", { number: index + 1 }), onClick: () => setDraft({ ...draft, steps: withoutStep(draft.steps, index) }) }}
                />
              ))}
            </List>
            <Button icon="plus" onClick={() => setAddingStep(true)}>
              {t("editor.add_step")}
            </Button>
          </section>

          {problem && <Hint tone="warning">{problem}</Hint>}

          <div className="recipes-actions">
            <Button onClick={onCancel}>{t("common.cancel")}</Button>
            <Button variant="primary" disabled={!canSave(draft) || saving} onClick={() => void save()}>
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </div>

          {addingStep && (
            <StepSheet
              position={draft.steps.length + 1}
              ingredients={draft.ingredients}
              onClose={() => setAddingStep(false)}
              onAdd={(step) => {
                setDraft({ ...draft, steps: [...draft.steps, step] });
                setAddingStep(false);
              }}
            />
          )}
          {adding && (
            <IngredientSheet
              pantry={pantry}
              onClose={() => setAdding(false)}
              onAdd={(ingredient) => {
                setDraft({ ...draft, ingredients: [...draft.ingredients, ingredient] });
                setAdding(false);
              }}
            />
          )}
        </>
      )}
      <AppVersion />
    </Screen>
  );
}

function IngredientSheet({
  pantry,
  onClose,
  onAdd,
}: {
  pantry: Food[];
  onClose: () => void;
  onAdd: (ingredient: IngredientIn & { label: string }) => void;
}) {
  const t = useT();
  const [chosen, setChosen] = useState<Food | null>(null);
  const [quantity, setQuantity] = useState("100");
  const [unit, setUnit] = useState<Unit>("g");
  const [note, setNote] = useState("");
  const amount = Number(quantity.replace(",", "."));

  return (
    <Sheet
      title={t("editor.add_ingredient")}
      onClose={onClose}
      action={{
        label: t("common.add"),
        disabled: !chosen || !Number.isFinite(amount) || amount <= 0,
        onClick: () =>
          chosen &&
          onAdd({
            food_id: chosen.id,
            quantity: amount,
            unit,
            note: note.trim() || null,
            label: labelOf(chosen),
          }),
      }}
    >
      {pantry.length === 0 && <Hint>{t("editor.empty_pantry")}</Hint>}
      <ChoiceChips
        label={t("editor.food")}
        value={chosen?.id ?? null}
        onChange={(id) => setChosen(pantry.find((food) => food.id === id) ?? null)}
        options={[...pantry]
          .sort((a, b) => labelOf(a).localeCompare(labelOf(b)))
          .map((food) => ({ value: food.id, label: labelOf(food) }))}
      />
      {chosen && <Hint>{t("editor.per_100", { line: macroLine(chosen.macros, t) })}</Hint>}
      <TextField label={t("editor.quantity")} inputMode="decimal" value={quantity} onChange={setQuantity} />
      <SegmentedControl
        label={t("editor.unit")}
        value={unit}
        onChange={setUnit}
        options={UNITS.slice(0, 3).map((one) => ({ value: one, label: unitShort(t, one) }))}
      />
      <ChoiceChips
        label={t("editor.other_units")}
        value={unit}
        onChange={setUnit}
        options={UNITS.slice(3).map((one) => ({ value: one, label: unitName(t, one) }))}
      />
      <TextField label={t("editor.note")} value={note} onChange={setNote} placeholder={t("editor.note_placeholder")} />
    </Sheet>
  );
}

export function withoutStep(steps: StepIn[], index: number): StepIn[] {
  const gone = index + 1;
  return steps
    .filter((_, other) => other !== index)
    .map((step) => ({
      ...step,
      after: step.after.filter((one) => one !== gone).map((one) => (one > gone ? one - 1 : one)),
    }));
}

export function withoutIngredient(draft: Draft, index: number): Pick<Draft, "ingredients" | "steps"> {
  const gone = index + 1;
  return {
    ingredients: draft.ingredients.filter((_, other) => other !== index),
    steps: draft.steps.map((step) => ({
      ...step,
      ingredients: step.ingredients.filter((one) => one !== gone).map((one) => (one > gone ? one - 1 : one)),
    })),
  };
}

function StepSheet({
  position,
  ingredients,
  onClose,
  onAdd,
}: {
  position: number;
  ingredients: (IngredientIn & { label: string })[];
  onClose: () => void;
  onAdd: (step: StepIn) => void;
}) {
  const t = useT();
  const [action, setAction] = useState("chop");
  const [text, setText] = useState("");
  const [minutes, setMinutes] = useState(10);
  const [equipment, setEquipment] = useState("board");
  const [attended, setAttended] = useState(true);
  const [together, setTogether] = useState(false);
  const [touched, setTouched] = useState(false);
  const [uses, setUses] = useState<string[]>([]);

  function chooseAction(next: string) {
    setAction(next);
    if (!touched) setAttended(!USUALLY_UNATTENDED.has(next));
  }

  return (
    <Sheet
      title={t("editor.step", { number: position })}
      onClose={onClose}
      action={{
        label: t("common.add"),
        disabled: text.trim().length === 0,
        onClick: () =>
          onAdd({
            action,
            text: text.trim(),
            minutes,
            attended,
            equipment,
            after: position === 1 || together ? [] : [position - 1],
            ingredients: uses.map(Number).sort((a, b) => a - b),
          }),
      }}
    >
      <TextField
        label={t("editor.what")}
        value={text}
        onChange={setText}
        placeholder={t("editor.what_placeholder")}
      />
      <ChoiceChips
        label={t("editor.verb")}
        value={action}
        onChange={chooseAction}
        options={ACTIONS.map((value) => ({ value, label: actionName(t, value) }))}
      />
      <Stepper
        label={t("editor.minutes")}
        value={minutes}
        step={5}
        min={1}
        max={2880}
        unit="min"
        inputMode="numeric"
        onChange={(value) => setMinutes(value ?? 1)}
      />
      <ChoiceChips
        label={t("editor.where")}
        value={equipment}
        onChange={setEquipment}
        options={EQUIPMENT.map((value) => ({ value, label: equipmentName(t, value) }))}
      />
      {ingredients.length > 0 && (
        <CheckChips
          label={t("editor.uses")}
          values={uses}
          onChange={setUses}
          options={ingredients.map((one, index) => ({
            value: String(index + 1),
            label: one.label,
          }))}
        />
      )}
      <Switch
        label={t("editor.attended")}
        checked={attended}
        onChange={(value) => {
          setTouched(true);
          setAttended(value);
        }}
      />
      {position > 1 && <Switch label={t("editor.together")} checked={together} onChange={setTogether} />}
    </Sheet>
  );
}

export function stepLine(
  step: { action: string; minutes: number; equipment: string; attended: boolean; after: number[]; ingredients: number[] },
  index: number,
  ingredients: { label: string }[],
  t: Translate,
): string {
  return [
    actionName(t, step.action),
    `${step.minutes} min`,
    equipmentName(t, step.equipment),
    !step.attended ? t("kitchen.runs_alone") : null,
    step.after.length === 0 && index > 0 ? t("editor.with_previous") : null,
    step.ingredients.length > 0
      ? step.ingredients
          .map((one) => ingredients[one - 1]?.label)
          .filter(Boolean)
          .join(", ")
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
