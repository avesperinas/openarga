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
  type Translate,
  dates,
  useT,
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

const FIELDS = ["kcal", "protein", "carbs", "fat"] as const;

const SHARES = new Set([
  "protein", "carbs", "fat", "fiber", "sugars", "added_sugars", "starch", "saturated_fat",
  "monounsaturated_fat", "polyunsaturated_fat", "trans_fat", "alcohol",
]);

function parsed(text: string): number | null {
  const value = Number(text.replace(",", "."));
  return text.trim() && Number.isFinite(value) && value >= 0 ? value : null;
}

export function referenceLabel(reference: Reference, unit: string, t: Translate): string {
  if (reference.kind === "energy_share") return t("reference.share_cap", { pct: amount(reference.value * 100, 0) });
  return `${amount(reference.value)} ${unit} ${t(`reference.${reference.kind}`)}`;
}

const PROFILES = ["any", "training", "rest"] as const;

const source = (t: Translate, key: GoalInfo["source"]) => (key === "efsa" ? "EFSA" : t("goal.yours"));

export const PER_KG = new Set(["kcal", "protein", "carbs", "fat"]);

export function goalLabel(
  goal: Pick<GoalInfo, "min" | "max" | "unit" | "nutrient_unit" | "kg" | "amount">,
  t: Translate,
): string {
  if (goal.unit === "per_kg") {
    const said = goalLabel({ ...goal, unit: "amount", nutrient_unit: `${goal.nutrient_unit}/kg` }, t);
    const today = goal.amount ? goalLabel({ ...goal.amount, unit: "amount", nutrient_unit: goal.nutrient_unit }, t) : null;
    return today && goal.kg
      ? `${said} · ${t("goal.with_kg", { amount: today.replace(/^[≥≤] /, ""), kg: amount(goal.kg) })}`
      : said;
  }
  const unit = goal.unit === "kcal_pct" ? t("goal.pct_unit") : goal.nutrient_unit;
  const digits = goal.unit === "kcal_pct" ? 0 : undefined;
  const one = (value: number) => amount(value, digits);
  if (goal.min !== null && goal.max !== null) {
    return goal.min === goal.max ? `${one(goal.min)} ${unit}` : `${one(goal.min)} – ${one(goal.max)} ${unit}`;
  }
  if (goal.min !== null) return `≥ ${one(goal.min)} ${unit}`;
  if (goal.max !== null) return `≤ ${one(goal.max)} ${unit}`;
  return t("goal.none");
}

export function dayKindLabel(found: DayKindInfo, t: Translate): string {
  if (found.kind === "rest") return found.source === "manual" ? t("kind.rest_manual") : t("kind.rest");
  if (found.source === "manual") return t("kind.training_manual");
  return t("kind.training", { workouts: found.workouts.join(", ") });
}

export function proteinPerKilo(protein: number | null, kg: number | null, t: Translate): string | null {
  if (!protein || !kg) return null;
  return t("goal.protein_per_kg", { grams: amount(protein / kg, 1) });
}

export function GoalsScreen() {
  const t = useT();
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
          Object.fromEntries(FIELDS.map((key) => [key, found?.[key] == null ? "" : String(found[key])])),
        );
        setReferences(refs.references);
        setProfile(refs.profile);
        setNutrients(list);
      })
      .catch((reason: unknown) => {
        if (reason instanceof Unauthorised) return signIn();
        setError(reason instanceof Error ? reason.message : t("common.load_failed"));
      });
  }, [t]);

  useEffect(load, [load]);

  const save = () => {
    const body = Object.fromEntries(FIELDS.map((key) => [key, parsed(draft[key] ?? "")]));
    saveTarget({ ...body, valid_from: todayIso() })
      .then((saved) => {
        setTarget(saved);
        toast({ message: t("target.saved") });
      })
      .catch((reason: unknown) =>
        toast({ message: reason instanceof Error ? reason.message : t("common.save_failed"), tone: "error" }),
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
        toast({ message: reason instanceof Error ? reason.message : t("common.save_failed"), tone: "error" }),
      );
  const saveEditing = () => {
    if (!editing) return;
    finish(saveGoal(editing, { min: parsed(low), max: parsed(high), unit: goalUnit, profile: goalProfile }));
  };
  const markDay = (next: DayKindInfo["kind"] | null) =>
    void setDayKind(todayIso(), next)
      .then(() => load())
      .catch((reason: unknown) =>
        toast({ message: reason instanceof Error ? reason.message : t("common.save_failed"), tone: "error" }),
      );

  return (
    <Screen>
      <ScreenHeader title={t("tabs.goals")} />
      <OfflineNotice />
      {!references ? (
        error ? (
          <ErrorState
            title={t("common.not_answering")}
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
          <section className="surface macros-panel" aria-label={t("target.title")}>
            <GroupLabel>{t("target.title")}</GroupLabel>
            <div className="macros-fields">
              {FIELDS.map((key) => (
                <TextField
                  key={key}
                  label={t(`target.${key}`)}
                  inputMode="decimal"
                  value={draft[key] ?? ""}
                  onChange={(text) => setDraft((current) => ({ ...current, [key]: text }))}
                />
              ))}
            </div>
            <Hint>
              {target
                ? t("target.since", {
                    day: dates({ day: "numeric", month: "long", year: "numeric" }).format(
                      new Date(`${target.valid_from}T12:00:00`),
                    ),
                  })
                : t("target.none")}{" "}
              {t("target.shortcut")}
            </Hint>
            <Button variant="primary" onClick={save}>
              {t("goal.save_today")}
            </Button>
          </section>

          <BodyWeightCard
            history={weight}
            note={proteinPerKilo(target?.protein ?? null, weight?.latest?.kg ?? null, t) ?? undefined}
            onLog={(kg) =>
              logWeight(kg)
                .then(setWeight)
                .catch((reason: unknown) => {
                  toast({ message: reason instanceof Error ? reason.message : t("weight.log_failed"), tone: "error" });
                  throw reason;
                })
            }
          />

          {kind && (
            <section className="surface macros-panel" aria-label={t("kind.title")}>
              <GroupLabel>{t("kind.title")}</GroupLabel>
              <Hint>
                {dayKindLabel(kind, t)} {t("kind.override")}
              </Hint>
              <ChoiceChips
                label={t("day.today")}
                value={kind.source === "manual" ? kind.kind : "auto"}
                onChange={(next) => markDay(next === "auto" ? null : (next as DayKindInfo["kind"]))}
                options={[
                  { value: "auto", label: t("kind.auto") },
                  { value: "training", label: t("profile.training") },
                  { value: "rest", label: t("profile.rest") },
                ]}
              />
            </section>
          )}

          <section className="surface macros-panel" aria-label={t("goals.title")}>
            <GroupLabel>{t("goals.title")}</GroupLabel>
            <Hint>
              {profile?.from_health
                ? t(profile.age ? "goals.efsa_age" : "goals.efsa", {
                    who: t(`goals.who.${profile.sex === "female" || profile.sex === "male" ? profile.sex : "adult"}`),
                    age: profile.age ?? "",
                  })
                : t("goals.efsa_default")}
            </Hint>
            <List>
              {(goals ?? [])
                .filter((goal) => named.has(goal.nutrient))
                .sort((a, b) => order.indexOf(a.nutrient) - order.indexOf(b.nutrient))
                .map((goal) => (
                  <ListRow
                    key={goal.nutrient}
                    title={goal.name}
                    subtitle={
                      goal.profile === "any"
                        ? source(t, goal.source)
                        : `${source(t, goal.source)}, ${t(`profile.${goal.profile}`).toLowerCase()}`
                    }
                    value={goalLabel(goal, t)}
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
          action={{ label: t("goal.save_today"), onClick: saveEditing, disabled: parsed(low) === null && parsed(high) === null }}
        >
          <ChoiceChips
            label={t("goal.for")}
            value={goalProfile}
            onChange={(next) => setGoalProfile(next as GoalInfo["profile"])}
            options={PROFILES.map((value) => ({ value, label: t(`profile.${value}`) }))}
          />
          {named.get(editing) && (SHARES.has(editing) || PER_KG.has(editing)) && (
            <ChoiceChips
              label={t("goal.in")}
              value={goalUnit}
              onChange={(next) => setGoalUnit(next as GoalInfo["unit"])}
              options={[
                { value: "amount", label: named.get(editing)!.unit },
                ...(SHARES.has(editing) ? [{ value: "kcal_pct", label: t("goal.pct_unit") }] : []),
                ...(PER_KG.has(editing) ? [{ value: "per_kg", label: t("goal.per_kilo", { unit: named.get(editing)!.unit }) }] : []),
              ]}
            />
          )}
          {goalUnit === "per_kg" && (
            <Hint>
              {t("goal.follows_weight", {
                weight: weight?.latest ? t("goal.weight_today", { kg: amount(weight.latest.kg) }) : t("goal.no_weight"),
              })}
            </Hint>
          )}
          <div className="macros-fields">
            <TextField label={t("goal.min")} inputMode="decimal" value={low} onChange={setLow} onSubmit={saveEditing} autoFocus />
            <TextField label={t("goal.max")} inputMode="decimal" value={high} onChange={setHigh} onSubmit={saveEditing} />
          </div>
          <Hint>{t("goal.min_max_hint")}</Hint>
          {editingGoal && (
            <Hint>{t("goal.now", { goal: goalLabel(editingGoal, t), source: source(t, editingGoal.source) })}</Hint>
          )}
          <Button onClick={() => finish(saveGoal(editing, { min: null, max: null, unit: "amount", profile: goalProfile }))}>
            {t("goal.clear")}
          </Button>
          <Button onClick={() => finish(resetGoal(editing, goalProfile))}>{t("goal.reset")}</Button>
        </Sheet>
      )}
    </Screen>
  );
}
