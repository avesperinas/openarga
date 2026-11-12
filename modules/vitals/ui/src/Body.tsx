import { Button, Heading, Hint, SegmentedControl, SeriesChart, Skeleton, StatRow, StatTile, TrendChart } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Figure, type FigureSeries, type HeartDay, Unauthorised, readFigure, readHeartDay, readHeartDays, signIn } from "./api";
import { figureValue, rolling } from "./body";
import { heartSeries, minuteLabel } from "./heart";
import { PERIODS, type Period, dayLabel, monthsBefore } from "./weight";

const CHART = "vitals-figure";

export function FigureChart({ figure }: { figure: Figure }) {
  const [series, setSeries] = useState<FigureSeries | null>(null);
  const [period, setPeriod] = useState<Period>("1y");
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readFigure(figure.id)
      .then(setSeries)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(`No se pudo leer ${figure.name.toLowerCase()}.`);
      });
  }, [figure]);

  const points = series?.points ?? [];
  const last = points[points.length - 1];
  const shown =
    last && period !== "all"
      ? points.filter((one) => one.day > monthsBefore(last.day, period === "3m" ? 3 : 12))
      : points;

  return (
    <section id={CHART} className="surface vitals-card" aria-label={figure.name}>
      <Heading>{figure.name}</Heading>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {series === null && !problem && <Skeleton label={`Cargando ${figure.name.toLowerCase()}`} />}
      {series && (
        <>
          <SegmentedControl
            label="Periodo"
            options={PERIODS.map((one) => ({ value: one.id, label: one.label }))}
            value={period}
            onChange={setPeriod}
          />
          <TrendChart
            label={`${figure.name} en el tiempo`}
            points={rolling(shown, 7, series.figure.changed_on ?? null)}
            valueName="El día"
            averageName="Media de 7 días con dato"
            format={(value) => figureValue(figure, value)}
            formatDay={(day) => dayLabel(day)}
            marker={series.figure.changed_on ? { day: series.figure.changed_on, label: "Cambio a la pulsera" } : null}
          />
          <Hint>
            {series.figure.days} días con dato
            {last ? ` · el último, ${dayLabel(last.day)}` : ""}. {figure.about}
            {series.figure.changed_on ? " Las medias no cruzan el día del cambio." : ""}
          </Hint>
        </>
      )}
    </section>
  );
}

export function HeartDayCard() {
  const [days, setDays] = useState<string[] | null>(null);
  const [at, setAt] = useState(0);
  const [found, setFound] = useState<HeartDay | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readHeartDays()
      .then(setDays)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudo leer el vitals del día.");
      });
  }, []);

  const day = days?.[at];
  useEffect(() => {
    if (!day) return;
    setFound(null);
    readHeartDay(day)
      .then(setFound)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudo leer el vitals del día.");
      });
  }, [day]);

  if (days !== null && days.length === 0) return null;

  return (
    <section className="surface vitals-card" aria-label="El vitals del día">
      <Heading>{day ? `El vitals del ${dayLabel(day)}` : "El vitals del día"}</Heading>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {found === null && !problem && <Skeleton label="Cargando el vitals del día" />}
      {found && (
        <>
          <StatRow label="El día">
            <StatTile label="Más bajo" value={found.min ? `${Math.round(found.min.min)} lpm` : "—"} foot={found.min ? minuteLabel(found.min.minute) : ""} />
            <StatTile label="Más alto" value={found.max ? `${Math.round(found.max.max)} lpm` : "—"} foot={found.max ? minuteLabel(found.max.minute) : ""} />
          </StatRow>
          <SeriesChart
            label={`Vitals del ${dayLabel(found.day)} cada ${found.step} minutos`}
            kind="lines"
            labels={found.buckets.map((one) => minuteLabel(one.minute))}
            series={heartSeries(found.buckets)}
            order={["max", "avg", "min"]}
            format={(value) => `${Math.round(value)} lpm`}
          />
        </>
      )}
      {days && days.length > 1 && (
        <div className="vitals-actions">
          <Button variant="plain" disabled={at >= days.length - 1} onClick={() => setAt(at + 1)}>
            Día anterior
          </Button>
          <Button variant="plain" disabled={at === 0} onClick={() => setAt(at - 1)}>
            Día siguiente
          </Button>
        </div>
      )}
    </section>
  );
}
