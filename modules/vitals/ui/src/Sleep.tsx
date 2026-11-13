import {
  Collapsible,
  Columns,
  EmptyState,
  HealthRing,
  Heading,
  Hint,
  Hypnogram,
  IconButton,
  InfoHeading,
  KeyFigures,
  PartBars,
  List,
  ListRow,
  QualityMonth,
  Screen,
  SeriesChart,
  Skeleton,
  SleepSchedule,
  StageBreakdown,
  TrendChart,
  YearCalendar,
  type Translate,
  useLocale,
  useT,
} from "@openarga/ui";
import { useEffect, useMemo, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type NightPage,
  type SleepPatterns,
  type SleepSummary,
  Unauthorised,
  readNight,
  readSleep,
  readSleepPatterns,
  signIn,
} from "./api";
import { ScreenHeader } from "./Header";
import { wakeTiles } from "./rhythm";
import { figureName } from "./body";
import {
  againstUsual,
  monthsOf,
  scoreDays,
  scoreParts,
  scoreTrend,
  stageShareList,
  yearAgo,
} from "./nights";
import { STAGES, hours, shortDay, stageSeries, timeOf } from "./sleep";
import { baselineTile, groupLine } from "./workouts";
import { dayLabel } from "./weight";
import { decimal } from "./words";

export function SleepScreen({ onSettings }: { onSettings: () => void }) {
  const t = useT();
  const locale = useLocale();
  const [summary, setSummary] = useState<SleepSummary | null>(null);
  const [problem, setProblem] = useState("");
  const [day, setDay] = useState<string | null>(null);
  const [month, setMonth] = useState<string | null>(null);

  useEffect(() => {
    readSleep(yearAgo(new Date()))
      .then((found) => {
        setSummary(found);
        setDay(found.last?.day ?? null);
        setMonth(found.last?.day.slice(0, 7) ?? null);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("sleep.read_failed"));
      });
  }, [t]);

  const nights = summary?.nights ?? [];
  const months = useMemo(() => monthsOf(nights), [nights]);
  const recent = nights.slice(-30);
  const at = month ? months.indexOf(month) : -1;

  const open = (picked: string) => {
    setDay(picked);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <Screen wide>
      <ScreenHeader title={t("panel.sleep")} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {summary === null && !problem && <Skeleton label={t("sleep.loading")} />}

      {summary && summary.last === null && (
        <EmptyState title={t("sleep.none_title")} action={{ label: t("common.to_settings"), onClick: onSettings }}>
          {t("sleep.none_text")}
        </EmptyState>
      )}

      {day && <NightCard day={day} onDay={setDay} />}

      <Columns count={2} stack>
        {month && nights.length > 0 && (
          <section className="surface vitals-card" aria-label={t("sleep.the_month")}>
            <InfoHeading info={t("info.calendar")}>{t("sleep.quality_each")}</InfoHeading>
            <QualityMonth
              label={t("sleep.score_each_month")}
              month={month}
              days={scoreDays(nights)}
              selected={day}
              onSelect={open}
              onPrevious={
                at > 0 ? () => setMonth(months[at - 1] ?? month) : undefined
              }
              onNext={
                at >= 0 && at < months.length - 1
                  ? () => setMonth(months[at + 1] ?? month)
                  : undefined
              }
            />
          </section>
        )}

        {recent.length > 1 && summary && (
          <section
            className="surface vitals-card health-figures"
            aria-label={t("sleep.the_schedule")}
          >
            <InfoHeading info={t("info.schedule")}>{t("sleep.schedule")}</InfoHeading>
            <SleepSchedule
              label={t("today.schedule_label")}
              nights={recent
                .slice(-14)
                .map((one) => ({
                  day: one.day,
                  start: one.start,
                  end: one.end,
                  quality: one.score?.quality ?? null,
                }))}
              formatDay={(day) => shortDay(day, locale)}
            />
            <Regularity summary={summary} />
          </section>
        )}
      </Columns>
      <Columns count={2} stack>
        {nights.length > 2 && (
          <section className="surface vitals-card" aria-label={t("sleep.the_trends")}>
            <InfoHeading info={t("info.trend")}>{t("sleep.trend")}</InfoHeading>
            <TrendChart
              label={t("sleep.trend_label")}
              points={scoreTrend(nights.slice(-90))}
              band={{ low: 80, high: 100 }}
              bandName={t("sleep.good_or_better")}
              valueName={t("sleep.score")}
              averageName={t("sleep.mean_7")}
              format={(value) => String(Math.round(value))}
            />
            {recent.some((one) => one.stages) && (
              <Collapsible
                title={t("sleep.stages_each")}
                subtitle={t("sleep.stages_hours")}
              >
                <SeriesChart
                  label={t("sleep.stages_hours")}
                  kind="stacked"
                  palette="stages"
                  labels={recent.map((one) => shortDay(one.day, locale))}
                  series={stageSeries(recent, t)}
                  order={STAGES.map((one) => one.id)}
                  format={(value) => hours(value * 60)}
                  axisFormat={(value) => `${decimal(value, locale, 1)} h`}
                />
              </Collapsible>
            )}
          </section>
        )}

        {nights.length > 7 && (
          <section className="surface vitals-card" aria-label={t("steps.the_year")}>
            <InfoHeading info={t("info.year")}>{t("steps.the_year")}</InfoHeading>
            <YearCalendar
              label={t("sleep.score_each_year")}
              days={scoreDays(nights)}
              goal={80}
              format={(value) => t("sleep.score_value", { value })}
            />
            <Hint>{t("sleep.green")}</Hint>
          </section>
        )}
      </Columns>

      {summary?.last && <PatternsCard />}
      <Hint>{t("summary.disclaimer")}</Hint>
      <AppVersion />
    </Screen>
  );
}

function NightCard({
  day,
  onDay,
}: {
  day: string;
  onDay: (day: string) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const [page, setPage] = useState<NightPage | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    setProblem("");
    readNight(day)
      .then(setPage)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("sleep.night_failed"));
      });
  }, [day, t]);

  if (problem) return <Hint tone="warning">{problem}</Hint>;
  if (!page || page.night.day !== day)
    return <Skeleton label={t("sleep.night_loading")} />;
  const { night, mean_30: usual } = page;
  const score = night.score;
  const woke = wakeTiles(night, t);

  return (
    <section
      className="surface vitals-card health-figures"
      aria-label={t("sleep.night_of", { day: dayLabel(night.day, locale) })}
    >
      <div className="vitals-night-head">
        <IconButton
          icon="chevron-left"
          label={t("sleep.previous")}
          variant="plain"
          disabled={!page.previous}
          onClick={() => page.previous && onDay(page.previous)}
        />
        <Heading>{t("sleep.night_of", { day: dayLabel(night.day, locale) })}</Heading>
        <IconButton
          icon="chevron-right"
          label={t("sleep.next")}
          variant="plain"
          disabled={!page.next}
          onClick={() => page.next && onDay(page.next)}
        />
      </div>

      <div className="vitals-night-top">
        {score && (
          <HealthRing
            value={score.value}
            target={100}
            display={String(score.value)}
            caption={t(`verdict.${score.quality}`)}
            quality={score.quality}
            label={t("sleep.sleep_score")}
            size="l"
            info={t("score.info")}
          />
        )}
        <KeyFigures
          label={t("sleep.the_night")}
          items={[
            {
              label: t("sleep.asleep"),
              value: hours(night.minutes_asleep),
              foot: againstUsual(night.minutes_asleep, usual.asleep, t),
              info: t("info.sleepMinutes"),
            },
            {
              label: t("sleep.in_bed"),
              value: `${timeOf(night.start)} – ${timeOf(night.end)}`,
              foot: night.minutes_in_bed
                ? hours(night.minutes_in_bed)
                : undefined,
              info: t("info.inBed"),
            },
            ...(night.minutes_to_fall_asleep != null
              ? [
                  {
                    label: t("sleep.fell_asleep"),
                    value: hours(night.minutes_to_fall_asleep),
                    info: t("info.fellAsleep"),
                  },
                ]
              : []),
            ...(night.nap_minutes > 0
              ? [
                  {
                    label: t("sleep.naps"),
                    value: hours(night.nap_minutes),
                    info: t("info.naps"),
                  },
                ]
              : []),
          ]}
        />
      </div>

      {score && (
        <PartBars label={t("sleep.score_parts")} parts={scoreParts(score, t)} />
      )}

      {night.segments.length > 0 && (
        <>
          <InfoHeading info={t("info.hypnogram")}>{t("sleep.night_stages")}</InfoHeading>
          <Hypnogram
            segments={night.segments}
            start={night.start}
            end={night.end}
            pulse={page.heart}
            label={t("sleep.hypnogram_label")}
          />
        </>
      )}
      {(night.stages || page.figures.length > 0 || woke.length > 0) && (
        <Collapsible
          title={t("sleep.more")}
          subtitle={moreLine(page, woke.length, t)}
        >
          {night.stages && (
            <>
              <InfoHeading info={t("info.stages")}>{t("sleep.how_much_each")}</InfoHeading>
              <StageBreakdown stages={stageShareList(night, usual)} />
            </>
          )}
          {page.figures.length > 0 && (
            <>
              <InfoHeading info={t("info.normal")}>{t("sleep.against_normal")}</InfoHeading>
              <KeyFigures
                label={t("sleep.against_normal")}
                items={page.figures.map((one) => {
                  const tile = baselineTile(one, t, locale);
                  const info = NIGHT_INFO[one.id];
                  return {
                    label: figureName(t, { id: one.id, name: one.name }),
                    value: tile.value,
                    foot: tile.foot,
                    tone: tile.tone === "warning" ? "warning" : undefined,
                    info: info ? t(info) : undefined,
                  };
                })}
              />
            </>
          )}
          {woke.length > 0 && (
            <KeyFigures
              label={t("sleep.awakenings")}
              items={woke.map((one) => ({ ...one, info: t("info.awakenings") }))}
            />
          )}
        </Collapsible>
      )}
    </section>
  );
}

function Regularity({ summary }: { summary: SleepSummary }) {
  const t = useT();
  const [found, setFound] = useState<SleepPatterns | null>(null);
  useEffect(() => {
    readSleepPatterns()
      .then(setFound)
      .catch(() => setFound(null));
  }, []);
  const mean = summary.mean_30;
  return (
    <KeyFigures
      label={t("sleep.regularity")}
      items={[
        {
          label: t("sleep.fall_asleep_avg"),
          value: clockText(mean.fell_asleep_at),
          foot:
            found?.fell_asleep_spread != null
              ? `± ${found.fell_asleep_spread} min`
              : undefined,
          info: t("info.regularity"),
        },
        {
          label: t("sleep.wake_avg"),
          value: clockText(mean.woke_at),
          foot:
            found?.woke_spread != null
              ? `± ${found.woke_spread} min`
              : undefined,
          info: t("info.regularity"),
        },
        {
          label: t("sleep.asleep_30"),
          value: hours(mean.asleep),
          foot: t("group.nights.other", { count: mean.nights }),
        },
      ]}
    />
  );
}

function moreLine(page: NightPage, awakenings: number, t: Translate): string {
  const hrv = page.figures.find((one) => one.id === "hrv_ms");
  return [
    page.night.stages ? t("sleep.stages") : null,
    hrv && hrv.value !== null ? t("group.hrv", { value: Math.round(hrv.value) }) : null,
    awakenings > 0 && page.night.awakenings
      ? t(page.night.awakenings === 1 ? "sleep.awakening.one" : "sleep.awakening.other", { count: page.night.awakenings })
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

const NIGHT_INFO: Record<string, string> = {
  hrv_ms: "info.hrv",
  respiratory_rate: "info.respiration",
  spo2_pct: "info.spo2",
  skin_temp_delta_c: "info.skinTemp",
};

function clockText(minutes: number | null): string {
  if (minutes === null) return "—";
  const day = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(day / 60)).padStart(2, "0")}:${String(day % 60).padStart(2, "0")}`;
}

function PatternsCard() {
  const t = useT();
  const locale = useLocale();
  const [found, setFound] = useState<SleepPatterns | null>(null);
  useEffect(() => {
    readSleepPatterns()
      .then(setFound)
      .catch(() => setFound(null));
  }, []);
  if (!found || found.comparisons.length === 0) return null;
  return (
    <section
      className="surface vitals-card"
      aria-label={t("sleep.day_before")}
    >
      <InfoHeading info={t("info.afterTraining")}>{t("sleep.day_before")}</InfoHeading>
      <List>
        {found.comparisons.map((one) => {
          const key = `pattern.${one.id}`;
          return (
            <ListRow
              key={one.id}
              title={t(key) === key ? one.label : t(key)}
              subtitle={t("sleep.compared", { after: groupLine(one.after, t, locale), rest: groupLine(one.rest, t, locale) })}
            />
          );
        })}
      </List>
      <Hint>{t("sleep.averages_90")}</Hint>
    </section>
  );
}
