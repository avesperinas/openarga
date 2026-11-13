import {
  BatteryLine,
  Heading,
  Hint,
  HourStrip,
  InfoHeading,
  Notice,
  Panes,
  RangeBar,
  RingFigure,
  Screen,
  SeriesChart,
  Sheet,
  Skeleton,
  SleepSchedule,
  VitalCard,
  VitalCards,
  WeekDots,
  type Translate,
  useLocale,
  useT,
} from "@openarga/ui";
import { useTick } from "@openarga/app/fresh";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Baseline,
  type DayLine,
  type SleepSummary,
  type Stress,
  type Today,
  Unauthorised,
  readDayLine,
  readSleep,
  readStress,
  readToday,
  signIn,
} from "./api";
import { minuteLabel } from "./heart";
import { ScreenHeader } from "./Header";
import { bandFigure } from "./rhythm";
import { hours, shortDay } from "./sleep";
import {
  daySentence,
  loadPace,
  moveVerdict,
  rangeState,
  recoveryLine,
  recoveryVerdict,
  sleepVerdict,
  thisWeek,
  trainVerdict,
  weekDots,
  worstTone,
} from "./today";
import { baselineValue, minutesLabel } from "./workouts";

export function localDay(now: Date = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function weekAgo(now: Date): string {
  const before = new Date(now);
  before.setDate(before.getDate() - 7);
  return localDay(before);
}

export type Go = (place: "sleep" | "training" | "steps") => void;

export function TodayScreen({ go }: { go?: Go } = {}) {
  const t = useT();
  const locale = useLocale();
  const [today, setToday] = useState<Today | null>(null);
  const [line, setLine] = useState<DayLine | null>(null);
  const [stress, setStress] = useState<Stress | null>(null);
  const [nights, setNights] = useState<SleepSummary | null>(null);
  const [problem, setProblem] = useState("");
  const [recovery, setRecovery] = useState(false);
  const now = new Date();
  const tick = useTick();

  useEffect(() => {
    const again = tick > 0;
    readStress().then(setStress).catch(() => again || setStress(null));
    readDayLine(localDay()).then(setLine).catch(() => again || setLine(null));
    readSleep(weekAgo(new Date())).then(setNights).catch(() => again || setNights(null));
    readToday()
      .then(setToday)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        if (!again) setProblem(t("today.read_failed"));
      });
  }, [tick, t]);

  const night = line?.night ?? null;
  const sleep = sleepVerdict(night?.score, t);
  const morning = stress?.morning ?? null;
  const ready = recoveryVerdict(morning?.score, t);
  const move = today ? moveVerdict(today.steps, t, locale) : null;
  const paced = today ? loadPace(today.load, now) : null;
  const train = paced ? trainVerdict(paced.share, t) : null;
  const week = today ? thisWeek(today.workouts, now) : [];
  const trainedToday = week.filter((one) => localDay(new Date(one.start)) === localDay(now));
  const sentence = daySentence({ sleep, recovery: ready, train }, t);
  const tone = worstTone([sleep?.tone, ready?.tone, train?.tone]);
  const battery = today?.battery ?? null;
  const band = battery ? bandFigure(battery, t) : null;
  const buckets = line?.heart?.buckets ?? [];
  const hrv = today?.baselines.find((one) => one.id === "hrv_ms");
  const resting = today?.baselines.find((one) => one.id === "resting_heart_rate");

  const cards = today && (
    <VitalCards label={t("today.how_are_you")}>
      {night?.score && sleep && (
        <VitalCard
          label={t("panel.sleep")}
          icon="moon"
          ring={{ value: night.score.value, target: 100, display: String(night.score.value) }}
          verdict={sleep.verdict}
          tone={sleep.tone}
          detail={[
            hours(night.minutes_asleep),
            night.minutes_to_fall_asleep != null ? t("today.took", { time: minutesLabel(night.minutes_to_fall_asleep) }) : null,
          ]
            .filter(Boolean)
            .join(" · ")}
          info={t("info.sleepScore")}
          onOpen={go ? () => go("sleep") : undefined}
        />
      )}
      {morning?.score != null && ready && (
        <VitalCard
          label={t("today.recovery")}
          icon="heart"
          ring={{ value: morning.score, target: 100, display: String(morning.score), mark: 0.5 }}
          verdict={ready.verdict}
          tone={ready.tone}
          detail={recoveryLine(morning.hrv_z, morning.resting_z, t)}
          info={t("info.readiness")}
          onOpen={() => setRecovery(true)}
        />
      )}
      {move && (
        <VitalCard
          label={t("today.movement")}
          icon="today"
          ring={{
            value: today.steps.today ?? 0,
            target: today.steps.goal ?? Math.max(1, today.steps.mean_30 ?? 1),
            display: (today.steps.today ?? 0).toLocaleString(locale),
          }}
          verdict={move.verdict}
          tone={move.tone}
          detail={move.detail}
          info={t("info.steps")}
          onOpen={go ? () => go("steps") : undefined}
        />
      )}
      {train && paced && (
        <VitalCard
          label={t("training.workout")}
          icon="flame"
          ring={{
            value: today.load.this_week,
            target: paced.expected ? Math.max(paced.expected, today.load.this_week) : Math.max(1, today.load.this_week),
            display: Math.round(today.load.this_week).toLocaleString(locale),
            mark: paced.expected ? Math.min(1, paced.expected / Math.max(paced.expected, today.load.this_week)) : undefined,
          }}
          verdict={train.verdict}
          tone={train.tone}
          detail={t("today.trained", {
            today: trainedToday.length > 0 ? trainedToday.map((one) => one.name).join(", ") : t("today.nothing"),
            week: week.length,
          })}
          info={t("info.load")}
          onOpen={go ? () => go("training") : undefined}
        />
      )}
    </VitalCards>
  );

  const day = (buckets.length > 1 || stress?.tension) && (
    <section className="surface vitals-card" aria-label={t("today.your_day")}>
      <InfoHeading info={t("info.dayPulse")}>{t("today.your_day")}</InfoHeading>
      {buckets.length > 1 && (
        <SeriesChart
          label={t("today.heart_today")}
          kind="lines"
          labels={buckets.map((one) => minuteLabel(one.minute))}
          series={[{ key: "avg", name: t("today.heart_rate"), values: buckets.map((one) => one.avg) }]}
          format={(value) => t("common.bpm", { value: Math.round(value) })}
        />
      )}
      {stress?.tension && (
        <>
          <HourStrip
            label={t("today.tension_label")}
            values={stress.tension.by_hour}
            format={(value) => `${Math.round(value)} min`}
            now={now.getHours()}
          />
          <Hint>{tensionLine(stress.tension.by_hour, stress.tension.minutes, t)}</Hint>
        </>
      )}
    </section>
  );

  const aside = today && (
    <>
      <section className="surface vitals-card" aria-label={t("today.this_week")}>
        <Heading>{t("today.this_week")}</Heading>
        <WeekDots days={weekDots(today.workouts, now)} label={t("training.workouts_week", { count: week.length })} size="large" />
        {nights && nights.nights.length > 1 && (
          <SleepSchedule
            label={t("today.schedule_label")}
            nights={nights.nights.slice(-7).map((one) => ({ day: one.day, start: one.start, end: one.end, quality: one.score?.quality ?? null }))}
            formatDay={(day) => shortDay(day, locale)}
          />
        )}
      </section>
      {battery?.battery_pct != null && <BatteryLine name={battery.name} percent={battery.battery_pct} detail={band?.foot} />}
    </>
  );

  return (
    <Screen wide>
      <ScreenHeader
        eyebrow={capital(new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long" }).format(now))}
        title={t("tabs.today")}
      />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {today === null && !problem && <Skeleton label={t("today.loading")} />}
      {today && (
        <Panes
          asideLabel={t("today.your_week")}
          main={
            <>
              {sentence && (
                <Notice tone={tone === "good" ? "positive" : tone === "neutral" ? "info" : "warning"}>{sentence}</Notice>
              )}
              {cards}
              {day}
              {buckets.length === 0 && !night && (
                <Hint>{t("today.nothing_yet")}</Hint>
              )}
            </>
          }
          aside={aside}
        />
      )}
      <Hint>{t("summary.disclaimer")}</Hint>
      <AppVersion />
      {recovery && morning?.score != null && (
        <Sheet title={t("today.how_you_start")} onClose={() => setRecovery(false)}>
          <RingFigure
            share={morning.score / 100}
            value={String(morning.score)}
            label={ready?.verdict ?? ""}
            detail={t("today.fifty_usual")}
          />
          {hrv && <BaselineBar baseline={hrv} label={t("metric.hrv_ms.name")} />}
          {resting && <BaselineBar baseline={resting} label={t("today.resting_heart")} />}
          <Hint>{t("info.readiness")}</Hint>
        </Sheet>
      )}
    </Screen>
  );
}

function BaselineBar({ baseline, label }: { baseline: Baseline; label: string }) {
  const t = useT();
  const locale = useLocale();
  return (
    <RangeBar
      label={label}
      value={baseline.value}
      unit={baseline.unit}
      low={baseline.low}
      high={baseline.high}
      state={rangeState(baseline)}
      figure={baselineValue(baseline, baseline.value, t, locale)}
      detail={
        baseline.low !== null && baseline.high !== null
          ? t("today.your_normal", {
              low: baselineValue(baseline, baseline.low, t, locale),
              high: baselineValue(baseline, baseline.high, t, locale),
            })
          : t("baseline.not_yet", { days: baseline.days })
      }
    />
  );
}

export function tensionLine(byHour: number[], minutes: number, t: Translate): string {
  if (minutes <= 0) return t("tension.none");
  let best = 0;
  let from = 0;
  for (let hour = 0; hour < byHour.length - 1; hour += 1) {
    const two = (byHour[hour] ?? 0) + (byHour[hour + 1] ?? 0);
    if (two > best) {
      best = two;
      from = hour;
    }
  }
  return t("tension.line", { time: minutesLabel(minutes), from, to: from + 2 });
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
