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
import { INFO } from "./info";
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

const LONG = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long" });

function weekAgo(now: Date): string {
  const before = new Date(now);
  before.setDate(before.getDate() - 7);
  return localDay(before);
}

export type Go = (place: "sleep" | "training" | "steps") => void;

export function TodayScreen({ go }: { go?: Go } = {}) {
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
        if (!again) setProblem("No se pudo leer hoy.");
      });
  }, [tick]);

  const night = line?.night ?? null;
  const sleep = sleepVerdict(night?.score);
  const morning = stress?.morning ?? null;
  const ready = recoveryVerdict(morning?.score);
  const move = today ? moveVerdict(today.steps) : null;
  const paced = today ? loadPace(today.load, now) : null;
  const train = paced ? trainVerdict(paced.share) : null;
  const week = today ? thisWeek(today.workouts, now) : [];
  const trainedToday = week.filter((one) => localDay(new Date(one.start)) === localDay(now));
  const sentence = daySentence({ sleep, recovery: ready, train });
  const tone = worstTone([sleep?.tone, ready?.tone, train?.tone]);
  const battery = today?.battery ?? null;
  const band = battery ? bandFigure(battery) : null;
  const buckets = line?.heart?.buckets ?? [];
  const hrv = today?.baselines.find((one) => one.id === "hrv_ms");
  const resting = today?.baselines.find((one) => one.id === "resting_heart_rate");

  const cards = today && (
    <VitalCards label="Cómo estás hoy">
      {night?.score && sleep && (
        <VitalCard
          label="Sueño"
          icon="moon"
          ring={{ value: night.score.value, target: 100, display: String(night.score.value) }}
          verdict={sleep.verdict}
          tone={sleep.tone}
          detail={[
            hours(night.minutes_asleep),
            night.minutes_to_fall_asleep != null ? `tardaste ${minutesLabel(night.minutes_to_fall_asleep)}` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
          info={INFO.sleepScore}
          onOpen={go ? () => go("sleep") : undefined}
        />
      )}
      {morning?.score != null && ready && (
        <VitalCard
          label="Recuperación"
          icon="heart"
          ring={{ value: morning.score, target: 100, display: String(morning.score), mark: 0.5 }}
          verdict={ready.verdict}
          tone={ready.tone}
          detail={recoveryLine(morning.hrv_z, morning.resting_z)}
          info={INFO.readiness}
          onOpen={() => setRecovery(true)}
        />
      )}
      {move && (
        <VitalCard
          label="Movimiento"
          icon="today"
          ring={{
            value: today.steps.today ?? 0,
            target: today.steps.goal ?? Math.max(1, today.steps.mean_30 ?? 1),
            display: (today.steps.today ?? 0).toLocaleString("es-ES"),
          }}
          verdict={move.verdict}
          tone={move.tone}
          detail={move.detail}
          info={INFO.steps}
          onOpen={go ? () => go("steps") : undefined}
        />
      )}
      {train && paced && (
        <VitalCard
          label="Entreno"
          icon="flame"
          ring={{
            value: today.load.this_week,
            target: paced.expected ? Math.max(paced.expected, today.load.this_week) : Math.max(1, today.load.this_week),
            display: Math.round(today.load.this_week).toLocaleString("es-ES"),
            mark: paced.expected ? Math.min(1, paced.expected / Math.max(paced.expected, today.load.this_week)) : undefined,
          }}
          verdict={train.verdict}
          tone={train.tone}
          detail={`hoy: ${trainedToday.length > 0 ? trainedToday.map((one) => one.name).join(", ") : "nada"} · semana: ${week.length}`}
          info={INFO.load}
          onOpen={go ? () => go("training") : undefined}
        />
      )}
    </VitalCards>
  );

  const day = (buckets.length > 1 || stress?.tension) && (
    <section className="surface vitals-card" aria-label="Tu día">
      <InfoHeading info={INFO.dayPulse}>Tu día</InfoHeading>
      {buckets.length > 1 && (
        <SeriesChart
          label="El vitals de hoy"
          kind="lines"
          labels={buckets.map((one) => minuteLabel(one.minute))}
          series={[{ key: "avg", name: "Vitals", values: buckets.map((one) => one.avg) }]}
          format={(value) => `${Math.round(value)} lpm`}
        />
      )}
      {stress?.tension && (
        <>
          <HourStrip
            label="Minutos de vitals alto estando quieto, por hora"
            values={stress.tension.by_hour}
            format={(value) => `${Math.round(value)} min`}
            now={now.getHours()}
          />
          <Hint>{tensionLine(stress.tension.by_hour, stress.tension.minutes)}</Hint>
        </>
      )}
    </section>
  );

  const aside = today && (
    <>
      <section className="surface vitals-card" aria-label="Esta semana">
        <Heading>Esta semana</Heading>
        <WeekDots days={weekDots(today.workouts, now)} label={`${week.length} entrenos esta semana`} size="large" />
        {nights && nights.nights.length > 1 && (
          <SleepSchedule
            label="De qué hora a qué hora dormiste las últimas noches"
            nights={nights.nights.slice(-7).map((one) => ({ day: one.day, start: one.start, end: one.end, quality: one.score?.quality ?? null }))}
            formatDay={shortDay}
          />
        )}
      </section>
      {battery?.battery_pct != null && <BatteryLine name={battery.name} percent={battery.battery_pct} detail={band?.foot} />}
    </>
  );

  return (
    <Screen wide>
      <ScreenHeader eyebrow={capital(LONG.format(now))} title="Hoy" />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {today === null && !problem && <Skeleton label="Cargando hoy" />}
      {today && (
        <Panes
          asideLabel="Tu semana"
          main={
            <>
              {sentence && (
                <Notice tone={tone === "good" ? "positive" : tone === "neutral" ? "info" : "warning"}>{sentence}</Notice>
              )}
              {cards}
              {day}
              {buckets.length === 0 && !night && (
                <Hint>Todavía no ha llegado nada de hoy: la pulsera pasa sus datos al sincronizar con el móvil.</Hint>
              )}
            </>
          }
          aside={aside}
        />
      )}
      <Hint>Vitals enseña cifras y rangos; no diagnostica ni aconseja.</Hint>
      <AppVersion />
      {recovery && morning?.score != null && (
        <Sheet title="Cómo llegas" onClose={() => setRecovery(false)}>
          <RingFigure share={morning.score / 100} value={String(morning.score)} label={ready?.verdict ?? ""} detail="50 es lo de siempre" />
          {hrv && <BaselineBar baseline={hrv} label="Variabilidad (VFC)" />}
          {resting && <BaselineBar baseline={resting} label="Vitals en reposo" />}
          <Hint>{INFO.readiness}</Hint>
        </Sheet>
      )}
    </Screen>
  );
}

function BaselineBar({ baseline, label }: { baseline: Baseline; label: string }) {
  return (
    <RangeBar
      label={label}
      value={baseline.value}
      unit={baseline.unit}
      low={baseline.low}
      high={baseline.high}
      state={rangeState(baseline)}
      figure={baselineValue(baseline, baseline.value)}
      detail={
        baseline.low !== null && baseline.high !== null
          ? `tu normal: ${baselineValue(baseline, baseline.low)} – ${baselineValue(baseline, baseline.high)}`
          : `aún sin tu normal (${baseline.days} de 14 días)`
      }
    />
  );
}

export function tensionLine(byHour: number[], minutes: number): string {
  if (minutes <= 0) return "Sin ratos de tensión hoy.";
  let best = 0;
  let from = 0;
  for (let hour = 0; hour < byHour.length - 1; hour += 1) {
    const two = (byHour[hour] ?? 0) + (byHour[hour + 1] ?? 0);
    if (two > best) {
      best = two;
      from = hour;
    }
  }
  return `${minutesLabel(minutes)} de tensión, sobre todo de ${from} a ${from + 2}.`;
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
