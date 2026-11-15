import { Button, CreateButton, EmptyState, GroupLabel, Hint, Icon, type IconName, List, ListRow, OfflineNotice, Panes, Screen, Tile, Tiles, useToast } from "@openarga/ui";
import { useState } from "react";

import { type Assessment, type Course, type Session, api } from "./api";
import { useNavigate } from "./App";
import { AppVersion } from "./AppVersion";
import { Pending, Problem, Section, dueTone, useLoad } from "./Bits";
import { AddSheet } from "./AddSheet";
import { CourseSheet } from "./CourseSheet";
import { ScreenHeader } from "./Header";
import {
  ASSESSMENT_KINDS,
  countdown,
  dateShort,
  dayTitle,
  grade,
  hhmm,
  isoDate,
  labelOf,
  sessionMoment,
  todayIso,
} from "./words";
import { t } from "./lang";

const hueOf = (tone: number) => (((tone - 1) % 8) + 1) as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

const ICON: Record<string, IconName> = { master: "bookmark", degree: "bookmark", course: "book", language: "globe", certification: "target" };

export function courseFace(course: Course, today: string): { figure?: string; caption?: string; detail?: string } {
  if (course.tracks.includes("grades")) {
    const average = course.average.average ?? course.grade?.current ?? null;
    return { figure: grade(average, course.scale_max), caption: t("home.average"), detail: course.progress?.label };
  }
  if (course.ends_on && course.ends_on >= today) {
    const left = Math.round((new Date(`${course.ends_on}T12:00:00`).getTime() - new Date(`${today}T12:00:00`).getTime()) / 86_400_000);
    return {
      figure: left === 0 ? t("home.today") : t(left === 1 ? "home.days.one" : "home.days.other", { count: left }),
      caption: t("home.until", { date: dateShort(course.ends_on) }),
      detail: course.institution ?? undefined,
    };
  }
  const next = course.next_session
    ? t("home.next", { date: dateShort(isoDate(new Date(course.next_session.starts_at))) })
    : null;
  return { detail: [course.institution, next].filter(Boolean).join(" · ") || undefined };
}

export function HomeScreen() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [adding, setAdding] = useState(false);
  const { data, found, problem, fail, refresh } = useLoad("home:", () => api.home());
  const toast = useToast();
  const today = todayIso();

  const done = (item: Assessment, status: "pending" | "submitted") =>
    void api
      .gradeAssessment(item.id, null, status)
      .then(() => {
        void refresh();
        if (status === "submitted")
          toast({
            message: t("home.submitted_toast", { title: item.title }),
            action: { label: t("action.undo"), run: () => done(item, "pending") },
          });
      })
      .catch(fail);

  const tasks = (data?.upcoming ?? []).filter((one) => one.status === "pending");
  const days = (data?.days ?? []).filter((day) => day.date >= today && (day.sessions.length > 0 || day.assessments.length > 0));

  const main = data && (
    <>
      <Section title={t("home.your_courses")} count={data.courses.length}>
        <Tiles label={t("home.your_courses")}>
          {data.courses.map((course) => (
            <Tile
              key={course.id}
              title={course.name}
              hue={hueOf(course.tone)}
              glyph={<Icon name={ICON[course.kind] ?? "book"} />}
              {...courseFace(course, today)}
              onOpen={() => navigate({ tab: "course", id: course.id })}
            />
          ))}
        </Tiles>
      </Section>
      {tasks.length > 0 && (
        <Section title={t("home.to_do")} count={tasks.length}>
          <List>
            {tasks.map((item) => (
              <ListRow
                key={item.id}
                title={item.title}
                subtitle={[item.course, item.due_on ? dateShort(item.due_on) : null, item.due_time ? hhmm(item.due_time) : null].filter(Boolean).join(" · ")}
                detail={countdown(item.days_left ?? 0)}
                tone={dueTone(item.days_left ?? 0)}
                onClick={() => navigate({ tab: "assessment", id: item.id })}
                action={{ icon: "done", kind: "check", label: t("home.done_label", { title: item.title }), onClick: () => done(item, "submitted") }}
              />
            ))}
          </List>
        </Section>
      )}
      {data.archived > 0 && (
        <List>
          <ListRow
            title={t("home.archived", { count: data.archived })}
            icon="box"
            accessory="chevron-right"
            onClick={() => navigate({ tab: "archive" })}
          />
        </List>
      )}
      <Button variant="plain" icon="plus" onClick={() => setCreating(true)}>
        {t("home.new_course")}
      </Button>
    </>
  );

  const aside = data && (
    <Section title={t("home.this_week")}>
      {days.length === 0 ? (
        <Hint>{t("home.nothing_soon")}</Hint>
      ) : (
        days.map((day) => (
          <div key={day.date} className="study-agenda">
            <GroupLabel>{day.today ? t("home.today_is", { day: dayTitle(day.date) }) : dayTitle(day.date)}</GroupLabel>
            <List>
              {day.assessments.map((item) => (
                <AgendaDeadline key={item.id} item={item} onOpen={() => navigate({ tab: "assessment", id: item.id })} />
              ))}
              {day.sessions.map((session) => (
                <AgendaSession key={session.id} session={session} onOpen={() => navigate({ tab: "session", id: session.id })} />
              ))}
            </List>
          </div>
        ))
      )}
      <Button variant="plain" icon="calendar" onClick={() => window.location.assign("/planner/")}>
        {t("home.see_in_calendar")}
      </Button>
    </Section>
  );

  return (
    <Screen wide>
      <ScreenHeader eyebrow={dayTitle(today)} title={t("app.name")} />
      <OfflineNotice />
      <Problem text={problem} />
      {data === null && <Pending found={found} />}

      {data && data.courses.length === 0 && (
        <EmptyState
          icon="book"
          hue={5}
          title={t("home.empty")}
          action={{ label: t("home.create"), icon: "plus", onClick: () => setCreating(true) }}
        >
          <p>{t("home.empty_detail")}</p>
          <p>{t("home.empty_claude")}</p>
        </EmptyState>
      )}

      {data && data.courses.length > 0 && <Panes main={main} aside={aside} asideLabel={t("home.this_week")} />}
      {data && data.courses.length > 0 && <CreateButton label={t("home.add")} onClick={() => setAdding(true)} />}

      <AppVersion />

      {adding && data && (
        <AddSheet
          courses={data.courses}
          onClose={() => setAdding(false)}
          onSaved={(message, open) => {
            setAdding(false);
            void refresh();
            toast({ message });
            if (open) navigate(open);
          }}
        />
      )}
      {creating && (
        <CourseSheet
          course={null}
          onClose={() => setCreating(false)}
          onSaved={(detail) => {
            setCreating(false);
            void refresh();
            navigate({ tab: "course", id: detail.course.id });
          }}
          onError={fail}
        />
      )}
    </Screen>
  );
}

function AgendaSession({ session, onOpen }: { session: Session; onOpen: () => void }) {
  const moment = sessionMoment(session);
  const where = [session.place, session.title !== session.course ? session.course : null].filter(Boolean).join(" · ");
  const cancelled = session.status === "cancelled";
  return (
    <ListRow
      title={session.title}
      subtitle={[
        cancelled ? t("session.cancelled") : t("session.until", { time: hhmm(new Date(session.ends_at).toTimeString()) }),
        cancelled ? null : where,
        session.has_notes ? t("session.with_notes") : null,
      ]
        .filter(Boolean)
        .join(" · ")}
      detail={
        moment === "now" && !cancelled
          ? t("session.now")
          : session.attendance === "present"
            ? t("session.went")
            : session.attendance === "absent"
              ? t("session.missed")
              : undefined
      }
      value={hhmm(new Date(session.starts_at).toTimeString())}
      tone={cancelled ? "negative" : moment === "now" ? "warning" : session.attendance === "present" ? "positive" : undefined}
      onClick={onOpen}
    />
  );
}

function AgendaDeadline({ item, onOpen }: { item: Assessment; onOpen: () => void }) {
  return (
    <ListRow
      title={`${labelOf(ASSESSMENT_KINDS, item.kind)}: ${item.title}`}
      subtitle={item.subject ?? item.course}
      detail={item.status === "submitted" ? t("assessment.submitted") : item.status === "graded" ? grade(item.grade, item.scale_max) : undefined}
      value={item.due_time ? hhmm(item.due_time) : t("assessment.all_day")}
      tone={
        item.status === "submitted"
          ? "positive"
          : item.status === "graded"
            ? item.grade !== null && item.min_grade !== null && item.grade < item.min_grade
              ? "negative"
              : undefined
            : item.days_left !== null
              ? dueTone(item.days_left)
              : undefined
      }
      onClick={onOpen}
    />
  );
}


