import { Hint, InfoHeading, KeyFigures, Screen, Skeleton, useLocale, useT } from "@openarga/ui";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type BodyOverview, type FigureSeries, Unauthorised, readBody, readFigure, readProfile, signIn } from "./api";
import { FigureChart, HeartDayCard } from "./Body";
import { figureAbout, figureName, figureValue } from "./body";
import { ScreenHeader } from "./Header";
import { heartSummary } from "./heart";
import { RhythmCard } from "./Rhythm";

const LOWER_IS_BEST = new Set(["resting_heart_rate", "walking_heart_rate"]);
const WITH_BEST = new Set(["resting_heart_rate", "hrv_ms", "vo2max", "walking_heart_rate"]);

export function FigureScreen({ id, onBack }: { id: string; onBack: () => void }) {
  const t = useT();
  const locale = useLocale();
  const [overview, setOverview] = useState<BodyOverview | null>(null);
  const [series, setSeries] = useState<FigureSeries | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readBody()
      .then(setOverview)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("figure.read_failed"));
      });
    readFigure(id).then(setSeries).catch(() => setSeries(null));
  }, [id, t]);

  const figure = overview?.sections.flatMap((one) => one.figures).find((one) => one.id === id) ?? null;
  const summary = series ? heartSummary(series, LOWER_IS_BEST.has(id), t, locale) : null;
  const name = figure ? figureName(t, figure) : t("figure.title");

  return (
    <Screen>
      <ScreenHeader title={name} back={{ label: t("tabs.health"), onClick: onBack }} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {overview === null && !problem && <Skeleton label={t("heart.loading")} />}
      {overview && !figure && <Hint>{t("figure.unknown")}</Hint>}
      {figure && (
        <section className="surface vitals-card" aria-label={t("figure.what_is", { name })}>
          <InfoHeading info={figureAbout(t, figure)}>{t("figure.in_figures")}</InfoHeading>
          <KeyFigures
            label={name}
            items={[
              {
                label: t("figure.last"),
                value: figure.latest ? figureValue(figure, figure.latest.value, t, locale) : "—",
                foot: figure.latest ? new Date(`${figure.latest.day}T12:00:00`).toLocaleDateString(locale) : undefined,
              },
              ...(summary
                ? [
                    { label: t("figure.now_7"), value: summary.now },
                    { label: t("heart.month_ago"), value: summary.month, foot: summary.change },
                  ]
                : []),
              { label: t("figure.mean_30_label"), value: figure.mean_30 !== null ? figureValue(figure, figure.mean_30, t, locale) : "—" },
              { label: t("figure.mean_year_label"), value: figure.mean_365 !== null ? figureValue(figure, figure.mean_365, t, locale) : "—" },
              ...(summary && WITH_BEST.has(id) ? [{ label: summary.bestLabel, value: summary.best, foot: summary.bestDay }] : []),
              { label: t("figure.days"), value: String(figure.days) },
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
  const t = useT();
  return (
    <Screen>
      <ScreenHeader title={t("figure.heart_each_day")} back={{ label: t("tabs.health"), onClick: onBack }} />
      <HeartDayCard />
      <AppVersion />
    </Screen>
  );
}

export function RhythmScreen({ onBack }: { onBack: () => void }) {
  const t = useT();
  const [alertsEnabled, setAlertsEnabled] = useState<boolean | null>(null);
  useEffect(() => {
    readProfile()
      .then((profile) => setAlertsEnabled(profile?.irn_enrolled ?? null))
      .catch(() => setAlertsEnabled(null));
  }, []);
  return (
    <Screen>
      <ScreenHeader title={t("rhythm.title")} back={{ label: t("tabs.health"), onClick: onBack }} />
      <RhythmCard alertsEnabled={alertsEnabled} />
      <AppVersion />
    </Screen>
  );
}
