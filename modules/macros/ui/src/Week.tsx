import {
  Card,
  Columns,
  CoverageList,
  EmptyState,
  ErrorState,
  Figures,
  GroupLabel,
  Hint,
  List,
  ListRow,
  Notice,
  OfflineNotice,
  Screen,
  SegmentedControl,
  Sheet,
  Skeleton,
  Switch,
  TrendChart,
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import {
  type Contributors,
  type Suggestions,
  type Trend,
  type Week,
  Unauthorised,
  readDay,
  readSuggestions,
  readTrend,
  readWeek,
  readWeekContributors,
  signIn,
} from "./api";
import { coverageNote, figure } from "./DayDetail";
import { coverageGroups, daysNear, energyLine, kcalTrend, windowLine } from "./eating";
import { ExpenditureCard } from "./Expenditure";
import { ScreenHeader } from "./Header";
import { amount, shiftDay, todayIso } from "./words";

const wide = () => typeof window !== "undefined" && window.matchMedia("(min-width: 1100px)").matches;

export function WeekScreen({ onAdd }: { onAdd?: () => void }) {
  const [found, setFound] = useState<Week | null>(null);
  const [trend, setTrend] = useState<Trend | null>(null);
  const [tips, setTips] = useState<Suggestions | null>(null);
  const [all, setAll] = useState(false);
  const [span, setSpan] = useState<"4" | "8">(wide() ? "8" : "4");
  const [asking, setAsking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const today = todayIso();
    readDay(today)
      .then((day) => (day.complete ? today : shiftDay(today, -1)))
      .catch(() => shiftDay(today, -1))
      .then((last) => {
        readTrend(last, 8).then(setTrend).catch(() => setTrend(null));
        readSuggestions(last).then(setTips).catch(() => setTips(null));
        return readWeek(last, all);
      })
      .then((next) => {
        setFound(next);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (reason instanceof Unauthorised) return signIn();
        setError(reason instanceof Error ? reason.message : "No se ha podido cargar la semana");
      });
  }, [all]);

  useEffect(load, [load]);

  const kcalGoal = (found?.goals ?? []).find((goal) => goal.nutrient === "kcal");
  const low = kcalGoal?.min ?? null;
  const high = kcalGoal?.max ?? null;
  const aim = low !== null && high !== null ? (low + high) / 2 : (high ?? low);
  const average = found?.averages.kcal ?? null;
  const near = found ? daysNear(found, aim) : null;
  const groups = found ? coverageGroups(found, trend, setAsking) : [];
  const points = trend ? kcalTrend(trend, Number(span)) : [];

  return (
    <Screen wide>
      <ScreenHeader eyebrow={found ? windowLine(found) : undefined} title="Cómo comes" />
      <OfflineNotice />
      {!found && error ? (
        <ErrorState title="Macros no contesta" detail={error} onRetry={load} />
      ) : !found ? (
        <Skeleton rows={6} />
      ) : found.days_logged === 0 ? (
        <EmptyState
          icon="chart"
          hue={4}
          title="Nada apuntado esta semana"
          action={onAdd ? { label: "Apuntar", icon: "plus", onClick: onAdd } : undefined}
        >
          <p>La semana sale en cuanto haya algo apuntado.</p>
        </EmptyState>
      ) : (
        <>
          {found.counted && !found.counted.complete && (
            <Notice tone="info">
              Pocos días marcados como completos: cuentan los {found.counted.days} con algo apuntado.
            </Notice>
          )}
          <Card>
            <GroupLabel>Energía</GroupLabel>
            <Figures
              label="La energía de la semana"
              items={[
                { label: "kcal de media", value: average === null ? "—" : amount(average, 0) },
                { label: "objetivo", value: aim ? amount(aim, 0) : "—" },
                ...(near && aim ? [{ label: "días cerca", value: `${near.near} de ${near.of}` }] : []),
              ]}
            />
            <SegmentedControl
              label="Cuánto se ve"
              options={[
                { value: "4", label: "4 semanas" },
                { value: "8", label: "8 semanas" },
              ]}
              value={span}
              onChange={setSpan}
            />
            {points.length > 1 ? (
              <TrendChart
                label="Las kcal de cada día completo, con su media de 7 y la banda del objetivo"
                points={points}
                band={aim ? { low: aim * 0.9, high: aim * 1.1 } : null}
                bandName="Cerca del objetivo"
                valueName="Día completo"
                averageName="Media de 7 días"
                format={(value) => `${amount(value, 0)} kcal`}
              />
            ) : (
              <Hint>La tendencia sale con unos días completos más.</Hint>
            )}
            <Hint>{energyLine(average, low, high, found)}</Hint>
          </Card>

          <Columns count={2} stack>
            <Card>
              <GroupLabel>Cómo comes</GroupLabel>
              {!found.profile.from_health && <Hint>Sin ficha de Apple Salud: se compara con un adulto de 30 a 59 años.</Hint>}
              {groups.map((group) => (
                <div key={group.key} className="macros-coverage-group">
                  <GroupLabel count={group.items.length} tone={group.key === "caution" ? "warning" : undefined}>
                    {group.title}
                  </GroupLabel>
                  <CoverageList label={group.title} items={group.items} />
                </div>
              ))}
              <div className="macros-switch">
                <span>Ver todos los micros</span>
                <Switch label="Ver todos los micros" checked={all} onChange={setAll} />
              </div>
            </Card>
            <Improve tips={tips} onAdd={onAdd} />
          </Columns>

          {found.expenditure && <ExpenditureCard found={found.expenditure} kcalGoal={high} onChanged={load} />}
        </>
      )}
      {asking && found && <WeekContributors last={found.last} nutrient={asking} onClose={() => setAsking(null)} />}
    </Screen>
  );
}

function Improve({ tips, onAdd }: { tips: Suggestions | null; onAdd?: () => void }) {
  if (!tips) return null;
  return (
    <Card>
      <GroupLabel>Para mejorar</GroupLabel>
      {tips.nutrients.length === 0 ? (
        <EmptyState icon="done" hue={2} title="Esta semana cubres todo lo que se mide.">
          <p>Bien.</p>
        </EmptyState>
      ) : (
        tips.nutrients.map((nutrient) => (
          <div key={nutrient.key} className="macros-coverage-group">
            <GroupLabel>{`${nutrient.name} · ${amount(nutrient.average, nutrient.average >= 10 ? 0 : 1)} de ${amount(nutrient.reference, nutrient.reference >= 10 ? 0 : 1)} ${nutrient.unit} al día`}</GroupLabel>
            {nutrient.foods.length === 0 ? (
              <Hint>Nada de lo que sueles comer aporta mucho {nutrient.name.toLowerCase()}. Pregúntale a Claude qué añadir.</Hint>
            ) : (
              <List>
                {nutrient.foods.map((food) => (
                  <ListRow
                    key={food.food_id ?? food.recipe_id ?? food.name}
                    title={food.name}
                    subtitle={`${food.portion} · ${sinceLabel(food.last_eaten)}`}
                    value={`+${amount(food.amount, food.amount >= 10 ? 0 : 1)} ${nutrient.unit}`}
                    onClick={onAdd}
                  />
                ))}
              </List>
            )}
          </div>
        ))
      )}
      <Hint>Sale de lo que has comido en los últimos 60 días. Claude te lo explica si se lo preguntas.</Hint>
    </Card>
  );
}

export function sinceLabel(day: string, now: Date = new Date()): string {
  const days = Math.round((now.getTime() - new Date(`${day}T12:00:00`).getTime()) / 86_400_000);
  if (days <= 0) return "hoy";
  if (days === 1) return "ayer";
  return `hace ${days} días`;
}

function WeekContributors({ last, nutrient, onClose }: { last: string; nutrient: string; onClose: () => void }) {
  const [found, setFound] = useState<Contributors | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    readWeekContributors(last, nutrient)
      .then(setFound)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "No se ha podido cargar"));
  }, [last, nutrient]);
  return (
    <Sheet title={found?.name ?? "Quién lo aporta"} onClose={onClose}>
      {error && <Notice tone="warning">{error}</Notice>}
      {!found && !error && <Skeleton rows={3} />}
      {found && (
        <>
          <Hint>
            {found.total === null ? "Nada de lo comido trae este dato." : `${figure(found.total, found.unit)} en la semana.`}
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
        </>
      )}
    </Sheet>
  );
}
