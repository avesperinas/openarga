import {
  ChoiceChips,
  EmptyState,
  Heading,
  Hint,
  ratio,
  Screen,
  SegmentedControl,
  SeriesChart,
  Skeleton,
  StatRow,
  StatTile,
  YearCalendar,
} from "@openarga/ui";
import { useTick } from "@openarga/app/fresh";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type StepsSummary, Unauthorised, readSteps, signIn } from "./api";
import { ScreenHeader } from "./Header";
import { CALENDAR_GOAL, type Grain, WEEKDAYS, bucketLabel, count, perBucket, steps, stepsTone, yearEnd, yearsOf } from "./steps";
import { dayLabel } from "./weight";

export function StepsScreen({ onSettings, onBack }: { onSettings: () => void; onBack?: () => void }) {
  const [summary, setSummary] = useState<StepsSummary | null>(null);
  const [problem, setProblem] = useState("");
  const [grain, setGrain] = useState<Grain>("month");
  const [year, setYear] = useState<string>("last");

  const tick = useTick();

  useEffect(() => {
    readSteps()
      .then(setSummary)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        if (tick === 0) setProblem("No se pudieron leer los pasos.");
      });
  }, [tick]);

  const goal = summary?.goal ?? null;
  const buckets = summary ? perBucket(summary.days, grain) : [];
  const years = summary ? yearsOf(summary.days) : [];
  const today = new Date().toISOString().slice(0, 10);
  const end = year === "last" ? summary?.today?.day : yearEnd(year, today);

  return (
    <Screen>
      <ScreenHeader title="Pasos" back={onBack ? { label: "Salud", onClick: onBack } : undefined} />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {summary === null && !problem && <Skeleton label="Cargando los pasos" />}

      {summary && summary.days.length === 0 && (
        <EmptyState title="Todavía no llegan pasos" action={{ label: "Ir a Ajustes", onClick: onSettings }}>
            Llegan de la pulsera por Google Health. En Ajustes está cómo conectarla.
        </EmptyState>
      )}

      {summary && summary.days.length > 0 && (
        <>
          <StatRow label="Cómo van los pasos">
            <StatTile
              label="Hoy"
              value={summary.today ? count(summary.today.steps) : "—"}
              foot={goal ? `de ${count(goal)}` : "Sin objetivo"}
              tone={stepsTone(summary.today?.steps, goal)}
              progress={goal ? ratio(summary.today?.steps ?? 0, goal) : undefined}
            />
            <StatTile
              label="Media de 7 días"
              value={summary.mean_7 === null ? "—" : count(summary.mean_7)}
              foot={goal ? `objetivo ${count(goal)}` : "al día"}
              tone={stepsTone(summary.mean_7, goal)}
            />
            <StatTile
              label="Media de 30 días"
              value={summary.mean_30 === null ? "—" : count(summary.mean_30)}
              foot={goal ? `objetivo ${count(goal)}` : "al día"}
              tone={stepsTone(summary.mean_30, goal)}
            />
          </StatRow>

          <section className="surface vitals-card" aria-label="El año">
            <Heading>{year === "last" ? "El último año" : year}</Heading>
            {years.length > 1 && (
              <ChoiceChips
                label="Año del calendario"
                options={[
                  { value: "last", label: "Último año" },
                  ...years.map((one) => ({ value: one, label: one })),
                ]}
                value={year}
                onChange={setYear}
              />
            )}
            <YearCalendar
              key={year}
              label={year === "last" ? "Pasos de cada día del último año" : `Pasos de cada día de ${year}`}
              days={summary.days.map((one) => ({ day: one.day, value: one.steps }))}
              end={end}
              goal={goal ?? CALENDAR_GOAL}
              format={steps}
            />
          </section>

          <section className="surface vitals-card" aria-label="Por semana, mes o año">
            <SegmentedControl
              label="Agrupar"
              options={[
                { value: "week", label: "Semanas" },
                { value: "month", label: "Meses" },
                { value: "year", label: "Años" },
              ]}
              value={grain}
              onChange={setGrain}
            />
            <SeriesChart
              label={`Media diaria de cada ${grain === "week" ? "semana" : grain === "month" ? "mes" : "año"}`}
              labels={buckets.map((one) => bucketLabel(one.start, grain))}
              series={[{ key: "steps", name: "Media diaria", values: buckets.map((one) => Math.round(one.mean)) }]}
              kind="bars"
              format={steps}
              axisFormat={count}
            />
          </section>

          <StatRow label="Lo mejor">
            <StatTile
              label="Mejor día"
              value={summary.best ? count(summary.best.steps) : "—"}
              foot={summary.best ? dayLabel(summary.best.day) : undefined}
            />
            <StatTile
              label="Racha"
              value={goal ? `${summary.streak} ${summary.streak === 1 ? "día" : "días"}` : "—"}
              foot={goal ? `seguidos sobre ${count(goal)}` : "Pon un objetivo en Ajustes"}
              tone={summary.streak > 0 ? "positive" : "neutral"}
            />
          </StatRow>

          <section className="surface vitals-card" aria-label="Por día de la semana">
            <Heading>Cada día de la semana</Heading>
            <SeriesChart
              label="Media de pasos de cada día de la semana"
              labels={WEEKDAYS}
              series={[{ key: "steps", name: "Media", values: summary.by_weekday.map((one) => one ?? 0) }]}
              kind="bars"
              format={steps}
              axisFormat={count}
            />
          </section>

          {summary.last_received && (
            <Hint>
              Último dato recibido: {new Date(summary.last_received).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: "short" })}
            </Hint>
          )}
        </>
      )}
      <AppVersion />
    </Screen>
  );
}
