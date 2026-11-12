import { Hint, InfoHeading, KeyFigures, Screen, Skeleton } from "@openarga/ui";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type BodyOverview, type FigureSeries, Unauthorised, readBody, readFigure, readProfile, signIn } from "./api";
import { FigureChart, HeartDayCard } from "./Body";
import { figureValue } from "./body";
import { ScreenHeader } from "./Header";
import { heartSummary } from "./heart";
import { RhythmCard } from "./Rhythm";

const LOWER_IS_BEST = new Set(["resting_heart_rate", "walking_heart_rate"]);
const WITH_BEST = new Set(["resting_heart_rate", "hrv_ms", "vo2max", "walking_heart_rate"]);

export function FigureScreen({ id, onBack }: { id: string; onBack: () => void }) {
  const [overview, setOverview] = useState<BodyOverview | null>(null);
  const [series, setSeries] = useState<FigureSeries | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readBody()
      .then(setOverview)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudo leer esa cifra.");
      });
    readFigure(id).then(setSeries).catch(() => setSeries(null));
  }, [id]);

  const figure = overview?.sections.flatMap((one) => one.figures).find((one) => one.id === id) ?? null;
  const summary = series ? heartSummary(series, LOWER_IS_BEST.has(id)) : null;

  return (
    <Screen>
      <ScreenHeader title={figure?.name ?? "Cifra"} back={{ label: "Salud", onClick: onBack }} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {overview === null && !problem && <Skeleton label="Cargando la cifra" />}
      {overview && !figure && <Hint>Esta cifra no está entre las que se guardan.</Hint>}
      {figure && (
        <section className="surface vitals-card" aria-label={`Qué es ${figure.name}`}>
          <InfoHeading info={figure.about}>En cifras</InfoHeading>
          <KeyFigures
            label={figure.name}
            items={[
              { label: "Último dato", value: figure.latest ? figureValue(figure, figure.latest.value) : "—", foot: figure.latest ? figure.latest.day.split("-").reverse().join("/") : undefined },
              ...(summary ? [{ label: "Ahora, media de 7 días", value: summary.now }, { label: "Hace un mes", value: summary.month, foot: summary.change }] : []),
              { label: "Media de 30 días", value: figure.mean_30 !== null ? figureValue(figure, figure.mean_30) : "—" },
              { label: "Media del año", value: figure.mean_365 !== null ? figureValue(figure, figure.mean_365) : "—" },
              ...(summary && WITH_BEST.has(id) ? [{ label: summary.bestLabel, value: summary.best, foot: summary.bestDay }] : []),
              { label: "Días con dato", value: String(figure.days) },
            ]}
          />
        </section>
      )}
      {figure && <FigureChart figure={figure} />}
      <AppVersion />
    </Screen>
  );
}

export function HeartDayScreen({ onBack }: { onBack: () => void }) {
  return (
    <Screen>
      <ScreenHeader title="Vitals de cada día" back={{ label: "Salud", onClick: onBack }} />
      <HeartDayCard />
      <AppVersion />
    </Screen>
  );
}

export function RhythmScreen({ onBack }: { onBack: () => void }) {
  const [alertsEnabled, setAlertsEnabled] = useState<boolean | null>(null);
  useEffect(() => {
    readProfile()
      .then((profile) => setAlertsEnabled(profile?.irn_enrolled ?? null))
      .catch(() => setAlertsEnabled(null));
  }, []);
  return (
    <Screen>
      <ScreenHeader title="Ritmo" back={{ label: "Salud", onClick: onBack }} />
      <RhythmCard alertsEnabled={alertsEnabled} />
      <AppVersion />
    </Screen>
  );
}
