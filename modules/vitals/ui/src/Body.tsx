import {
  Button,
  Heading,
  Hint,
  SegmentedControl,
  SeriesChart,
  Skeleton,
  StatRow,
  StatTile,
  TrendChart,
  useLocale,
  useT,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Figure, type FigureSeries, type HeartDay, Unauthorised, readFigure, readHeartDay, readHeartDays, signIn } from "./api";
import { figureAbout, figureName, figureValue, rolling } from "./body";
import { heartSeries, minuteLabel } from "./heart";
import { type Period, dayLabel, monthsBefore, periods } from "./weight";

const CHART = "vitals-figure";

export function FigureChart({ figure }: { figure: Figure }) {
  const t = useT();
  const locale = useLocale();
  const name = figureName(t, figure);
  const [series, setSeries] = useState<FigureSeries | null>(null);
  const [period, setPeriod] = useState<Period>("1y");
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readFigure(figure.id)
      .then(setSeries)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("figure.read_named_failed", { name: name.toLowerCase() }));
      });
  }, [figure, name, t]);

  const points = series?.points ?? [];
  const last = points[points.length - 1];
  const shown =
    last && period !== "all"
      ? points.filter((one) => one.day > monthsBefore(last.day, period === "3m" ? 3 : 12))
      : points;

  return (
    <section id={CHART} className="surface vitals-card" aria-label={name}>
      <Heading>{name}</Heading>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {series === null && !problem && <Skeleton label={t("figure.loading_named", { name: name.toLowerCase() })} />}
      {series && (
        <>
          <SegmentedControl
            label={t("figure.period")}
            options={periods(t).map((one) => ({ value: one.id, label: one.label }))}
            value={period}
            onChange={setPeriod}
          />
          <TrendChart
            label={t("figure.over_time", { name })}
            points={rolling(shown, 7, series.figure.changed_on ?? null)}
            valueName={t("figure.the_day")}
            averageName={t("figure.mean_7_with_data")}
            format={(value) => figureValue(figure, value, t, locale)}
            formatDay={(day) => dayLabel(day, locale)}
            marker={series.figure.changed_on ? { day: series.figure.changed_on, label: t("figure.switch_to_band") } : null}
          />
          <Hint>
            {t("figure.days_with_data", { count: series.figure.days })}
            {last ? ` · ${t("figure.the_last", { day: dayLabel(last.day, locale) })}` : ""}. {figureAbout(t, figure)}
            {series.figure.changed_on ? ` ${t("figure.no_crossing")}` : ""}
          </Hint>
        </>
      )}
    </section>
  );
}

export function HeartDayCard() {
  const t = useT();
  const locale = useLocale();
  const [days, setDays] = useState<string[] | null>(null);
  const [at, setAt] = useState(0);
  const [found, setFound] = useState<HeartDay | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readHeartDays()
      .then(setDays)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("heartday.read_failed"));
      });
  }, [t]);

  const day = days?.[at];
  useEffect(() => {
    if (!day) return;
    setFound(null);
    readHeartDay(day)
      .then(setFound)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("heartday.read_failed"));
      });
  }, [day, t]);

  if (days !== null && days.length === 0) return null;

  return (
    <section className="surface vitals-card" aria-label={t("heartday.title")}>
      <Heading>{day ? t("heartday.of", { day: dayLabel(day, locale) }) : t("heartday.title")}</Heading>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {found === null && !problem && <Skeleton label={t("heartday.loading")} />}
      {found && (
        <>
          <StatRow label={t("figure.the_day")}>
            <StatTile
              label={t("heartday.lowest")}
              value={found.min ? t("common.bpm", { value: Math.round(found.min.min) }) : "—"}
              foot={found.min ? minuteLabel(found.min.minute) : ""}
            />
            <StatTile
              label={t("heartday.highest")}
              value={found.max ? t("common.bpm", { value: Math.round(found.max.max) }) : "—"}
              foot={found.max ? minuteLabel(found.max.minute) : ""}
            />
          </StatRow>
          <SeriesChart
            label={t("heartday.chart", { day: dayLabel(found.day, locale), step: found.step })}
            kind="lines"
            labels={found.buckets.map((one) => minuteLabel(one.minute))}
            series={heartSeries(found.buckets, t)}
            order={["max", "avg", "min"]}
            format={(value) => t("common.bpm", { value: Math.round(value) })}
          />
        </>
      )}
      {days && days.length > 1 && (
        <div className="vitals-actions">
          <Button variant="plain" disabled={at >= days.length - 1} onClick={() => setAt(at + 1)}>
            {t("heartday.previous")}
          </Button>
          <Button variant="plain" disabled={at === 0} onClick={() => setAt(at - 1)}>
            {t("heartday.next")}
          </Button>
        </div>
      )}
    </section>
  );
}
