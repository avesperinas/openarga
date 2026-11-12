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
  ZONES_INFO,
  ZONE_LABELS,
} from "@openarga/ui";
import { useTick } from "@openarga/app/fresh";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type Load, type Workout, type WorkoutDetail, Unauthorised, readLoad, readWorkout, readWorkouts, signIn } from "./api";
import { ScreenHeader } from "./Header";
import { INFO } from "./info";
import { daysStarted, loadPace, trainVerdict, weekDots } from "./today";
import { byName, byWeek, clock, elapsed, fromFirstLoad, minutesLabel, rollingMean, whenLabel, workoutLine, zoneShares, zoneWeeks } from "./workouts";
import { shortDay } from "./sleep";

const HUE = { strength: 4, activity: 6 } as const;

export function WorkoutList({ workouts, onOpen }: { workouts: Workout[]; onOpen: (id: string) => void }) {
  return (
    <List>
      {workouts.map((one) => (
        <ListRow
          key={one.id}
          hue={HUE[one.kind]}
          title={one.name}
          subtitle={workoutLine(one)}
          accessory="chevron-right"
          onClick={() => onOpen(one.id)}
        />
      ))}
    </List>
  );
}

export function ZoneWeeksChart({ load }: { load: Load }) {
  return (
    <SeriesChart
      label="Minutos en cada zona de vitals, por semana"
      kind="stacked"
      palette="zones"
      labels={load.weeks.map((one) => shortDay(one.start))}
      series={zoneWeeks(load).map((values, index) => ({ key: `z${index + 1}`, name: `Zona ${index + 1} · ${ZONE_LABELS[index]}`, values }))}
      order={["z1", "z2", "z3", "z4", "z5"]}
      format={(value) => `${Math.round(value)} min`}
    />
  );
}

export function LoadChart({ load }: { load: Load }) {
  return (
    <SeriesChart
      label="Carga de entreno por semana"
      labels={load.weeks.map((one) => shortDay(one.start))}
      series={[{ key: "load", name: "Carga", values: load.weeks.map((one) => one.load) }]}
      format={(value) => Math.round(value).toLocaleString("es-ES")}
    />
  );
}

export function TrainingScreen() {
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
        if (tick === 0) setProblem("No se pudieron leer los entrenos.");
      });
  }, [tick]);

  const paced = load ? loadPace(load, now) : null;
  const verdict = paced ? trainVerdict(paced.share) : null;
  const counts = load ? load.weeks.slice(-5, -1).map((week) => week.workouts) : [];
  const meanCount = counts.length === 4 ? counts.reduce((sum, one) => sum + one, 0) / 4 : null;
  const doneCount = load?.weeks.at(-1)?.workouts ?? 0;
  const expectedCount = meanCount !== null ? (meanCount * daysStarted(now)) / 7 : null;
  const shown = load ? fromFirstLoad(load) : null;
  const zones = load ? zoneShares(load) : null;
  const names = workouts ? byName(workouts, now) : [];
  const weeks = workouts ? byWeek(workouts, now) : [];
  const visibleWeeks = all ? weeks : weeks.slice(0, 4);

  const hero = load && paced && verdict && (
    <section className="surface vitals-card" aria-label="Esta semana">
      <Heading>Esta semana</Heading>
      <div className="health-rings">
        <HealthRing
          value={load.this_week}
          target={paced.expected ? Math.max(paced.expected, load.this_week) : Math.max(1, load.this_week)}
          display={Math.round(load.this_week).toLocaleString("es-ES")}
          caption={paced.expected ? `normal hoy: ${Math.round(paced.expected)}` : undefined}
          label="Carga"
          info={INFO.load}
          mark={paced.expected ? Math.min(1, paced.expected / Math.max(paced.expected, load.this_week)) : undefined}
        />
        <HealthRing
          value={doneCount}
          target={expectedCount ? Math.max(expectedCount, doneCount) : Math.max(1, doneCount)}
          display={String(doneCount)}
          caption={expectedCount ? `normal hoy: ${expectedCount.toLocaleString("es-ES", { maximumFractionDigits: 1 })}` : undefined}
          label="Entrenos"
          info={INFO.workoutsWeek}
          mark={expectedCount ? Math.min(1, expectedCount / Math.max(expectedCount, doneCount)) : undefined}
        />
      </div>
      {workouts && <WeekDots days={weekDots(workouts, now)} label={`${doneCount} entrenos esta semana`} size="large" />}
      <Hint>{weekLine(verdict.verdict, load.this_week, paced.expected)}</Hint>
    </section>
  );

  const charts = shown && shown.weeks.length > 0 && (
    <>
      <section className="surface vitals-card" aria-label="Carga por semana">
        <InfoHeading info={INFO.loadWeeks}>Carga por semana</InfoHeading>
        <SeriesChart
          label="Carga de entreno por semana, con tu media de las cuatro de antes"
          labels={shown.weeks.map((one, index) => (index === shown.weeks.length - 1 ? "esta" : shortDay(one.start)))}
          series={[{ key: "load", name: "Carga", values: shown.weeks.map((one) => one.load) }]}
          overlay={{
            key: "mean",
            name: "Tu media",
            values: rollingMean(load!).slice(load!.weeks.length - shown.weeks.length).map((one) => one ?? Number.NaN),
          }}
          format={(value) => Math.round(value).toLocaleString("es-ES")}
        />
      </section>
      {zones && zones.minutes.some((one) => one > 0) && (
        <section className="surface vitals-card" aria-label="Intensidad">
          <InfoHeading info={`${INFO.zoneWeeks} ${ZONES_INFO}`}>Intensidad, últimas 4 semanas</InfoHeading>
          <SplitBar
            label="Minutos en cada zona de vitals en las últimas cuatro semanas"
            palette="zones"
            parts={zones.minutes.map((minutes, index) => ({
              label: `Z${index + 1} · ${ZONE_LABELS[index]}`,
              value: `${Math.round((zones.shares[index] ?? 0) * 100)} % · ${minutesLabel(minutes)}`,
              share: minutes,
              hue: (index + 1) as 1 | 2 | 3 | 4 | 5,
            }))}
          />
          <Collapsible title="Por semana" subtitle="Minutos en cada zona, semana a semana">
            <ZoneWeeksChart load={shown} />
          </Collapsible>
        </section>
      )}
    </>
  );

  const aside = workouts && workouts.length > 0 && (
    <>
      {names.length > 0 && (
        <section className="surface vitals-card" aria-label="Qué haces">
          <Heading>Qué haces · 30 días</Heading>
          <PartBars
            label="Lo que haces, por minutos, en los últimos 30 días"
            parts={names.map((one) => ({
              label: one.name,
              value: `${one.count} · ${minutesLabel(one.minutes)}`,
              share: one.minutes / Math.max(1, names[0]?.minutes ?? 1),
            }))}
          />
        </section>
      )}
      <section className="surface vitals-card" aria-label="Los entrenos">
        <Heading>Entrenos</Heading>
        {visibleWeeks.map((week) => (
          <div key={week.start} className="vitals-group">
            <GroupLabel>{week.label}</GroupLabel>
            <WorkoutList workouts={week.items} onOpen={setOpen} />
          </div>
        ))}
        {weeks.length > 4 && !all && (
          <Button variant="plain" onClick={() => setAll(true)}>
            Ver los 90 días
          </Button>
        )}
      </section>
    </>
  );

  return (
    <Screen wide>
      <ScreenHeader title="Entrenar" />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {workouts === null && !problem && <Skeleton label="Cargando los entrenos" />}
      {workouts && workouts.length === 0 && (
        <EmptyState title="Todavía no hay entrenos">
          Los entrenos de Training y lo que registre la pulsera (pádel, bici…) aparecen aquí con su vitals.
        </EmptyState>
      )}
      {(hero || aside) && (
        <Panes
          asideLabel="Tus entrenos"
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

export function weekLine(verdict: string, done: number, expected: number | null): string {
  const day = new Intl.DateTimeFormat("es-ES", { weekday: "long" }).format(new Date());
  const said: Record<string, string> = {
    "Por encima de tu ritmo": "Vas por encima de tu ritmo",
    "A tu ritmo": "Vas a tu ritmo",
    "Algo por debajo": "Vas algo por debajo de tu ritmo",
    "Por debajo de tu ritmo": "Vas por debajo de tu ritmo",
    "Sin media aún": "Aún sin cuatro semanas para comparar",
  };
  const head = said[verdict] ?? verdict;
  if (expected === null) return `${head}: ${Math.round(done).toLocaleString("es-ES")} de carga.`;
  return `${head}: ${Math.round(done).toLocaleString("es-ES")} de carga; lo normal a ${day}, ${Math.round(expected).toLocaleString("es-ES")}.`;
}

export function WorkoutSheet({ id, onClose }: { id: string; onClose: () => void }) {
  const [found, setFound] = useState<WorkoutDetail | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    setFound(null);
    readWorkout(id)
      .then(setFound)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudo leer el entreno.");
      });
  }, [id]);

  return (
    <Sheet title={found?.name ?? "Entreno"} onClose={onClose}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {found === null && !problem && <Skeleton label="Cargando el entreno" />}
      {found && <WorkoutBody workout={found} />}
    </Sheet>
  );
}

export function WorkoutBody({ workout }: { workout: WorkoutDetail }) {
  return (
    <>
      <Hint>
        {whenLabel(workout.start)} – {clock(workout.end)} · {minutesLabel(workout.minutes)}
        {workout.href ? " · " : ""}
        {workout.href && <a href={workout.href}>{workout.kind === "strength" ? "Abrir en Training" : "Ver en Training"}</a>}
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
          <Heading>Series</Heading>
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
