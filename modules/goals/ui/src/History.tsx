import { useResource } from "@openarga/app";
import { EmptyState, ErrorState, GroupLabel, OfflineNotice, Screen, SegmentedControl, Skeleton, useT } from "@openarga/ui";
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
  const t = useT();
  const today = todayIso();

  if (!goals && found.error) {
    return <ErrorState title={t("app.not_answering")} detail={found.error.message} onRetry={found.refresh} />;
  }
  if (!goals) return <Skeleton rows={3} />;
  if (goals.length === 0) {
    return (
      <EmptyState icon="target" hue={2} title={t("history.empty")}>
        <p>{t("history.empty_detail")}</p>
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
            <GroupLabel count={ofYear.length}>{t("history.year", { year, count: achieved })}</GroupLabel>
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
  const t = useT();
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
      <ScreenHeader title={t("history.title")} />
      <OfflineNotice />
      <SegmentedControl<Part>
        label={t("history.what")}
        options={[
          { value: "goals", label: t("history.closed_goals") },
          { value: "tasks", label: t("history.done_tasks") },
        ]}
        value={part}
        onChange={change}
      />
      {part === "goals" ? <ClosedGoals onOpen={onOpenGoal} /> : <DoneTasks />}
    </Screen>
  );
}
