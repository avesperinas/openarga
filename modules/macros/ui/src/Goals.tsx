import {
  type BodyWeightHistory,
  BodyWeightCard,
  Button,
  ChoiceChips,
  ErrorState,
  GroupLabel,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  Screen,
  Sheet,
  Skeleton,
  TextField,
  useToast,
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import {
  type DayKindInfo,
  type GoalInfo,
  type NutrientInfo,
  type Profile,
  type Reference,
  type Target,
  Unauthorised,
  logWeight,
  readNutrients,
  readReferences,
  readTarget,
  readGoals,
  readWeight,
  resetGoal,
  saveGoal,
  saveTarget,
  setDayKind,
  signIn,
} from "./api";
import { ScreenHeader } from "./Header";
import { amount, todayIso } from "./words";

const FIELDS = [
  { key: "kcal", label: "Kcal" },
  { key: "protein", label: "Proteína, g" },
  { key: "carbs", label: "Hidratos, g" },
  { key: "fat", label: "Grasa, g" },
] as const;

const KIND = { min: "mínimo", max: "máximo", energy_share: "de las kcal" } as const;

const SHARES = new Set([
  "protein", "carbs", "fat", "fiber", "sugars", "added_sugars", "starch", "saturated_fat",
  "monounsaturated_fat", "polyunsaturated_fat", "trans_fat", "alcohol",
]);

function parsed(text: string): number | null {
  const value = Number(text.replace(",", "."));
  return text.trim() && Number.isFinite(value) && value >= 0 ? value : null;
}

export function referenceLabel(reference: Reference, unit: string): string {
  if (reference.kind === "energy_share") return `${amount(reference.value * 100, 0)} % de las kcal, como tope`;
  return `${amount(reference.value)} ${unit} ${KIND[reference.kind]}`;
}

const PROFILES = [
  { value: "any", label: "Todos los días" },
  { value: "training", label: "Entreno" },
  { value: "rest", label: "Descanso" },
] as const;

const SOURCES = { own: "tuyo", legacy: "tuyo", efsa: "EFSA" } as const;

export const PER_KG = new Set(["kcal", "protein", "carbs", "fat"]);

export function goalLabel(goal: Pick<GoalInfo, "min" | "max" | "unit" | "nutrient_unit" | "kg" | "amount">): string {
  if (goal.unit === "per_kg") {
    const said = goalLabel({ ...goal, unit: "amount", nutrient_unit: `${goal.nutrient_unit}/kg` });
    const today = goal.amount ? goalLabel({ ...goal.amount, unit: "amount", nutrient_unit: goal.nutrient_unit }) : null;
    return today && goal.kg ? `${said} · ${today.replace(/^[≥≤] /, "")} con ${amount(goal.kg)} kg` : said;
  }
  const unit = goal.unit === "kcal_pct" ? "% de las kcal" : goal.nutrient_unit;
  const digits = goal.unit === "kcal_pct" ? 0 : undefined;
  const one = (value: number) => amount(value, digits);
  if (goal.min !== null && goal.max !== null) {
    return goal.min === goal.max ? `${one(goal.min)} ${unit}` : `${one(goal.min)} – ${one(goal.max)} ${unit}`;
  }
  if (goal.min !== null) return `≥ ${one(goal.min)} ${unit}`;
  if (goal.max !== null) return `≤ ${one(goal.max)} ${unit}`;
  return "sin objetivo";
}

export function dayKindLabel(found: DayKindInfo): string {
  if (found.kind === "rest") return found.source === "manual" ? "Hoy es de descanso, a mano." : "Hoy es de descanso.";
  if (found.source === "manual") return "Hoy es de entreno, a mano.";
  return `Hoy es de entreno: ${found.workouts.join(", ")}.`;
}

export function proteinPerKilo(protein: number | null, kg: number | null): string | null {
  if (!protein || !kg) return null;
  return `Tu objetivo de proteína son ${amount(protein / kg, 1)} g por kilo. El mismo peso en Salud y en Training.`;
}

export function GoalsScreen() {
  const [target, setTarget] = useState<Target | null>(null);
  const [goals, setGoals] = useState<GoalInfo[] | null>(null);
  const [kind, setKind] = useState<DayKindInfo | null>(null);
  const [goalProfile, setGoalProfile] = useState<GoalInfo["profile"]>("any");
  const [goalUnit, setGoalUnit] = useState<GoalInfo["unit"]>("amount");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [references, setReferences] = useState<Reference[] | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [nutrients, setNutrients] = useState<NutrientInfo[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [weight, setWeight] = useState<BodyWeightHistory | null>(null);
  const toast = useToast();

  useEffect(() => {
    readWeight()
      .then(setWeight)
      .catch(() => setWeight({ days: [], latest: null }));
  }, []);

  const load = useCallback(() => {
    Promise.all([readTarget(), readReferences(), readNutrients(), readGoals()])
      .then(([found, refs, list, current]) => {
        setGoals(current.goals);
        setKind(current.day_kind);
        setTarget(found);
        setDraft(
          Object.fromEntries(FIELDS.map(({ key }) => [key, found?.[key] == null ? "" : String(found[key])])),
        );
        setReferences(refs.references);
        setProfile(refs.profile);
        setNutrients(list);
      })
      .catch((reason: unknown) => {
        if (reason instanceof Unauthorised) return signIn();
        setError(reason instanceof Error ? reason.message : "No se ha podido cargar");
      });
  }, []);

  useEffect(load, [load]);

  const save = () => {
    const body = Object.fromEntries(FIELDS.map(({ key }) => [key, parsed(draft[key] ?? "")]));
    saveTarget({ ...body, valid_from: todayIso() })
      .then((saved) => {
        setTarget(saved);
        toast({ message: "Objetivo guardado desde hoy" });
      })
      .catch((reason: unknown) =>
        toast({ message: reason instanceof Error ? reason.message : "No se ha podido guardar", tone: "error" }),
      );
  };

  const named = new Map(nutrients.map((one) => [one.key, one]));
  const order = nutrients.map((one) => one.key);
  const editingGoal = goals?.find((one) => one.nutrient === editing) ?? null;
  const open = (nutrient: string) => {
    const found = goals?.find((one) => one.nutrient === nutrient);
    setEditing(nutrient);
    setGoalProfile(found && found.source === "own" ? found.profile : "any");
    setGoalUnit(found?.unit ?? "amount");
    setLow(found?.min == null ? "" : String(found.min));
    setHigh(found?.max == null ? "" : String(found.max));
  };
  const finish = (action: Promise<unknown>) =>
    void action
      .then(() => {
        setEditing(null);
        load();
      })
      .catch((reason: unknown) =>
        toast({ message: reason instanceof Error ? reason.message : "No se ha podido guardar", tone: "error" }),
      );
  const saveEditing = () => {
    if (!editing) return;
    finish(saveGoal(editing, { min: parsed(low), max: parsed(high), unit: goalUnit, profile: goalProfile }));
  };
  const markDay = (next: DayKindInfo["kind"] | null) =>
    void setDayKind(todayIso(), next)
      .then(() => load())
      .catch((reason: unknown) =>
        toast({ message: reason instanceof Error ? reason.message : "No se ha podido guardar", tone: "error" }),
      );

  return (
    <Screen>
      <ScreenHeader title="Objetivo" />
      <OfflineNotice />
      {!references ? (
        error ? (
          <ErrorState
            title="Macros no contesta"
            detail={error}
            onRetry={() => {
              setError(null);
              load();
            }}
          />
        ) : (
          <Skeleton rows={6} />
        )
      ) : (
        <>
          <section className="surface macros-panel" aria-label="Objetivo del día">
            <GroupLabel>Objetivo del día</GroupLabel>
            <div className="macros-fields">
              {FIELDS.map(({ key, label }) => (
                <TextField
                  key={key}
                  label={label}
                  inputMode="decimal"
                  value={draft[key] ?? ""}
                  onChange={(text) => setDraft((current) => ({ ...current, [key]: text }))}
                />
              ))}
            </div>
            <Hint>
              {target ? `Vale desde el ${target.valid_from.split("-").reverse().join("/")}. ` : "Sin objetivo todavía. "}
              Atajo para todos los días: las kcal, los hidratos y la grasa quedan como rango de ±10 %, y la proteína
              como mínimo. Para un rango exacto o un tipo de día, en Objetivos.
            </Hint>
            <Button variant="primary" onClick={save}>
              Guardar desde hoy
            </Button>
          </section>

          <BodyWeightCard
            history={weight}
            note={proteinPerKilo(target?.protein ?? null, weight?.latest?.kg ?? null) ?? undefined}
            onLog={(kg) =>
              logWeight(kg)
                .then(setWeight)
                .catch((reason: unknown) => {
                  toast({ message: reason instanceof Error ? reason.message : "No se ha podido apuntar", tone: "error" });
                  throw reason;
                })
            }
          />

          {kind && (
            <section className="surface macros-panel" aria-label="Tipo de día">
              <GroupLabel>Tipo de día</GroupLabel>
              <Hint>{dayKindLabel(kind)} Los objetivos de entreno o de descanso mandan sobre los de todos los días.</Hint>
              <ChoiceChips
                label="Hoy"
                value={kind.source === "manual" ? kind.kind : "auto"}
                onChange={(next) => markDay(next === "auto" ? null : (next as DayKindInfo["kind"]))}
                options={[
                  { value: "auto", label: "Solo" },
                  { value: "training", label: "Entreno" },
                  { value: "rest", label: "Descanso" },
                ]}
              />
            </section>
          )}

          <section className="surface macros-panel" aria-label="Objetivos">
            <GroupLabel>Objetivos</GroupLabel>
            <Hint>
              {profile?.from_health
                ? `Las de la EFSA para ${profile.sex === "female" ? "una mujer" : profile.sex === "male" ? "un hombre" : "un adulto"}${profile.age ? ` de ${profile.age} años` : ""}, de tu ficha de Apple Salud.`
                : "Las de la EFSA para un adulto de 30 a 59 años: no hay ficha de Apple Salud."}
            </Hint>
            <List>
              {(goals ?? [])
                .filter((goal) => named.has(goal.nutrient))
                .sort((a, b) => order.indexOf(a.nutrient) - order.indexOf(b.nutrient))
                .map((goal) => (
                  <ListRow
                    key={goal.nutrient}
                    title={goal.name}
                    subtitle={goal.profile === "any" ? SOURCES[goal.source] : `${SOURCES[goal.source]}, ${goal.profile === "training" ? "entreno" : "descanso"}`}
                    value={goalLabel(goal)}
                    accessory="edit"
                    onClick={() => open(goal.nutrient)}
                  />
                ))}
            </List>
          </section>
        </>
      )}
      {editing && (
        <Sheet
          title={named.get(editing)?.name ?? editing}
          onClose={() => setEditing(null)}
          action={{ label: "Guardar desde hoy", onClick: saveEditing, disabled: parsed(low) === null && parsed(high) === null }}
        >
          <ChoiceChips label="Para" value={goalProfile} onChange={(next) => setGoalProfile(next as GoalInfo["profile"])} options={[...PROFILES]} />
          {named.get(editing) && (SHARES.has(editing) || PER_KG.has(editing)) && (
            <ChoiceChips
              label="En"
              value={goalUnit}
              onChange={(next) => setGoalUnit(next as GoalInfo["unit"])}
              options={[
                { value: "amount", label: named.get(editing)!.unit },
                ...(SHARES.has(editing) ? [{ value: "kcal_pct", label: "% de las kcal" }] : []),
                ...(PER_KG.has(editing) ? [{ value: "per_kg", label: `${named.get(editing)!.unit} por kilo` }] : []),
              ]}
            />
          )}
          {goalUnit === "per_kg" && (
            <Hint>
              Sigue a tu peso, el mismo de Salud: {weight?.latest ? `hoy ${amount(weight.latest.kg)} kg.` : "aún no hay ninguno, y sin peso no se compara."}
            </Hint>
          )}
          <div className="macros-fields">
            <TextField label="Mínimo" inputMode="decimal" value={low} onChange={setLow} onSubmit={saveEditing} autoFocus />
            <TextField label="Máximo" inputMode="decimal" value={high} onChange={setHigh} onSubmit={saveEditing} />
          </div>
          <Hint>Un mínimo, un máximo o los dos. Lo de antes de hoy se sigue midiendo con lo que había.</Hint>
          {editingGoal && <Hint>Ahora: {goalLabel(editingGoal)} ({SOURCES[editingGoal.source]}).</Hint>}
          <Button onClick={() => finish(saveGoal(editing, { min: null, max: null, unit: "amount", profile: goalProfile }))}>
            Sin objetivo
          </Button>
          <Button onClick={() => finish(resetGoal(editing, goalProfile))}>Volver al de la EFSA</Button>
        </Sheet>
      )}
    </Screen>
  );
}
