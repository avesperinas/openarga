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
  standing,
  subtitle,
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

export const tickable = (goal: Goal) => goal.kind === "periodic" && goal.period === "day";

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
  const { tone, text } = standing(goal);
  const dated = goal.kind === "dated" && goal.target !== null;
  return (
    <GoalRow
      title={goal.title}
      subtitle={subtitle(goal, today, withCategory)}
      hue={goal.hue}
      tone={tone}
      status={text}
      figure={current(goal) ?? undefined}
      against={against(goal, today) ?? undefined}
      progress={dated ? goal.progress : undefined}
      expected={
        dated && goal.status === "active" && goal.expected !== null && goal.start !== null && goal.target !== goal.start
          ? (goal.expected - goal.start) / (goal.target! - goal.start)
          : undefined
      }
      week={goal.kind === "periodic" ? goal.week : undefined}
      weekLabel={goal.kind === "periodic" ? weekLabel(goal) : undefined}
      check={
        onTick && tickable(goal) && goal.status === "active"
          ? { checked: goal.today_met === true, label: `Hecho hoy: ${goal.title}`, onClick: onTick }
          : undefined
      }
      onOpen={onOpen}
    />
  );
}

export const GOALS = "goals";

export function goalFigures(goals: Goal[]) {
  const periodic = goals.filter((goal) => tickable(goal));
  const done = periodic.filter((goal) => goal.today_met).length;
  const behind = goals.filter((goal) => goal.pace === "behind").length;
  const best = goals.reduce<Goal | null>((top, goal) => ((goal.streak ?? 0) > (top?.streak ?? 0) ? goal : top), null);
  return [
    { label: "hechas hoy", value: periodic.length ? `${done}/${periodic.length}` : "–", lit: periodic.length > 0 && done === periodic.length },
    { label: "por detrás", value: behind, muted: behind === 0 },
    {
      label: best?.streak ? `racha (${best.streak_unit === "weeks" ? "semanas" : "días"})` : "racha",
      value: best?.streak ?? 0,
    },
  ];
}

export function GoalsScreen({ onOpen }: { onOpen: (id: string) => void }) {
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
          const unit = saved.streak_unit === "weeks" ? "semanas" : "días";
          toast({ message: `${goal.title} · ${saved.streak} ${unit} seguidos` });
        }
      })
      .catch((reason: unknown) => {
        load();
        toast({ message: reason instanceof Error ? reason.message : "No se ha podido marcar", tone: "error" });
      });
  };

  const groups = goals ? (view === "date" ? byDate(goals) : byCategory(goals, categories)) : [];

  return (
    <Screen>
      <ScreenHeader eyebrow={capital(longDate(today))} title="KPIs" />
      <OfflineNotice />

      {!goals && found.error ? (
        <ErrorState title="KPIs no contesta" detail={found.error.message} onRetry={found.refresh} />
      ) : !goals ? (
        <Skeleton rows={4} />
      ) : goals.length === 0 ? (
        <EmptyState
          icon="target"
          hue={2}
          title="Aún no te has propuesto nada"
          action={{ label: "Ponerte una meta", icon: "plus", onClick: () => setCreating(true) }}
        >
          <p>
            Algo de cada día, como leer o andar 8.000 pasos, o algo con fecha, como llegar a un peso o
            a un ahorro. Si la cifra ya está en arga, se mueve sola.
          </p>
        </EmptyState>
      ) : (
        <>
          <Card>
            <Figures label="Cómo vas" items={goalFigures(goals)} />
          </Card>
          <SegmentedControl<GoalView>
            label="Ordenar"
            options={[
              { value: "category", label: "Por categoría" },
              { value: "date", label: "Por fecha" },
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

      <CreateButton label="Meta" onClick={() => setCreating(true)} />

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
