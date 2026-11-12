import {
  Card,
  type DayMark,
  Figures,
  Heading,
  isoDay,
  List,
  ListRow,
  Hint,
  MonthCalendar,
  Notice,
  Panes,
  Screen,
  Section,
  SegmentedControl,
  Switch,
  YearCalendar,
  type Locale,
  useLocale,
  useT,
} from "@openarga/ui";
import { peek, remember } from "@openarga/app";
import { useEffect, useMemo, useState } from "react";

import { type Activity, type SessionSummary, listActivities, listSessions, readToday } from "./api";
import { ActivityList, ActivitySheet } from "./Activities";
import { AppVersion } from "./AppVersion";
import { ScreenHeader } from "./Header";
import { HUE_OF_KIND, formatDuration, plural, shortDate } from "./labels";

const SHOW_ACTIVITIES = "training:calendar-activities";

function useShowActivities(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(() => {
    try {
      return window.localStorage.getItem(SHOW_ACTIVITIES) !== "false";
    } catch {
      return true;
    }
  });
  const set = (next: boolean) => {
    setOn(next);
    try {
      window.localStorage.setItem(SHOW_ACTIVITIES, String(next));
    } catch {
    }
  };
  return [on, set];
}

const SINCE = "2000-01-01";

type Loaded = { sessions: SessionSummary[]; goal: number; activities?: Activity[] };

export interface HistoryScreenProps {
  onOpenSession: (id: string) => void;
  now?: Date;
  initial?: Loaded;
}

export function HistoryScreen({ onOpenSession, now = new Date(), initial }: HistoryScreenProps) {
  const t = useT();
  const locale = useLocale();
  const [loaded, setLoaded] = useState<Loaded | null>(() => initial ?? peek<Loaded>("history") ?? null);
  const [failed, setFailed] = useState(false);
  const [cursor, setCursor] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<"month" | "list">("month");
  const today = isoDay(now);

  useEffect(() => {
    if (initial) return;
    Promise.all([listSessions(SINCE, today), readToday(), listActivities(SINCE, today).catch(() => [])])
      .then(([sessions, current, activities]) => {
        const fresh = { sessions, goal: current.settings.weekly_goal, activities };
        remember("history", fresh);
        setLoaded(fresh);
      })
      .catch(() => setFailed(true));
  }, [initial, today]);

  const sessions = loaded?.sessions ?? [];
  const [showActivities, setShowActivities] = useShowActivities();
  const activities = useMemo(() => (showActivities ? (loaded?.activities ?? []) : []), [loaded, showActivities]);
  const [openActivity, setOpenActivity] = useState<Activity | null>(null);
  const marks = useMemo(() => marksOf(sessions, activities), [sessions, activities]);
  const monthKey = `${cursor.year}-${String(cursor.month + 1).padStart(2, "0")}`;
  const activitiesShown = activities.filter((activity) =>
    selected ? activity.day === selected : activity.day.startsWith(monthKey),
  );
  const inMonth = sessions.filter((session) => session.day.startsWith(monthKey));
  const shown = selected ? sessions.filter((session) => session.day === selected) : inMonth;
  const stats = monthStats(inMonth);

  const step = (delta: number) => {
    setSelected(null);
    setCursor(({ year, month }) => {
      const date = new Date(year, month + delta, 1);
      return { year: date.getFullYear(), month: date.getMonth() };
    });
  };

  return (
    <Screen wide>
      <ScreenHeader title={t("tabs.calendar")} />

      {failed && <Notice tone="negative">{t("history.load_failed")}</Notice>}

      <SegmentedControl
        label={t("history.view")}
        value={view}
        onChange={setView}
        options={[
          { value: "month", label: t("history.month") },
          { value: "list", label: t("history.list") },
        ]}
      />

      {view === "month" ? (
        <Panes
          asideLabel={t("history.aside")}
          main={
            <>
              <Card label={t("history.the_month")}>
                <Figures
                  items={[
                    { label: plural(t, "history.workouts", stats.count), value: stats.count },
                    { label: t("history.in_total"), value: hours(stats.totalSeconds) },
                    { label: t("history.sets"), value: stats.sets },
                  ]}
                />
                <MonthCalendar
                  year={cursor.year}
                  month={cursor.month}
                  marks={marks}
                  today={today}
                  selected={selected}
                  onSelect={(day) => setSelected(selected === day ? null : day)}
                  onPrevious={() => step(-1)}
                  onNext={() => step(1)}
                  weekBelow={(monday) => weekBelow(monday, sessions, loaded?.goal ?? 0, today)}
                  weekLabel={(monday) => rotationOf(monday, sessions)}
                />
                <div className="training-switch-row">
                  <span>{t("history.show_activities")}</span>
                  <Switch label={t("history.show_activities")} checked={showActivities} onChange={setShowActivities} />
                </div>
              </Card>

              <SessionList
                title={selected ? dayTitle(selected, locale) : t("history.this_month")}
                sessions={shown}
                empty={
                  sessions.length === 0
                    ? t("history.empty")
                    : selected
                      ? t("history.empty_day")
                      : t("history.empty_month")
                }
                onOpenSession={onOpenSession}
              />
            </>
          }
          aside={
            <>
              {sessions.length > 0 && (
                <Section title={t("history.last_year")}>
                  <Card>
                    <YearCalendar
                      days={yearDays(sessions, today)}
                      label={t("history.year_label")}
                      end={today}
                      format={(value) => plural(t, "common.sets", value)}
                    />
                  </Card>
                </Section>
              )}

              {activitiesShown.length > 0 && (
                <section className="training-history" aria-label={t("today.activities")}>
                  <Heading>{t("today.activities")}</Heading>
                  <ActivityList activities={activitiesShown} onOpen={setOpenActivity} />
                </section>
              )}
            </>
          }
        />
      ) : (
        <SessionList
          title={t("history.all")}
          sessions={sessions}
          grouped
          empty={t("history.empty_list")}
          onOpenSession={onOpenSession}
        />
      )}
      {openActivity && (
        <ActivitySheet
          activity={openActivity}
          onClose={() => setOpenActivity(null)}
          onChanged={(changed) => {
            setOpenActivity(null);
            setLoaded((previous) =>
              previous
                ? { ...previous, activities: (previous.activities ?? []).map((a) => (a.id === changed.id ? changed : a)) }
                : previous,
            );
          }}
          onRemoved={(id) => {
            setOpenActivity(null);
            setLoaded((previous) =>
              previous ? { ...previous, activities: (previous.activities ?? []).filter((a) => a.id !== id) } : previous,
            );
          }}
        />
      )}

      <AppVersion />
    </Screen>
  );
}

export function marksOf(sessions: SessionSummary[], activities: Activity[] = []): Record<string, DayMark[]> {
  const marks: Record<string, DayMark[]> = {};
  for (const session of [...sessions].reverse()) {
    (marks[session.day] ??= []).push({
      kind: session.kind,
      label: `${session.day_name}, ${formatDuration(session.duration_seconds)}`,
    });
  }
  for (const activity of [...activities].reverse()) {
    (marks[activity.day] ??= []).push({ kind: "activity", label: activity.name });
  }
  return marks;
}

export function monthStats(sessions: SessionSummary[]) {
  const finished = sessions.filter((session) => session.duration_seconds !== null);
  const total = finished.reduce((sum, session) => sum + (session.duration_seconds ?? 0), 0);
  return {
    count: sessions.length,
    sets: sessions.reduce((sum, session) => sum + session.sets, 0),
    averageSeconds: finished.length ? Math.round(total / finished.length) : null,
    totalSeconds: total,
  };
}

export function hours(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

export function rotationOf(monday: string, sessions: SessionSummary[]): string | null {
  const [year, month, day] = monday.split("-").map(Number) as [number, number, number];
  const sunday = isoDay(new Date(year, month - 1, day + 6));
  const inWeek = sessions.filter((session) => session.day >= monday && session.day <= sunday);
  const first = inWeek.sort((a, b) => a.started_at.localeCompare(b.started_at))[0];
  return first ? `R${first.rotation_number}` : null;
}

export function yearDays(sessions: SessionSummary[], today: string): { day: string; value: number }[] {
  const byDay = new Map<string, number>();
  for (const session of sessions) byDay.set(session.day, (byDay.get(session.day) ?? 0) + session.sets);
  const first = sessions.reduce((min, session) => (session.day < min ? session.day : min), today);
  const [year, month, day] = today.split("-").map(Number) as [number, number, number];
  const out: { day: string; value: number }[] = [];
  for (let back = 0; back < 371; back++) {
    const current = isoDay(new Date(year, month - 1, day - back));
    if (current < first) break;
    out.push({ day: current, value: byDay.get(current) ?? 0 });
  }
  return out.reverse();
}

export function weekBelow(monday: string, sessions: SessionSummary[], goal: number, today: string): boolean {
  if (goal <= 0 || sessions.length === 0) return false;
  const [year, month, day] = monday.split("-").map(Number) as [number, number, number];
  const sunday = isoDay(new Date(year, month - 1, day + 6));
  const first = sessions[sessions.length - 1]!.day;
  if (sunday >= today || sunday < first) return false;
  const done = sessions.filter((s) => s.ended_at !== null && s.day >= monday && s.day <= sunday).length;
  return done < goal;
}

function dayTitle(day: string, locale: Locale): string {
  const [year, month, date] = day.split("-").map(Number) as [number, number, number];
  const text = new Date(year, month - 1, date).toLocaleDateString(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function monthTitle(day: string, locale: Locale): string {
  const [year, month] = day.split("-").map(Number) as [number, number];
  const text = new Date(year, month - 1, 1).toLocaleDateString(locale, { month: "long", year: "numeric" });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

interface SessionListProps {
  title: string;
  sessions: SessionSummary[];
  empty: string;
  grouped?: boolean;
  onOpenSession: (id: string) => void;
}

function SessionList({ title, sessions, empty, grouped = false, onOpenSession }: SessionListProps) {
  const t = useT();
  const locale = useLocale();
  if (sessions.length === 0) {
    return (
      <section className="training-history" aria-label={title}>
        <Heading>{title}</Heading>
        <Card>
          <Hint>{empty}</Hint>
        </Card>
      </section>
    );
  }

  const groups = new Map<string, SessionSummary[]>();
  for (const session of sessions) {
    const key = grouped ? monthTitle(session.day, locale) : title;
    groups.set(key, [...(groups.get(key) ?? []), session]);
  }

  return (
    <>
      {[...groups.entries()].map(([group, items]) => (
        <section key={group} className="training-history" aria-label={group}>
          <Heading>{group}</Heading>
          <List>
            {items.map((session) => (
              <ListRow
                key={session.id}
                hue={HUE_OF_KIND[session.kind]}
                title={session.day_name}
                subtitle={[
                  shortDate(session.day, locale),
                  session.ended_at ? formatDuration(session.duration_seconds) : t("common.ongoing"),
                  plural(t, "common.sets", session.sets),
                ]
                  .filter(Boolean)
                  .join(" · ")}
                accessory="chevron-right"
                onClick={() => onOpenSession(session.id)}
              />
            ))}
          </List>
        </section>
      ))}
    </>
  );
}
