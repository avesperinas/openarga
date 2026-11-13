import {
  Button,
  Collapsible,
  EmptyState,
  GroupLabel,
  HealthRing,
  InfoHeading,
  Heading,
  Hint,
  List,
  ListRow,
  Panes,
  PartBars,
  Screen,
  SeriesChart,
  Sheet,
  Skeleton,
  SplitBar,
  WeekDots,
  WorkoutHeart,
  type Locale,
  type Translate,
  useLocale,
  useT,
} from "@openarga/ui";
import { useTick } from "@openarga/app/fresh";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type Load, type Workout, type WorkoutDetail, Unauthorised, readLoad, readWorkout, readWorkouts, signIn } from "./api";
import { ScreenHeader } from "./Header";
import { daysStarted, loadPace, trainVerdict, weekDots } from "./today";
import { decimal } from "./words";
import { byName, byWeek, clock, elapsed, fromFirstLoad, minutesLabel, rollingMean, whenLabel, workoutLine, zoneShares, zoneWeeks } from "./workouts";
import { shortDay } from "./sleep";

const HUE = { strength: 4, activity: 6 } as const;

export function WorkoutList({ workouts, onOpen }: { workouts: Workout[]; onOpen: (id: string) => void }) {
  const t = useT();
  const locale = useLocale();
  return (
    <List>
      {workouts.map((one) => (
        <ListRow
          key={one.id}
          hue={HUE[one.kind]}
          title={one.name}
          subtitle={workoutLine(one, t, locale)}
          accessory="chevron-right"
          onClick={() => onOpen(one.id)}
        />
      ))}
    </List>
  );
}

export function ZoneWeeksChart({ load }: { load: Load }) {
  const t = useT();
  const locale = useLocale();
  return (
    <SeriesChart
      label={t("training.zone_minutes_week")}
      kind="stacked"
      palette="zones"
      labels={load.weeks.map((one) => shortDay(one.start, locale))}
      series={zoneWeeks(load).map((values, index) => ({
        key: `z${index + 1}`,
        name: t("training.zone_named", { number: index + 1, name: t(`zone.${index + 1}`) }),
        values,
      }))}
      order={["z1", "z2", "z3", "z4", "z5"]}
      format={(value) => `${Math.round(value)} min`}
    />
  );
}

export function LoadChart({ load }: { load: Load }) {
  const t = useT();
  const locale = useLocale();
  return (
    <SeriesChart
      label={t("training.load_per_week")}
      labels={load.weeks.map((one) => shortDay(one.start, locale))}
      series={[{ key: "load", name: t("stat.load"), values: load.weeks.map((one) => one.load) }]}
      format={(value) => Math.round(value).toLocaleString(locale)}
    />
  );
}

export function TrainingScreen() {
  const t = useT();
  const locale = useLocale();
  const [open, setOpen] = useState<string | null>(null);
  const [workouts, setWorkouts] = useState<Workout[] | null>(null);
  const [load, setLoad] = useState<Load | null>(null);
  const [all, setAll] = useState(false);
  const [problem, setProblem] = useState("");
  const now = new Date();

  const tick = useTick();

  useEffect(() => {
    Promise.all([readWorkouts(), readLoad()])
      .then(([found, weeks]) => {
        setWorkouts(found);
        setLoad(weeks);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        if (tick === 0) setProblem(t("training.read_failed"));
      });
  }, [tick, t]);

  const paced = load ? loadPace(load, now) : null;
  const verdict = paced ? trainVerdict(paced.share, t) : null;
  const counts = load ? load.weeks.slice(-5, -1).map((week) => week.workouts) : [];
  const meanCount = counts.length === 4 ? counts.reduce((sum, one) => sum + one, 0) / 4 : null;
  const doneCount = load?.weeks.at(-1)?.workouts ?? 0;
  const expectedCount = meanCount !== null ? (meanCount * daysStarted(now)) / 7 : null;
  const shown = load ? fromFirstLoad(load) : null;
  const zones = load ? zoneShares(load) : null;
  const names = workouts ? byName(workouts, now, t) : [];
  const weeks = workouts ? byWeek(workouts, now, t, locale) : [];
  const visibleWeeks = all ? weeks : weeks.slice(0, 4);

  const hero = load && paced && verdict && (
    <section className="surface vitals-card" aria-label={t("today.this_week")}>
      <Heading>{t("today.this_week")}</Heading>
      <div className="health-rings">
        <HealthRing
          value={load.this_week}
          target={paced.expected ? Math.max(paced.expected, load.this_week) : Math.max(1, load.this_week)}
          display={Math.round(load.this_week).toLocaleString(locale)}
          caption={paced.expected ? t("training.normal_today", { value: Math.round(paced.expected) }) : undefined}
          label={t("stat.load")}
          info={t("info.load")}
          mark={paced.expected ? Math.min(1, paced.expected / Math.max(paced.expected, load.this_week)) : undefined}
        />
        <HealthRing
          value={doneCount}
          target={expectedCount ? Math.max(expectedCount, doneCount) : Math.max(1, doneCount)}
          display={String(doneCount)}
          caption={expectedCount ? t("training.normal_today", { value: decimal(expectedCount, locale, 1) }) : undefined}
          label={t("stat.workouts")}
          info={t("info.workoutsWeek")}
          mark={expectedCount ? Math.min(1, expectedCount / Math.max(expectedCount, doneCount)) : undefined}
        />
      </div>
      {workouts && <WeekDots days={weekDots(workouts, now)} label={t("training.workouts_week", { count: doneCount })} size="large" />}
      <Hint>{weekLine(verdict.code, load.this_week, paced.expected, t, locale)}</Hint>
    </section>
  );

  const charts = shown && shown.weeks.length > 0 && (
    <>
      <section className="surface vitals-card" aria-label={t("training.load_weeks")}>
        <InfoHeading info={t("info.loadWeeks")}>{t("training.load_weeks")}</InfoHeading>
        <SeriesChart
          label={t("training.load_with_mean")}
          labels={shown.weeks.map((one, index) => (index === shown.weeks.length - 1 ? t("training.this") : shortDay(one.start, locale)))}
          series={[{ key: "load", name: t("stat.load"), values: shown.weeks.map((one) => one.load) }]}
          overlay={{
            key: "mean",
            name: t("training.your_mean"),
            values: rollingMean(load!).slice(load!.weeks.length - shown.weeks.length).map((one) => one ?? Number.NaN),
          }}
          format={(value) => Math.round(value).toLocaleString(locale)}
        />
      </section>
      {zones && zones.minutes.some((one) => one > 0) && (
        <section className="surface vitals-card" aria-label={t("training.intensity")}>
          <InfoHeading info={`${t("info.zoneWeeks")} ${t("zone.info")}`}>{t("training.intensity_4")}</InfoHeading>
          <SplitBar
            label={t("training.zone_minutes_4")}
            palette="zones"
            parts={zones.minutes.map((minutes, index) => ({
              label: `Z${index + 1} · ${t(`zone.${index + 1}`)}`,
              value: `${Math.round((zones.shares[index] ?? 0) * 100)} % · ${minutesLabel(minutes)}`,
              share: minutes,
              hue: (index + 1) as 1 | 2 | 3 | 4 | 5,
            }))}
          />
          <Collapsible title={t("training.per_week")} subtitle={t("training.per_week_sub")}>
            <ZoneWeeksChart load={shown} />
          </Collapsible>
        </section>
      )}
    </>
  );

  const aside = workouts && workouts.length > 0 && (
    <>
      {names.length > 0 && (
        <section className="surface vitals-card" aria-label={t("training.what_you_do")}>
          <Heading>{t("training.what_you_do_30")}</Heading>
          <PartBars
            label={t("training.what_you_do_label")}
            parts={names.map((one) => ({
              label: one.name,
              value: `${one.count} · ${minutesLabel(one.minutes)}`,
              share: one.minutes / Math.max(1, names[0]?.minutes ?? 1),
            }))}
          />
        </section>
      )}
      <section className="surface vitals-card" aria-label={t("training.the_workouts")}>
        <Heading>{t("stat.workouts")}</Heading>
        {visibleWeeks.map((week) => (
          <div key={week.start} className="vitals-group">
            <GroupLabel>{week.label}</GroupLabel>
            <WorkoutList workouts={week.items} onOpen={setOpen} />
          </div>
        ))}
        {weeks.length > 4 && !all && (
          <Button variant="plain" onClick={() => setAll(true)}>
            {t("training.see_90")}
          </Button>
        )}
      </section>
    </>
  );

  return (
    <Screen wide>
      <ScreenHeader title={t("tabs.training")} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {workouts === null && !problem && <Skeleton label={t("training.loading")} />}
      {workouts && workouts.length === 0 && <EmptyState title={t("training.none_title")}>{t("training.none_text")}</EmptyState>}
      {(hero || aside) && (
        <Panes
          asideLabel={t("training.yours")}
          main={
            <>
              {hero}
              {charts}
            </>
          }
          aside={aside}
        />
      )}
      {open && <WorkoutSheet id={open} onClose={() => setOpen(null)} />}
      <AppVersion />
    </Screen>
  );
}

export function weekLine(code: string, done: number, expected: number | null, t: Translate, locale: Locale): string {
  const day = new Intl.DateTimeFormat(locale, { weekday: "long" }).format(new Date());
  const head = t(`week_line.${code}`);
  const load = Math.round(done).toLocaleString(locale);
  if (expected === null) return t("week_line.load", { head, load });
  return t("week_line.load_expected", { head, load, day, expected: Math.round(expected).toLocaleString(locale) });
}

export function WorkoutSheet({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useT();
  const [found, setFound] = useState<WorkoutDetail | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    setFound(null);
    readWorkout(id)
      .then(setFound)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("training.workout_failed"));
      });
  }, [id, t]);

  return (
    <Sheet title={found?.name ?? t("training.workout")} onClose={onClose}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {found === null && !problem && <Skeleton label={t("training.workout_loading")} />}
      {found && <WorkoutBody workout={found} />}
    </Sheet>
  );
}

export function WorkoutBody({ workout }: { workout: WorkoutDetail }) {
  const t = useT();
  const locale = useLocale();
  return (
    <>
      <Hint>
        {whenLabel(workout.start, locale)} – {clock(workout.end)} · {minutesLabel(workout.minutes)}
        {workout.href ? " · " : ""}
        {workout.href && <a href={workout.href}>{workout.kind === "strength" ? t("training.open_in") : t("training.see_in")}</a>}
      </Hint>
      <WorkoutHeart
        start={workout.start}
        heart={{
          ...workout.heart,
          minutes: workout.minutes,
          kcal: workout.kcal,
          max_heart_rate: workout.max_heart_rate,
          beats: workout.beats,
          marks: workout.marks,
        }}
      />
      {workout.marks.length > 0 && (
        <>
          <Heading>{t("history.sets_title")}</Heading>
          <List>
            {workout.marks.map((mark) => (
              <ListRow
                key={mark.at}
                title={mark.label}
                subtitle={elapsed(Math.max(0, Math.round((Date.parse(mark.at) - Date.parse(workout.start)) / 1000)))}
              />
            ))}
          </List>
        </>
      )}
    </>
  );
}
