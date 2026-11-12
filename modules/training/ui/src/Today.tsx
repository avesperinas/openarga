import {
  Button,
  Card,
  Hint,
  IconBadge,
  Inline,
  List,
  ListRow,
  MonthCalendar,
  Section,
  Panes,
  Screen,
  WeekDots,
  type WeekDayState,
  isoDay,
} from "@openarga/ui";
import { peek, remember } from "@openarga/app";
import { useEffect, useMemo, useState } from "react";

import { ActivityList, ActivityQuick, ActivitySheet, LogActivitySheet } from "./Activities";
import { ConfirmStartSheet, rotationDetail } from "./ConfirmStart";
import {
  type Activity,
  type ActivityType,
  ApiError,
  type SessionSummary,
  type Today,
  listActivities,
  listActivityTypes,
  listSessions,
} from "./api";
import { readTodayKept, startAnywhere } from "./offline";
import { marksOf, monthStats } from "./History";
import { HUE_OF_KIND, ICON_OF_KIND, formatDuration, shortDate } from "./labels";
import { AppVersion } from "./AppVersion";
import { ScreenHeader } from "./Header";
import { todayLabel } from "./today";

export type TodayState = { status: "loading" } | { status: "ready"; today: Today } | { status: "error" };

export interface TodayScreenProps {
  now?: Date;
  initial?: TodayState;
  initialSessions?: SessionSummary[];
  onOpenSession: (id: string) => void;
  onOpenPlan?: () => void;
  onOpenHistory?: () => void;
}

export function TodayScreen({
  now = new Date(),
  initial,
  initialSessions,
  onOpenSession,
  onOpenPlan,
  onOpenHistory,
}: TodayScreenProps) {
  const [state, setState] = useState<TodayState>(() => {
    if (initial) return initial;
    const kept = peek<Today>("today");
    return kept ? { status: "ready", today: kept } : { status: "loading" };
  });
  const [sessions, setSessions] = useState<SessionSummary[] | null>(
    () => initialSessions ?? (initial ? [] : (peek<SessionSummary[]>("sessions") ?? null)),
  );
  const [cursor, setCursor] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [activities, setActivities] = useState<Activity[] | null>(() =>
    initial ? [] : (peek<Activity[]>("activities") ?? null),
  );
  const [types, setTypes] = useState<ActivityType[]>([]);
  const [logging, setLogging] = useState(false);
  const [openActivity, setOpenActivity] = useState<Activity | null>(null);
  const today = isoDay(now);

  useEffect(() => {
    if (initial) return;
    readTodayKept()
      .then((loaded) => setState({ status: "ready", today: loaded }))
      .catch(() => setState({ status: "error" }));
    listSessions("2000-01-01", today)
      .then((loaded) => {
        remember("sessions", loaded);
        setSessions(loaded);
      })
      .catch(() => setSessions((previous) => previous ?? []));
    listActivities("2000-01-01", today)
      .then((loaded) => {
        remember("activities", loaded);
        setActivities(loaded);
      })
      .catch(() => setActivities((previous) => previous ?? []));
    listActivityTypes()
      .then(setTypes)
      .catch(() => setTypes([]));
  }, [initial, today]);

  const marks = useMemo(() => marksOf(sessions ?? [], activities ?? []), [sessions, activities]);
  const monthKey = today.slice(0, 7);
  const month = monthStats((sessions ?? []).filter((session) => session.day.startsWith(monthKey)));
  const ready = state.status === "ready" ? state.today : null;
  const loading = state.status === "loading" ? "loading" : state.status === "error" ? "error" : "ready";

  return (
    <Screen wide>
      <ScreenHeader eyebrow={todayLabel(now)} />

      <Panes
        asideLabel="Lo último"
        main={
          <>
            <Card label={ready?.plan ? "Siguiente entreno" : "Tu plan"}>
              {ready ? (
                <NextBody today={ready} onOpenSession={onOpenSession} onOpenPlan={onOpenPlan} />
              ) : (
                <p className="widget-note" aria-busy={loading === "loading"}>
                  {loading === "error" ? "No se ha podido cargar. Comprueba la conexión." : "Cargando…"}
                </p>
              )}
            </Card>

            {ready && (
              <Section title="Esta semana">
                <Card>
                  <WeekStrip monday={ready.week.monday} today={today} sessions={sessions ?? []} />
                  <Hint>
                    {[
                      `${ready.week.done} de ${ready.week.goal}`,
                      `este mes, ${month.count} ${month.count === 1 ? "sesión" : "sesiones"}`,
                      `${month.sets} series`,
                      month.averageSeconds === null ? null : `${Math.round(month.averageSeconds / 60)} min de media`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Hint>
                </Card>
              </Section>
            )}

            <Section title="Calendario">
              <Card>
                <MonthCalendar
                  year={cursor.year}
                  month={cursor.month}
                  marks={marks}
                  today={today}
                  onSelect={(day) => {
                    const found = (sessions ?? []).find((session) => session.day === day);
                    if (found) onOpenSession(found.id);
                  }}
                  onPrevious={() => setCursor(shift(cursor, -1))}
                  onNext={() => setCursor(shift(cursor, 1))}
                />
              </Card>
            </Section>
          </>
        }
        aside={
          <>
            <Section
              title="Últimos entrenos"
              action={sessions && sessions.length > 4 && onOpenHistory ? { label: "Ver todo", onClick: onOpenHistory } : undefined}
            >
              {sessions && sessions.length === 0 ? (
                <p className="widget-note">Todavía no hay entrenos. El primero que termines aparecerá aquí y en el calendario.</p>
              ) : (
                <List>
                  {(sessions ?? []).slice(0, 4).map((session) => (
                    <ListRow
                      key={session.id}
                      hue={HUE_OF_KIND[session.kind]}
                      title={session.day_name}
                      subtitle={[
                        shortDate(session.day),
                        session.ended_at ? formatDuration(session.duration_seconds) : "en curso",
                        `${session.sets} ${session.sets === 1 ? "serie" : "series"}`,
                      ].join(" · ")}
                      accessory="chevron-right"
                      onClick={() => onOpenSession(session.id)}
                    />
                  ))}
                </List>
              )}
            </Section>

            <Section title="Actividades" action={{ label: "Anotar", icon: "plus", onClick: () => setLogging(true) }}>
              <ActivityQuick
                types={types}
                ongoing={activities?.find((activity) => activity.ongoing) ?? null}
                onChanged={(changed) =>
                  setActivities((previous) => [changed, ...(previous ?? []).filter((activity) => activity.id !== changed.id)])
                }
              />
              {activities && activities.length === 0 ? (
                <p className="widget-note">Escalada, pádel, una ruta: lo que hagas fuera de la rutina.</p>
              ) : (
                <ActivityList activities={latestFirst(activities ?? []).slice(0, 3)} onOpen={setOpenActivity} />
              )}
            </Section>
          </>
        }
      />

      {logging && (
        <LogActivitySheet
          today={today}
          onClose={() => setLogging(false)}
          onLogged={(activity) => {
            setLogging(false);
            setActivities((previous) =>
              [activity, ...(previous ?? [])].sort((a, b) => (a.day < b.day ? 1 : a.day > b.day ? -1 : 0)),
            );
          }}
        />
      )}
      {openActivity && (
        <ActivitySheet
          activity={openActivity}
          onClose={() => setOpenActivity(null)}
          onRemoved={(id) => {
            setOpenActivity(null);
            setActivities((previous) => (previous ?? []).filter((activity) => activity.id !== id));
          }}
          onChanged={(changed) => {
            setOpenActivity(null);
            setActivities((previous) => (previous ?? []).map((activity) => (activity.id === changed.id ? changed : activity)));
          }}
        />
      )}

      <AppVersion />
    </Screen>
  );
}

const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];

const addDays = (day: string, days: number) => {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};

export function WeekStrip({ monday, today, sessions }: { monday: string; today: string; sessions: SessionSummary[] }) {
  const days = WEEKDAYS.map((letter, index) => {
    const day = addDays(monday, index);
    const session = sessions.find((candidate) => candidate.day === day);
    const state: WeekDayState = session ? "met" : day === today ? "today" : day > today ? "future" : "missed";
    const said = `${letter}, ${session ? session.day_name : day > today ? "por venir" : "sin entreno"}`;
    return { day, state, kind: session?.kind, today: day === today, said };
  });
  return <WeekDots size="large" label={`Esta semana: ${days.map((one) => one.said).join("; ")}`} days={days} />;
}

const shift = ({ year, month }: { year: number; month: number }, delta: number) => {
  const date = new Date(year, month + delta, 1);
  return { year: date.getFullYear(), month: date.getMonth() };
};

interface NextBodyProps {
  today: Today;
  onOpenSession: (id: string) => void;
  onOpenPlan?: () => void;
}

function NextBody({ today, onOpenSession, onOpenPlan }: NextBodyProps) {
  const [confirming, setConfirming] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);

  const { plan, next, in_progress, rotation } = today;
  if (!plan) {
    return (
      <div className="training-next">
        <p className="training-next-name">Todavía no hay plan</p>
        <p className="training-next-label">
          Crea los días de tu ciclo con sus ejercicios. Después, aquí aparecerá cada día el entreno
          que toca.
        </p>
        {onOpenPlan && (
          <Button variant="primary" icon="plus" onClick={onOpenPlan}>
            Crear el plan
          </Button>
        )}
      </div>
    );
  }
  if (!next) return <p className="widget-note">El plan no tiene días todavía.</p>;

  const done = next.days_in_rotation - next.remaining;
  const pick = rotation?.days.find((day) => day.plan_day_id === chosen) ?? null;
  const target = pick
    ? { id: pick.plan_day_id, name: pick.name, kind: pick.kind }
    : { id: next.plan_day_id, name: next.name, kind: next.kind };

  async function start() {
    try {
      onOpenSession(await startAnywhere(pick && pick.plan_day_id !== next?.plan_day_id ? pick.plan_day_id : undefined));
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        const fresh = await readTodayKept().catch(() => null);
        if (fresh?.in_progress) {
          onOpenSession(fresh.in_progress);
          return;
        }
      }
      throw new Error(
        error instanceof ApiError && error.status !== 409
          ? error.message
          : "No se ha podido empezar: sin conexión hace falta haber abierto Training antes con red.",
      );
    }
  }

  return (
    <div className="training-next" data-kind={target.kind}>
      <p className="training-next-label">
        {in_progress ? "En curso" : pick && pick.plan_day_id !== next.plan_day_id ? "Elegido" : "Toca"} · rotación{" "}
        {next.rotation_number}, día {done + 1} de {next.days_in_rotation}
      </p>
      <p className="training-next-name">
        <IconBadge
          name={ICON_OF_KIND[target.kind]}
          hue={HUE_OF_KIND[target.kind] as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8}
        />
        <span>{in_progress ? "Entreno a medias" : target.name}</span>
      </p>
      {in_progress ? (
        <Button variant="primary" onClick={() => onOpenSession(in_progress)}>
          Continuar entreno
        </Button>
      ) : (
        <>
          <Inline>
            <Button variant="primary" onClick={() => setConfirming(true)}>
              {`Empezar ${target.name}`}
            </Button>
            {rotation && rotation.days.length > 1 && (
              <Button variant="plain" size="small" onClick={() => setConfirming(true)}>
                Otro día
              </Button>
            )}
          </Inline>
        </>
      )}
      {confirming && (
        <ConfirmStartSheet
          name={target.name}
          detail={rotationDetail(next.rotation_number, done + 1, next.days_in_rotation)}
          days={rotation?.days.map((day) => ({ id: day.plan_day_id, name: day.name, done: day.done }))}
          chosen={target.id}
          onChoose={setChosen}
          onCancel={() => setConfirming(false)}
          onStart={start}
        />
      )}
    </div>
  );
}

export function latestFirst(activities: Activity[]): Activity[] {
  return [...activities].sort((a, b) => {
    if (Boolean(a.ongoing) !== Boolean(b.ongoing)) return a.ongoing ? -1 : 1;
    const ka = `${a.day}T${a.start_time}`;
    const kb = `${b.day}T${b.start_time}`;
    return ka < kb ? 1 : ka > kb ? -1 : 0;
  });
}
