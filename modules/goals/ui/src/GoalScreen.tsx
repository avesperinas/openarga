import { useResource } from "@openarga/app";
import {
  Button,
  DateField,
  EmptyState,
  ErrorState,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  parseDecimal,
  Screen,
  Section,
  Skeleton,
  StatRow,
  StatTile,
  TextField,
  TrendChart,
  type TrendPoint,
  useT,
  useToast,
  YearCalendar,
} from "@openarga/ui";
import { useState } from "react";

import {
  type Goal,
  type GoalDetail,
  changed,
  checkGoal,
  closeGoal,
  readGoal,
  reopenGoal,
  uncheckGoal,
} from "./api";
import { GoalSheet } from "./GoalSheet";
import { figure, frequency, shortDate, standing, subtitle, unitWord, weekLabel } from "./goalWords";
import { ScreenHeader } from "./Header";
import { Problem, useBusy } from "./Parts";
import { capital, longDate, todayIso } from "./words";

export function chartPoints(detail: GoalDetail): TrendPoint[] {
  const { goal, history } = detail;
  const withValue = history.filter((point) => point.value !== null && point.day >= goal.start_on);
  if (goal.metric?.kind !== "amount") {
    return history.filter((point) => point.value !== null).map((point) => ({ day: point.day, value: point.value! }));
  }
  let total = goal.start ?? 0;
  return withValue.map((point) => {
    total += point.value!;
    return { day: point.day, value: total };
  });
}

const asksValueOf = (goal: Goal) => (goal.kind === "dated" ? goal.target !== null : goal.period === "week");

export function GoalScreen({ id, onBack }: { id: string; onBack: () => void }) {
  const t = useT();
  const found = useResource(`goal:${id}`, () => readGoal(id), { persist: true });
  const detail = found.data ?? null;
  const missing = Boolean(found.error?.message.includes(id));
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [day, setDay] = useState(todayIso());
  const { busy, error: failed, run } = useBusy();
  const toast = useToast();
  const today = todayIso();

  const load = changed;

  const back = { label: t("goals.title"), onClick: onBack };
  if (missing) {
    return (
      <Screen>
        <ScreenHeader back={back} />
        <EmptyState icon="alert" title={t("goal.missing")} action={{ label: t("goal.back"), onClick: onBack }}>
          <p>{found.error?.message}</p>
        </EmptyState>
      </Screen>
    );
  }
  if (!detail) {
    return (
      <Screen>
        <ScreenHeader back={back} />
        <OfflineNotice />
        {found.error ? (
          <ErrorState detail={found.error.message} onRetry={found.refresh} />
        ) : (
          <Skeleton rows={5} />
        )}
      </Screen>
    );
  }

  const { goal, history } = detail;
  const unit = goal.metric?.unit ?? null;
  const said = standing(t, goal);
  const active = goal.status === "active";
  const manual = history
    .filter((point) => point.manual)
    .reverse()
    .slice(0, goal.kind === "periodic" && !asksValueOf(goal) ? 10 : 60);
  const asksValue = asksValueOf(goal);

  const act = (action: () => Promise<Goal>, message: string) =>
    void run(async () => {
      await action();
      toast({ message });
      load();
    }, t("goal.failed"));

  const log = () =>
    void run(async () => {
      const amount = parseDecimal(value);
      if (amount === null) throw new Error(t("goal.write_figure"));
      await checkGoal(goal.id, { day, value: amount });
      setValue("");
      load();
    }, t("goal.log_failed"));

  return (
    <Screen>
      <ScreenHeader back={back} eyebrow={subtitle(t, goal, today)} title={goal.title} />
      <OfflineNotice />

      {goal.kind === "periodic" ? (
        <StatRow label={t("goals.how")}>
          <StatTile
            label={t("goal.streak")}
            value={t(goal.streak_unit === "weeks" ? "goal.streak_weeks" : "goal.streak_days", { count: goal.streak ?? 0 })}
            foot={goal.streak_unit === "weeks" ? t("goal.streak_weeks_foot") : t("goal.streak_days_foot")}
            tone={goal.streak ? "positive" : "neutral"}
          />
          <StatTile
            label={t("goal.this_week")}
            value={weekLabel(t, goal).replace(t("week.suffix"), "")}
            foot={goal.week_met ? t("standing.achieved") : frequency(t, goal)}
            tone={goal.week_met ? "positive" : "neutral"}
            progress={goal.week_target ? (goal.week_count ?? 0) / goal.week_target : null}
          />
          <StatTile
            label={t("goal.constancy")}
            value={goal.constancy === null ? "—" : t("goal.percent", { value: Math.round(goal.constancy * 100) })}
            foot={t("goal.last_4_weeks")}
          />
        </StatRow>
      ) : goal.target !== null ? (
        <StatRow label={t("goals.how")}>
          <StatTile
            label={active ? t("goal.now") : t("goal.at_close")}
            value={figure(t, active ? goal.current : goal.closed_value, unit)}
            foot={said.text}
            tone={said.tone}
            progress={goal.progress}
          />
          <StatTile
            label={t("goal.target")}
            value={figure(t, goal.target, unit)}
            foot={goal.due_on ? `${shortDate(goal.due_on, today)}${active && goal.days_left !== null ? ` · ${t("goal.days_left", { count: goal.days_left })}` : ""}` : undefined}
          />
          {active && (
            <StatTile
              label={t("goal.if_you_go_on")}
              value={goal.projection === null ? "—" : figure(t, goal.projection, unit)}
              foot={
                goal.projection === null
                  ? t("goal.needs_two_points")
                  : goal.projection_reached
                    ? t("goal.reach")
                    : t("goal.miss")
              }
              tone={goal.projection === null ? "neutral" : goal.projection_reached ? "positive" : "negative"}
            />
          )}
        </StatRow>
      ) : (
        <StatRow label={t("goals.how")}>
          <StatTile label={t("standing.milestone")} value={said.text} tone={said.tone} foot={goal.due_on ? shortDate(goal.due_on, today) : undefined} />
        </StatRow>
      )}

      {goal.kind === "periodic" ? (
        <Section title={t("goal.every_day")}>
          <YearCalendar
            label={t("goal.days_met", { title: goal.title })}
            days={history.map((point) => ({ day: point.day, value: point.met ? 1 : 0 }))}
            end={today}
            goal={1}
            format={(one) => (one >= 1 ? t("goal.met") : t("goal.not_met"))}
          />
        </Section>
      ) : goal.target !== null && chartPoints(detail).length > 0 ? (
        <Section title={goal.metric ? goal.metric.label : t("goal.logged")}>
          <TrendChart
            label={goal.title}
            points={chartPoints(detail)}
            band={goal.direction === "at_least" ? { low: goal.target } : { high: goal.target }}
            valueName={goal.metric?.kind === "amount" ? t("goal.summed") : t("goal.value")}
            format={(one) => figure(t, one, unit)}
          />
        </Section>
      ) : null}

      {active && goal.kind === "periodic" && goal.period === "day" && (
        <Section title={t("goal.today")}>
          <div className="goals-row-actions">
            <Button
              icon="done"
              variant={goal.today_met ? "secondary" : "primary"}
              onClick={() =>
                act(() => checkGoal(goal.id, { done: !goal.today_met }), goal.today_met ? t("goal.today_not_toast") : t("goal.done_today"))
              }
            >
              {goal.today_met ? t("goal.today_not") : t("goal.done_today")}
            </Button>
          </div>
        </Section>
      )}

      {active && asksValue && (
        <Section title={goal.metric ? t("goal.log_by_hand") : t("goal.log_where")}>
          <div className="goals-form">
            <TextField
              label={unitWord(t, unit) ? t("goal.figure_unit", { unit: unitWord(t, unit) }) : t("goal.figure")}
              value={value}
              inputMode="decimal"
              onChange={setValue}
              onSubmit={log}
            />
            <DateField label={t("task.day")} value={day} max={today} onChange={(one) => one && setDay(one)} />
            <Button icon="plus" disabled={busy || !value.trim()} onClick={log}>
              {t("goal.log")}
            </Button>
          </div>
        </Section>
      )}

      {active && goal.kind === "dated" && goal.target === null && (
        <Button icon="done" block onClick={() => act(() => checkGoal(goal.id, { done: true }), t("goal.milestone_done"))}>
          {t("goal.already_done")}
        </Button>
      )}

      {manual.length > 0 && (
        <Section title={t("goal.logged_by_hand")}>
          <List>
            {manual.map((point) => (
              <ListRow
                key={point.day}
                title={capital(longDate(point.day))}
                value={point.value !== null ? figure(t, point.value, unit) : point.done ? t("goal.done") : t("goal.no")}
                subtitle={point.note ?? undefined}
                action={
                  active
                    ? {
                        icon: "undo",
                        label: t("goal.remove_logged", { day: point.day }),
                        onClick: () => act(() => uncheckGoal(goal.id, point.day), t("goal.removed")),
                      }
                    : undefined
                }
              />
            ))}
          </List>
        </Section>
      )}

      {goal.note && (
        <Section title={t("goal.note")}>
          <Hint>{goal.note}</Hint>
        </Section>
      )}

      <div className="goals-row-actions">
        <Button icon="edit" variant="secondary" onClick={() => setEditing(true)}>
          {t("goal.edit")}
        </Button>
        {active ? (
          <>
            {goal.kind === "dated" && (
              <Button variant="secondary" icon="done" onClick={() => act(() => closeGoal(goal.id, "achieved"), t("standing.achieved"))}>
                {t("goal.mark_achieved")}
              </Button>
            )}
            <Button variant="secondary" icon="close" onClick={() => act(() => closeGoal(goal.id, "abandoned"), t("standing.abandoned"))}>
              {t("goal.abandon")}
            </Button>
          </>
        ) : (
          <Button variant="secondary" icon="undo" onClick={() => act(() => reopenGoal(goal.id), t("goal.reopened"))}>
            {t("goal.reopen")}
          </Button>
        )}
      </div>
      <Problem error={failed} />

      {editing && (
        <GoalSheet
          goal={goal}
          today={today}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setEditing(false);
            if (saved) load();
            else {
              changed();
              onBack();
            }
          }}
        />
      )}
    </Screen>
  );
}
