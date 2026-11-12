import { Heading, Hint, SegmentedControl, Skeleton, StatRow, StatTile, TrendChart } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type FigureSeries, readFigure } from "./api";
import { heartSummary } from "./heart";

type Pick = "resting_heart_rate" | "hrv_ms" | "vo2max";

const OPTIONS: { value: Pick; label: string }[] = [
  { value: "resting_heart_rate", label: "FC en reposo" },
  { value: "hrv_ms", label: "VFC" },
  { value: "vo2max", label: "VO₂ máx." },
];

export function HeartTrends() {
  const [picked, setPicked] = useState<Pick>("resting_heart_rate");
  const [found, setFound] = useState<FigureSeries | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    setFound(null);
    setMissing(false);
    readFigure(picked)
      .then(setFound)
      .catch(() => setMissing(true));
  }, [picked]);

  const summary = found ? heartSummary(found, picked === "resting_heart_rate") : null;

  return (
    <section className="surface vitals-card health-figures" aria-label="El corazón en el tiempo">
      <Heading>Corazón</Heading>
      <SegmentedControl label="Qué cifra" options={OPTIONS} value={picked} onChange={setPicked} />
      {!found && !missing && <Skeleton label="Cargando la cifra" />}
      {(missing || (found && !summary)) && <Hint>Todavía no hay datos de esta cifra.</Hint>}
      {found && summary && (
        <>
          <StatRow label={found.figure.name}>
            <StatTile label="Ahora, media de 7" value={summary.now} />
            <StatTile label="Hace un mes" value={summary.month} foot={summary.change} tone={summary.tone} />
            <StatTile label={summary.bestLabel} value={summary.best} foot={summary.bestDay} />
          </StatRow>
          <TrendChart
            label={`${found.figure.name} de los últimos 90 días`}
            points={summary.points}
            valueName={found.figure.name}
            averageName="Media de 7 días"
            format={(value) => `${value.toLocaleString("es-ES", { maximumFractionDigits: found.figure.digits })} ${found.figure.unit}`}
          />
        </>
      )}
    </section>
  );
}
