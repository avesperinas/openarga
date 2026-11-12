import { useResource } from "@openarga/app";
import { EmptyState, ErrorState, GroupLabel, OfflineNotice, Screen, SegmentedControl, Skeleton } from "@openarga/ui";
import { useState } from "react";

import { type Goal, readClosedGoals } from "./api";
import { DoneTasks } from "./Done";
import { GoalItem } from "./Goals";
import { ScreenHeader } from "./Header";
import { todayIso } from "./words";

type Part = "goals" | "tasks";
const PART_KEY = "goals.history.part";

function rememberedPart(): Part {
  try {
    return window.localStorage.getItem(PART_KEY) === "tasks" ? "tasks" : "goals";
  } catch {
    return "goals";
  }
}

function ClosedGoals({ onOpen }: { onOpen: (id: string) => void }) {
  const found = useResource("goals:closed", readClosedGoals, { persist: true });
  const goals = found.data ?? null;
  const today = todayIso();

  if (!goals && found.error) {
    return <ErrorState title="KPIs no contesta" detail={found.error.message} onRetry={found.refresh} />;
  }
  if (!goals) return <Skeleton rows={3} />;
  if (goals.length === 0) {
    return (
      <EmptyState icon="target" hue={2} title="Aún no has cerrado ninguna meta">
        <p>Las que cumplas, las que se pasen de fecha y las que abandones salen aquí, por año.</p>
      </EmptyState>
    );
  }
  const years: { year: string; goals: Goal[] }[] = [];
  for (const goal of goals) {
    const year = (goal.closed_on ?? goal.start_on).slice(0, 4);
    const last = years[years.length - 1];
    if (last?.year === year) last.goals.push(goal);
    else years.push({ year, goals: [goal] });
  }
  return (
    <>
      {years.map(({ year, goals: ofYear }) => {
        const achieved = ofYear.filter((goal) => goal.status === "achieved").length;
        return (
          <section key={year} className="goals-group" aria-label={year}>
            <GroupLabel count={ofYear.length}>{`${year} · ${achieved} cumplidas`}</GroupLabel>
            <div className="goals-goals">
              {ofYear.map((goal) => (
                <GoalItem key={goal.id} goal={goal} today={today} withCategory onOpen={() => onOpen(goal.id)} />
              ))}
            </div>
          </section>
        );
      })}
    </>
  );
}

export function HistoryScreen({ onOpenGoal }: { onOpenGoal: (id: string) => void }) {
  const [part, setPart] = useState<Part>(rememberedPart);
  const change = (next: Part) => {
    setPart(next);
    try {
      window.localStorage.setItem(PART_KEY, next);
    } catch {
    }
  };
  return (
    <Screen>
      <ScreenHeader title="Histórico" />
      <OfflineNotice />
      <SegmentedControl<Part>
        label="Qué"
        options={[
          { value: "goals", label: "KPIs cerrados" },
          { value: "tasks", label: "Tareas hechas" },
        ]}
        value={part}
        onChange={change}
      />
      {part === "goals" ? <ClosedGoals onOpen={onOpenGoal} /> : <DoneTasks />}
    </Screen>
  );
}
