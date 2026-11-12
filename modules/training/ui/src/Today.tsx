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
  useLocale,
  useT,
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
import { HUE_OF_KIND, ICON_OF_KIND, formatDuration, plural, shortDate } from "./labels";
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
  const t = useT();
  const locale = useLocale();
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
      <ScreenHeader eyebrow={todayLabel(now, locale)} />

      <Panes
        asideLabel={t("today.latest")}
        main={
          <>
            <Card label={ready?.plan ? t("today.next_workout") : t("today.your_plan")}>
              {ready ? (
                <NextBody today={ready} onOpenSession={onOpenSession} onOpenPlan={onOpenPlan} />
              ) : (
                <p className="widget-note" aria-busy={loading === "loading"}>
                  {loading === "error" ? t("common.load_failed") : t("common.loading")}
                </p>
              )}
            </Card>

            {ready && (
              <Section title={t("today.this_week")}>
                <Card>
                  <WeekStrip monday={ready.week.monday} today={today} sessions={sessions ?? []} />
                  <Hint>
                    {[
                      t("today.of_goal", { done: ready.week.done, goal: ready.week.goal }),
                      plural(t, "today.month_sessions", month.count),
                      plural(t, "common.sets", month.sets),
                      month.averageSeconds === null
                        ? null
                        : t("today.average_minutes", { minutes: Math.round(month.averageSeconds / 60) }),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Hint>
                </Card>
              </Section>
            )}

            <Section title={t("tabs.calendar")}>
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
              title={t("today.latest_workouts")}
              action={sessions && sessions.length > 4 && onOpenHistory ? { label: t("common.see_all"), onClick: onOpenHistory } : undefined}
            >
              {sessions && sessions.length === 0 ? (
                <p className="widget-note">{t("today.no_workouts")}</p>
              ) : (
                <List>
                  {(sessions ?? []).slice(0, 4).map((session) => (
                    <ListRow
                      key={session.id}
                      hue={HUE_OF_KIND[session.kind]}
                      title={session.day_name}
                      subtitle={[
                        shortDate(session.day, locale),
                        session.ended_at ? formatDuration(session.duration_seconds) : t("common.ongoing"),
                        plural(t, "common.sets", session.sets),
                      ].join(" · ")}
                      accessory="chevron-right"
                      onClick={() => onOpenSession(session.id)}
                    />
                  ))}
                </List>
              )}
            </Section>

            <Section title={t("today.activities")} action={{ label: t("activity.log"), icon: "plus", onClick: () => setLogging(true) }}>
              <ActivityQuick
                types={types}
                ongoing={activities?.find((activity) => activity.ongoing) ?? null}
                onChanged={(changed) =>
                  setActivities((previous) => [changed, ...(previous ?? []).filter((activity) => activity.id !== changed.id)])
                }
              />
              {activities && activities.length === 0 ? (
                <p className="widget-note">{t("today.activities_empty")}</p>
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

const addDays = (day: string, days: number) => {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};

export function WeekStrip({ monday, today, sessions }: { monday: string; today: string; sessions: SessionSummary[] }) {
  const t = useT();
  const days = t("today.weekday_letters").split(",").map((letter, index) => {
    const day = addDays(monday, index);
    const session = sessions.find((candidate) => candidate.day === day);
    const state: WeekDayState = session ? "met" : day === today ? "today" : day > today ? "future" : "missed";
    const said = `${letter}, ${session ? session.day_name : day > today ? t("today.to_come") : t("today.no_workout")}`;
    return { day, state, kind: session?.kind, today: day === today, said };
  });
  return <WeekDots size="large" label={t("today.week_label", { days: days.map((one) => one.said).join("; ") })} days={days} />;
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
  const t = useT();
  const [confirming, setConfirming] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);

  const { plan, next, in_progress, rotation } = today;
  if (!plan) {
    return (
      <div className="training-next">
        <p className="training-next-name">{t("today.no_plan")}</p>
        <p className="training-next-label">{t("today.no_plan_hint")}</p>
        {onOpenPlan && (
          <Button variant="primary" icon="plus" onClick={onOpenPlan}>
            {t("today.create_plan")}
          </Button>
        )}
      </div>
    );
  }
  if (!next) return <p className="widget-note">{t("today.plan_without_days")}</p>;

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
          : t("today.start_offline_failed"),
      );
    }
  }

  return (
    <div className="training-next" data-kind={target.kind}>
      <p className="training-next-label">
        {in_progress ? t("common.ongoing_title") : pick && pick.plan_day_id !== next.plan_day_id ? t("today.chosen") : t("today.due")}
        {" · "}
        {t("today.rotation_day", { rotation: next.rotation_number, day: done + 1, days: next.days_in_rotation })}
      </p>
      <p className="training-next-name">
        <IconBadge
          name={ICON_OF_KIND[target.kind]}
          hue={HUE_OF_KIND[target.kind] as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8}
        />
        <span>{in_progress ? t("today.half_done") : target.name}</span>
      </p>
      {in_progress ? (
        <Button variant="primary" onClick={() => onOpenSession(in_progress)}>
          {t("today.continue")}
        </Button>
      ) : (
        <>
          <Inline>
            <Button variant="primary" onClick={() => setConfirming(true)}>
              {t("today.start_named", { name: target.name })}
            </Button>
            {rotation && rotation.days.length > 1 && (
              <Button variant="plain" size="small" onClick={() => setConfirming(true)}>
                {t("today.other_day")}
              </Button>
            )}
          </Inline>
        </>
      )}
      {confirming && (
        <ConfirmStartSheet
          name={target.name}
          detail={rotationDetail(t, next.rotation_number, done + 1, next.days_in_rotation)}
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
