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
} from "@openarga/ui";
import { useState } from "react";

import { type Contributors, type Day, type GoalState, type NutrientGroup, Unauthorised, readContributors, signIn } from "./api";
import { amount, drinksLine, timeOf } from "./words";

const FRONT = ["kcal", "protein", "carbs", "fat", "fiber", "sugars", "saturated_fat", "sodium"];

export function figure(value: number | null, unit: string): string {
  if (value === null) return "—";
  return `${amount(value, value >= 100 || unit === "kcal" ? 0 : 1)} ${unit}`;
}

export function goalDetail(goal: Pick<GoalState, "basis" | "min" | "max" | "unit" | "share">): string {
  const unit = goal.basis === "kcal_pct" ? "% de las kcal" : goal.unit;
  const digits = goal.basis === "kcal_pct" || goal.unit === "kcal" ? 0 : 1;
  const one = (value: number) => amount(value, digits);
  let range = "";
  if (goal.min !== null && goal.max !== null) range = `${one(goal.min)} – ${one(goal.max)} ${unit}`;
  else if (goal.min !== null) range = `≥ ${one(goal.min)} ${unit}`;
  else if (goal.max !== null) range = `≤ ${one(goal.max)} ${unit}`;
  if (goal.basis === "kcal_pct" && goal.share !== null) return `${range} · vas en ${amount(goal.share, 1)} %`;
  return range;
}

export function coverageNote(coverage: number | null): string | undefined {
  if (coverage === null || coverage >= 0.8) return undefined;
  return `Faltan datos del ${Math.round((1 - coverage) * 100)} % de las kcal`;
}

export function hourly(day: Day): { series: number[]; labels: string[] } {
  const byHour = new Map<number, number>();
  for (const entry of day.entries) {
    const hour = Number(timeOf(entry.eaten_at).slice(0, 2));
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
        setError(reason instanceof Error ? reason.message : "No se ha podido cargar");
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
        <section className="macros-panel macros-goals" aria-label="Objetivos del día">
          <GroupLabel>Objetivos del día</GroupLabel>
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
                detail={[goalDetail(goal), coverageNote(goal.coverage)].filter(Boolean).join(" · ")}
                partial={goal.coverage !== null && goal.coverage < 0.8}
                onOpen={() => ask(goal.nutrient)}
              />
            ))}
          </div>
        </section>
      )}

      {(only === undefined || only === "detail" || only === "hours") && timeline.series.length > 1 && (
        <section className="surface macros-panel" aria-label="El día por horas">
          <GroupLabel>El día por horas</GroupLabel>
          <WidgetBars series={timeline.series} labels={timeline.labels} unit="kcal" />
        </section>
      )}

      {(only === undefined || only === "detail" || only === "hours") && caffeine && caffeine.total_mg > 0 && (
        <section className="surface macros-panel" aria-label="Cafeína">
          <GroupLabel>Cafeína</GroupLabel>
          <WidgetChart
            series={caffeine.curve.map((point) => point.mg)}
            value={Math.round(caffeine.now_mg)}
            unit="mg ahora"
            detail={`${amount(caffeine.total_mg, 0)} mg en el día${
              caffeine.last_at ? ` · la última a las ${timeOf(caffeine.last_at)}` : ""
            }`}
          />
          <Hint>Lo que queda en el cuerpo, con una vida media de {amount(caffeine.half_life_h, 0)} h.</Hint>
        </section>
      )}

      {(only === undefined || only === "detail" || only === "groups") &&
        (day.groups ?? []).map((group) => <GroupSection key={group.key} group={group} onOpen={ask} />)}

      {asking && (
        <Sheet title={found?.name ?? "Quién lo aporta"} onClose={() => setAsking(null)}>
          {error && <Notice tone="warning">{error}</Notice>}
          {!found && !error && <Skeleton rows={3} />}
          {found && (
            <>
              <Hint>
                {found.total === null ? "Nada de lo comido trae este dato." : `${figure(found.total, found.unit)} en el día.`}
                {coverageNote(found.coverage) ? ` ${coverageNote(found.coverage)}.` : ""}
              </Hint>
              <List>
                {found.items.map((one) => (
                  <ListRow
                    key={one.name}
                    title={one.name}
                    subtitle={one.times > 1 ? `${one.times} veces` : undefined}
                    value={`${figure(one.value, found.unit)} · ${amount(one.share, 0)} %`}
                  />
                ))}
              </List>
              {found.without.length > 0 && <Hint>Sin el dato: {found.without.join(", ")}.</Hint>}
            </>
          )}
        </Sheet>
      )}
    </>
  );
}

function GroupSection({ group, onOpen }: { group: NutrientGroup; onOpen: (key: string) => void }) {
  const shown = group.items.filter((item) => item.value !== null);
  const unknown = group.items.filter((item) => item.value === null && (item.min !== null || item.max !== null));
  if (shown.length === 0 && unknown.length === 0) return null;
  return (
    <section className="macros-panel macros-group" aria-label={group.name}>
      <GroupLabel>{group.name}</GroupLabel>
      {unknown.length > 0 && (
        <Hint>Sin dato en lo comido (no es un cero): {unknown.map((item) => item.name).join(", ")}.</Hint>
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
                ? goalDetail({ basis: item.goal_unit, min: item.min, max: item.max, unit: item.unit, share: null })
                : "",
              coverageNote(item.coverage),
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

export function kcalLine(eaten: number, target: number | null, planned = 0): string {
  if (target === null) return planned > 0 ? `con lo planificado, ${amount(eaten + planned, 0)}` : "sin objetivo de kcal";
  if (planned > 0) return `con lo planificado, ${amount(eaten + planned, 0)} de ${amount(target, 0)}`;
  const left = target - eaten;
  return left >= 0 ? `quedan ${amount(left, 0)} de ${amount(target, 0)}` : `te pasas ${amount(-left, 0)} de ${amount(target, 0)}`;
}

const KCAL_PER_GRAM = { protein: 4, carbs: 4, fat: 9 } as const;

export function macroParts(day: Pick<Day, "nutrients" | "target">) {
  const kcal = day.nutrients.kcal ?? 0;
  const one = (label: string, key: "protein" | "carbs" | "fat") => {
    const eaten = day.nutrients[key] ?? 0;
    const target = day.target?.[key] ?? null;
    if (target) return { label, value: `${amount(eaten, 0)} / ${amount(target, 0)} g`, share: eaten / target };
    const pct = kcal > 0 ? (eaten * KCAL_PER_GRAM[key] * 100) / kcal : 0;
    return { label, value: `${amount(eaten, 0)} g · ${amount(pct, 0)} % de las kcal`, share: pct / 100 };
  };
  return [one("Proteína", "protein"), one("Hidratos", "carbs"), one("Grasa", "fat")];
}

const MEAL_HUE: Record<string, 1 | 2 | 3 | 4 | 5 | 6> = {
  breakfast: 3,
  morning: 4,
  lunch: 2,
  snack: 6,
  dinner: 1,
  night: 5,
};

export function mealParts(day: Pick<Day, "meals" | "target" | "planned">) {
  const parts = day.meals
    .filter((meal) => meal.kcal > 0)
    .map((meal) => ({ label: meal.label, value: amount(meal.kcal, 0), share: meal.kcal, hue: MEAL_HUE[meal.meal] ?? 8 }));
  const planned = (day.planned ?? []).reduce((sum, entry) => sum + (entry.nutrients.kcal ?? 0), 0);
  if (planned > 0) parts.push({ label: "Planificado", value: amount(planned, 0), share: planned, hue: 7 });
  const eaten = parts.reduce((sum, part) => sum + part.share, 0);
  const target = day.target?.kcal ?? null;
  const rest = target !== null && target > eaten ? { label: "Queda", value: amount(target - eaten, 0), share: target - eaten } : undefined;
  return { parts: parts as { label: string; value: string; share: number; hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 }[], rest };
}

export function DaySummary({ day }: { day: Day }) {
  const eaten = day.nutrients.kcal ?? 0;
  const target = day.target?.kcal ?? null;
  const planned = (day.planned ?? []).reduce((sum, entry) => sum + (entry.nutrients.kcal ?? 0), 0);
  const drinks = drinksLine(day.drinks);
  const meals = mealParts(day);
  return (
    <Card>
      <RingFigure
        share={target ? eaten / target : null}
        planned={target && planned > 0 ? (eaten + planned) / target : null}
        value={amount(eaten, 0)}
        label={target ? `de ${amount(target, 0)} kcal` : "kcal"}
        detail={kcalLine(eaten, target, planned)}
        tone={target !== null && eaten > target ? "warning" : undefined}
      />
      <PartBars label="Macros" parts={macroParts(day)} />
      {meals.parts.length > 0 && (
        <>
          <GroupLabel>Por comidas</GroupLabel>
          <SplitBar label="Las kcal del día por comidas" parts={meals.parts} rest={meals.rest} />
        </>
      )}
      {day.day_kind?.kind === "training" && <Hint>Día de entreno: mandan tus objetivos de entreno.</Hint>}
      {drinks && <Hint>{drinks}</Hint>}
    </Card>
  );
}
