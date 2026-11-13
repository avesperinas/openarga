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
  useLocale,
  useT,
} from "@openarga/ui";
import { useTick } from "@openarga/app/fresh";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type StepsSummary, Unauthorised, readSteps, signIn } from "./api";
import { ScreenHeader } from "./Header";
import { CALENDAR_GOAL, type Grain, bucketLabel, count, perBucket, steps, stepsTone, weekdays, yearEnd, yearsOf } from "./steps";
import { dayLabel } from "./weight";
import { plural } from "./words";

export function StepsScreen({ onSettings, onBack }: { onSettings: () => void; onBack?: () => void }) {
  const t = useT();
  const locale = useLocale();
  const asSteps = (value: number) => steps(value, t, locale);
  const asCount = (value: number) => count(value, locale);
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
        if (tick === 0) setProblem(t("steps.read_failed"));
      });
  }, [tick, t]);

  const goal = summary?.goal ?? null;
  const buckets = summary ? perBucket(summary.days, grain) : [];
  const years = summary ? yearsOf(summary.days) : [];
  const today = new Date().toISOString().slice(0, 10);
  const end = year === "last" ? summary?.today?.day : yearEnd(year, today);

  return (
    <Screen>
      <ScreenHeader title={t("steps.title")} back={onBack ? { label: t("tabs.health"), onClick: onBack } : undefined} />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {summary === null && !problem && <Skeleton label={t("steps.loading")} />}

      {summary && summary.days.length === 0 && (
        <EmptyState title={t("steps.none_title")} action={{ label: t("common.to_settings"), onClick: onSettings }}>
          {t("steps.none_text")}
        </EmptyState>
      )}

      {summary && summary.days.length > 0 && (
        <>
          <StatRow label={t("steps.how")}>
            <StatTile
              label={t("tabs.today")}
              value={summary.today ? asCount(summary.today.steps) : "—"}
              foot={goal ? t("steps.of", { goal: asCount(goal) }) : t("goal.none")}
              tone={stepsTone(summary.today?.steps, goal)}
              progress={goal ? ratio(summary.today?.steps ?? 0, goal) : undefined}
            />
            <StatTile
              label={t("heart.mean_7")}
              value={summary.mean_7 === null ? "—" : asCount(summary.mean_7)}
              foot={goal ? t("steps.goal", { goal: asCount(goal) }) : t("steps.per_day")}
              tone={stepsTone(summary.mean_7, goal)}
            />
            <StatTile
              label={t("figure.mean_30_label")}
              value={summary.mean_30 === null ? "—" : asCount(summary.mean_30)}
              foot={goal ? t("steps.goal", { goal: asCount(goal) }) : t("steps.per_day")}
              tone={stepsTone(summary.mean_30, goal)}
            />
          </StatRow>

          <section className="surface vitals-card" aria-label={t("steps.the_year")}>
            <Heading>{year === "last" ? t("steps.last_year") : year}</Heading>
            {years.length > 1 && (
              <ChoiceChips
                label={t("steps.calendar_year")}
                options={[
                  { value: "last", label: t("steps.last_year_chip") },
                  ...years.map((one) => ({ value: one, label: one })),
                ]}
                value={year}
                onChange={setYear}
              />
            )}
            <YearCalendar
              key={year}
              label={year === "last" ? t("steps.each_day_last_year") : t("steps.each_day_of", { year })}
              days={summary.days.map((one) => ({ day: one.day, value: one.steps }))}
              end={end}
              goal={goal ?? CALENDAR_GOAL}
              format={asSteps}
            />
          </section>

          <section className="surface vitals-card" aria-label={t("steps.by_grain")}>
            <SegmentedControl
              label={t("steps.group")}
              options={[
                { value: "week", label: t("steps.weeks") },
                { value: "month", label: t("steps.months") },
                { value: "year", label: t("steps.years") },
              ]}
              value={grain}
              onChange={setGrain}
            />
            <SeriesChart
              label={t(`steps.daily_mean_of.${grain}`)}
              labels={buckets.map((one) => bucketLabel(one.start, grain, locale))}
              series={[{ key: "steps", name: t("steps.daily_mean"), values: buckets.map((one) => Math.round(one.mean)) }]}
              kind="bars"
              format={asSteps}
              axisFormat={asCount}
            />
          </section>

          <StatRow label={t("steps.best")}>
            <StatTile
              label={t("steps.best_day")}
              value={summary.best ? asCount(summary.best.steps) : "—"}
              foot={summary.best ? dayLabel(summary.best.day, locale) : undefined}
            />
            <StatTile
              label={t("steps.streak")}
              value={goal ? plural(t, "steps.days", summary.streak) : "—"}
              foot={goal ? t("steps.in_a_row", { goal: asCount(goal) }) : t("steps.set_goal")}
              tone={summary.streak > 0 ? "positive" : "neutral"}
            />
          </StatRow>

          <section className="surface vitals-card" aria-label={t("steps.by_weekday")}>
            <Heading>{t("steps.each_weekday")}</Heading>
            <SeriesChart
              label={t("steps.weekday_chart")}
              labels={weekdays(t)}
              series={[{ key: "steps", name: t("heart.average"), values: summary.by_weekday.map((one) => one ?? 0) }]}
              kind="bars"
              format={asSteps}
              axisFormat={asCount}
            />
          </section>

          {summary.last_received && (
            <Hint>
              {t("steps.last_received", {
                when: new Date(summary.last_received).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }),
              })}
            </Hint>
          )}
        </>
      )}
      <AppVersion />
    </Screen>
  );
}
