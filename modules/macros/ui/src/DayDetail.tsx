import {
  Card,
  GroupLabel,
  Hint,
  List,
  ListRow,
  Notice,
  PartBars,
  RangeBar,
  RingFigure,
  Sheet,
  Skeleton,
  SplitBar,
  WidgetBars,
  WidgetChart,
  type Translate,
  useT,
} from "@openarga/ui";
import { useState } from "react";

import { type Contributors, type Day, type GoalState, type NutrientGroup, Unauthorised, readContributors, signIn } from "./api";
import { amount, clockOf, drinksLine, timeOf } from "./words";

const FRONT = ["kcal", "protein", "carbs", "fat", "fiber", "sugars", "saturated_fat", "sodium"];

export function figure(value: number | null, unit: string): string {
  if (value === null) return "—";
  return `${amount(value, value >= 100 || unit === "kcal" ? 0 : 1)} ${unit}`;
}

export function goalDetail(goal: Pick<GoalState, "basis" | "min" | "max" | "unit" | "share">, t: Translate): string {
  const unit = goal.basis === "kcal_pct" ? t("goal.pct_unit") : goal.unit;
  const digits = goal.basis === "kcal_pct" || goal.unit === "kcal" ? 0 : 1;
  const one = (value: number) => amount(value, digits);
  let range = "";
  if (goal.min !== null && goal.max !== null) range = `${one(goal.min)} – ${one(goal.max)} ${unit}`;
  else if (goal.min !== null) range = `≥ ${one(goal.min)} ${unit}`;
  else if (goal.max !== null) range = `≤ ${one(goal.max)} ${unit}`;
  if (goal.basis === "kcal_pct" && goal.share !== null) return `${range} · ${t("goal.at_share", { pct: amount(goal.share, 1) })}`;
  return range;
}

export function coverageNote(coverage: number | null, t: Translate): string | undefined {
  if (coverage === null || coverage >= 0.8) return undefined;
  return t("coverage.missing", { pct: Math.round((1 - coverage) * 100) });
}

export function hourly(day: Day): { series: number[]; labels: string[] } {
  const byHour = new Map<number, number>();
  for (const entry of day.entries) {
    const hour = Number(clockOf(entry.eaten_at).slice(0, 2));
    byHour.set(hour, (byHour.get(hour) ?? 0) + (entry.nutrients.kcal ?? 0));
  }
  if (byHour.size === 0) return { series: [], labels: [] };
  const hours = [...byHour.keys()];
  const first = Math.min(...hours);
  const last = Math.max(...hours);
  const series: number[] = [];
  const labels: string[] = [];
  for (let hour = first; hour <= last; hour += 1) {
    series.push(Math.round(byHour.get(hour) ?? 0));
    labels.push(`${hour}h`);
  }
  return { series, labels };
}

export function DayDetail({ day, only }: { day: Day; only?: "goals" | "detail" | "hours" | "groups" }) {
  const t = useT();
  const [asking, setAsking] = useState<string | null>(null);
  const [found, setFound] = useState<Contributors | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = (nutrient: string) => {
    setAsking(nutrient);
    setFound(null);
    setError(null);
    readContributors(day.day, nutrient)
      .then(setFound)
      .catch((reason: unknown) => {
        if (reason instanceof Unauthorised) return signIn();
        setError(reason instanceof Error ? reason.message : t("common.load_failed"));
      });
  };

  const goals = day.goals ?? [];
  const front = FRONT.map((key) => goals.find((one) => one.nutrient === key)).filter(
    (one): one is GoalState => one !== undefined,
  );
  const timeline = hourly(day);
  const caffeine = day.caffeine;

  return (
    <>
      {(only === undefined || only === "goals") && front.length > 0 && (
        <section className="macros-panel macros-goals" aria-label={t("day.goals")}>
          <GroupLabel>{t("day.goals")}</GroupLabel>
          <div className="macros-bars">
            {front.map((goal) => (
              <RangeBar
                key={goal.nutrient}
                label={goal.name}
                value={goal.value}
                unit={goal.unit}
                figure={figure(goal.value, goal.unit)}
                low={goal.low}
                high={goal.high}
                state={goal.status}
                detail={[goalDetail(goal, t), coverageNote(goal.coverage, t)].filter(Boolean).join(" · ")}
                partial={goal.coverage !== null && goal.coverage < 0.8}
                onOpen={() => ask(goal.nutrient)}
              />
            ))}
          </div>
        </section>
      )}

      {(only === undefined || only === "detail" || only === "hours") && timeline.series.length > 1 && (
        <section className="surface macros-panel" aria-label={t("day.by_hour")}>
          <GroupLabel>{t("day.by_hour")}</GroupLabel>
          <WidgetBars series={timeline.series} labels={timeline.labels} unit="kcal" />
        </section>
      )}

      {(only === undefined || only === "detail" || only === "hours") && caffeine && caffeine.total_mg > 0 && (
        <section className="surface macros-panel" aria-label={t("day.caffeine")}>
          <GroupLabel>{t("day.caffeine")}</GroupLabel>
          <WidgetChart
            series={caffeine.curve.map((point) => point.mg)}
            value={Math.round(caffeine.now_mg)}
            unit={t("caffeine.now_unit")}
            detail={`${t("caffeine.day_total", { mg: amount(caffeine.total_mg, 0) })}${
              caffeine.last_at ? ` · ${t("caffeine.last_at", { at: timeOf(caffeine.last_at) })}` : ""
            }`}
          />
          <Hint>{t("caffeine.half_life", { hours: amount(caffeine.half_life_h, 0) })}</Hint>
        </section>
      )}

      {(only === undefined || only === "detail" || only === "groups") &&
        (day.groups ?? []).map((group) => <GroupSection key={group.key} group={group} onOpen={ask} />)}

      {asking && (
        <Sheet title={found?.name ?? t("contributors.title")} onClose={() => setAsking(null)}>
          {error && <Notice tone="warning">{error}</Notice>}
          {!found && !error && <Skeleton rows={3} />}
          {found && (
            <>
              <Hint>
                {found.total === null
                  ? t("contributors.none")
                  : t("contributors.total", { value: figure(found.total, found.unit) })}
                {coverageNote(found.coverage, t) ? ` ${coverageNote(found.coverage, t)}.` : ""}
              </Hint>
              <List>
                {found.items.map((one) => (
                  <ListRow
                    key={one.name}
                    title={one.name}
                    subtitle={one.times > 1 ? t("contributors.times", { count: one.times }) : undefined}
                    value={`${figure(one.value, found.unit)} · ${amount(one.share, 0)} %`}
                  />
                ))}
              </List>
              {found.without.length > 0 && <Hint>{t("contributors.without", { names: found.without.join(", ") })}</Hint>}
            </>
          )}
        </Sheet>
      )}
    </>
  );
}

function GroupSection({ group, onOpen }: { group: NutrientGroup; onOpen: (key: string) => void }) {
  const t = useT();
  const shown = group.items.filter((item) => item.value !== null);
  const unknown = group.items.filter((item) => item.value === null && (item.min !== null || item.max !== null));
  if (shown.length === 0 && unknown.length === 0) return null;
  return (
    <section className="macros-panel macros-group" aria-label={group.name}>
      <GroupLabel>{group.name}</GroupLabel>
      {unknown.length > 0 && (
        <Hint>{t("group.unknown", { names: unknown.map((item) => item.name).join(", ") })}</Hint>
      )}
      <div className="macros-bars">
        {shown.map((item) => (
          <RangeBar
            key={item.key}
            label={item.name}
            value={item.value}
            unit={item.unit}
            figure={figure(item.value, item.unit)}
            low={item.goal_unit === "amount" ? item.min : null}
            high={item.goal_unit === "amount" ? item.max : null}
            state={item.status}
            detail={[
              item.goal_unit
                ? goalDetail({ basis: item.goal_unit, min: item.min, max: item.max, unit: item.unit, share: null }, t)
                : "",
              coverageNote(item.coverage, t),
            ]
              .filter(Boolean)
              .join(" · ")}
            partial={item.partial}
            onOpen={() => onOpen(item.key)}
          />
        ))}
      </div>
    </section>
  );
}

export function kcalLine(eaten: number, target: number | null, t: Translate, planned = 0): string {
  const with_ = amount(eaten + planned, 0);
  if (target === null) return planned > 0 ? t("kcal.planned", { value: with_ }) : t("kcal.no_goal");
  const of = amount(target, 0);
  if (planned > 0) return t("kcal.planned_of", { value: with_, target: of });
  const left = target - eaten;
  return t(left >= 0 ? "kcal.left_of" : "kcal.over_of", { value: amount(Math.abs(left), 0), target: of });
}

const KCAL_PER_GRAM = { protein: 4, carbs: 4, fat: 9 } as const;

export function macroParts(day: Pick<Day, "nutrients" | "target">, t: Translate) {
  const kcal = day.nutrients.kcal ?? 0;
  const one = (label: string, key: "protein" | "carbs" | "fat") => {
    const eaten = day.nutrients[key] ?? 0;
    const target = day.target?.[key] ?? null;
    if (target) return { label, value: `${amount(eaten, 0)} / ${amount(target, 0)} g`, share: eaten / target };
    const pct = kcal > 0 ? (eaten * KCAL_PER_GRAM[key] * 100) / kcal : 0;
    return { label, value: t("macro.grams_share", { grams: amount(eaten, 0), pct: amount(pct, 0) }), share: pct / 100 };
  };
  return [one(t("nutrient.protein"), "protein"), one(t("nutrient.carbs"), "carbs"), one(t("nutrient.fat"), "fat")];
}

const MEAL_HUE: Record<string, 1 | 2 | 3 | 4 | 5 | 6> = {
  breakfast: 3,
  morning: 4,
  lunch: 2,
  snack: 6,
  dinner: 1,
  night: 5,
};

export function mealParts(day: Pick<Day, "meals" | "target" | "planned">, t: Translate) {
  const parts = day.meals
    .filter((meal) => meal.kcal > 0)
    .map((meal) => ({ label: meal.label, value: amount(meal.kcal, 0), share: meal.kcal, hue: MEAL_HUE[meal.meal] ?? 8 }));
  const planned = (day.planned ?? []).reduce((sum, entry) => sum + (entry.nutrients.kcal ?? 0), 0);
  if (planned > 0) parts.push({ label: t("day.planned"), value: amount(planned, 0), share: planned, hue: 7 });
  const eaten = parts.reduce((sum, part) => sum + part.share, 0);
  const target = day.target?.kcal ?? null;
  const rest = target !== null && target > eaten ? { label: t("day.left"), value: amount(target - eaten, 0), share: target - eaten } : undefined;
  return { parts: parts as { label: string; value: string; share: number; hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 }[], rest };
}

export function DaySummary({ day }: { day: Day }) {
  const t = useT();
  const eaten = day.nutrients.kcal ?? 0;
  const target = day.target?.kcal ?? null;
  const planned = (day.planned ?? []).reduce((sum, entry) => sum + (entry.nutrients.kcal ?? 0), 0);
  const drinks = drinksLine(day.drinks, t);
  const meals = mealParts(day, t);
  return (
    <Card>
      <RingFigure
        share={target ? eaten / target : null}
        planned={target && planned > 0 ? (eaten + planned) / target : null}
        value={amount(eaten, 0)}
        label={target ? t("kcal.of_target", { target: amount(target, 0) }) : "kcal"}
        detail={kcalLine(eaten, target, t, planned)}
        tone={target !== null && eaten > target ? "warning" : undefined}
      />
      <PartBars label="Macros" parts={macroParts(day, t)} />
      {meals.parts.length > 0 && (
        <>
          <GroupLabel>{t("day.by_meal")}</GroupLabel>
          <SplitBar label={t("day.kcal_by_meal")} parts={meals.parts} rest={meals.rest} />
        </>
      )}
      {day.day_kind?.kind === "training" && <Hint>{t("day.training")}</Hint>}
      {drinks && <Hint>{drinks}</Hint>}
    </Card>
  );
}
