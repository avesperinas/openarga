import { mutate, useResource } from "@openarga/app";
import {
  Card,
  CreateButton,
  EmptyState,
  Figures,
  ErrorState,
  GoalRow,
  GroupLabel,
  OfflineNotice,
  Screen,
  SegmentedControl,
  Skeleton,
  useT,
  useToast,
} from "@openarga/ui";
import { useState } from "react";

import { type Goal, changed, checkGoal, readGoals } from "./api";
import { GoalSheet } from "./GoalSheet";
import {
  type GoalView,
  against,
  byCategory,
  byDate,
  current,
  goalFigures,
  standing,
  subtitle,
  tickable,
  weekLabel,
} from "./goalWords";
import { ScreenHeader } from "./Header";
import { useCategories } from "./Parts";
import { capital, longDate, todayIso } from "./words";

const VIEW_KEY = "goals.goals.view";

function rememberedView(): GoalView {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "date" ? "date" : "category";
  } catch {
    return "category";
  }
}


export function GoalItem({
  goal,
  today,
  withCategory,
  onOpen,
  onTick,
}: {
  goal: Goal;
  today: string;
  withCategory: boolean;
  onOpen: () => void;
  onTick?: () => void;
}) {
  const t = useT();
  const { tone, text } = standing(t, goal);
  const dated = goal.kind === "dated" && goal.target !== null;
  return (
    <GoalRow
      title={goal.title}
      subtitle={subtitle(t, goal, today, withCategory)}
      hue={goal.hue}
      tone={tone}
      status={text}
      figure={current(t, goal) ?? undefined}
      against={against(t, goal, today) ?? undefined}
      progress={dated ? goal.progress : undefined}
      expected={
        dated && goal.status === "active" && goal.expected !== null && goal.start !== null && goal.target !== goal.start
          ? (goal.expected - goal.start) / (goal.target! - goal.start)
          : undefined
      }
      week={goal.kind === "periodic" ? goal.week : undefined}
      weekLabel={goal.kind === "periodic" ? weekLabel(t, goal) : undefined}
      check={
        onTick && tickable(goal) && goal.status === "active"
          ? { checked: goal.today_met === true, label: t("goals.done_today_label", { title: goal.title }), onClick: onTick }
          : undefined
      }
      onOpen={onOpen}
    />
  );
}

export const GOALS = "goals";

export function GoalsScreen({ onOpen }: { onOpen: (id: string) => void }) {
  const t = useT();
  const { list: categories } = useCategories();
  const found = useResource(GOALS, readGoals, { persist: true });
  const goals = found.data ?? null;
  const setGoals = (next: (list: Goal[] | undefined) => Goal[]) => void mutate<Goal[]>(GOALS, next);
  const [view, setView] = useState<GoalView>(rememberedView);
  const [creating, setCreating] = useState(false);
  const toast = useToast();
  const today = todayIso();

  const load = changed;

  const changeView = (next: GoalView) => {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
    }
  };

  const tick = (goal: Goal) => {
    const done = goal.today_met !== true;
    setGoals((list) => list?.map((one) => (one.id === goal.id ? { ...one, today_met: done } : one)) ?? []);
    checkGoal(goal.id, { done })
      .then((saved) => {
        setGoals((list) => list?.map((one) => (one.id === goal.id ? saved : one)) ?? []);
        changed();
        if (done && saved.streak && saved.streak > 1) {
          const unit = saved.streak_unit === "weeks" ? "weeks" : "days";
          toast({ message: t(`goals.streak_toast_${unit}`, { title: goal.title, count: saved.streak ?? 0 }) });
        }
      })
      .catch((reason: unknown) => {
        load();
        toast({ message: reason instanceof Error ? reason.message : t("goals.tick_failed"), tone: "error" });
      });
  };

  const groups = goals ? (view === "date" ? byDate(t, goals) : byCategory(t, goals, categories)) : [];

  return (
    <Screen>
      <ScreenHeader eyebrow={capital(longDate(today))} title={t("goals.title")} />
      <OfflineNotice />

      {!goals && found.error ? (
        <ErrorState title={t("app.not_answering")} detail={found.error.message} onRetry={found.refresh} />
      ) : !goals ? (
        <Skeleton rows={4} />
      ) : goals.length === 0 ? (
        <EmptyState
          icon="target"
          hue={2}
          title={t("goals.empty")}
          action={{ label: t("goals.set_one"), icon: "plus", onClick: () => setCreating(true) }}
        >
          <p>{t("goals.empty_detail")}</p>
        </EmptyState>
      ) : (
        <>
          <Card>
            <Figures label={t("goals.how")} items={goalFigures(t, goals)} />
          </Card>
          <SegmentedControl<GoalView>
            label={t("home.sort")}
            options={[
              { value: "category", label: t("home.by_category") },
              { value: "date", label: t("home.by_date") },
            ]}
            value={view}
            onChange={changeView}
          />
          {groups.map((group) => (
            <section key={group.id} className="goals-group" aria-label={group.label}>
              <GroupLabel count={group.goals.length}>{group.label}</GroupLabel>
              <div className="goals-goals">
                {group.goals.map((goal) => (
                  <GoalItem
                    key={goal.id}
                    goal={goal}
                    today={today}
                    withCategory={view === "date"}
                    onOpen={() => onOpen(goal.id)}
                    onTick={() => tick(goal)}
                  />
                ))}
              </div>
            </section>
          ))}
        </>
      )}

      <CreateButton label={t("goals.goal")} onClick={() => setCreating(true)} />

      {creating && (
        <GoalSheet
          today={today}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            load();
          }}
        />
      )}
    </Screen>
  );
}
