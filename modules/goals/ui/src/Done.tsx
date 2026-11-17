import { useResource } from "@openarga/app";
import { EmptyState, ErrorState, GroupLabel, List, ListRow, Screen, Skeleton, type Translate, useT, useToast } from "@openarga/ui";

import { type Task, changed, readDone, undoTask } from "./api";
import { ScreenHeader } from "./Header";
import { capital, daysBetween, longDate, todayIso } from "./words";

function dayLabel(t: Translate, iso: string, today: string): string {
  const days = daysBetween(iso, today);
  if (days === 0) return t("done.today");
  if (days === 1) return t("done.yesterday");
  return capital(longDate(iso));
}

export function DoneScreen() {
  const t = useT();
  return (
    <Screen>
      <ScreenHeader title={t("done.title")} />
      <DoneTasks />
    </Screen>
  );
}

export function DoneTasks() {
  const found = useResource("tasks:done", readDone, { persist: true });
  const tasks = found.data ?? null;
  const toast = useToast();
  const t = useT();
  const today = todayIso();
  const load = changed;

  const undo = (task: Task) =>
    undoTask(task.id)
      .then(() => {
        load();
        toast({ message: t("done.pending_again", { title: task.title }) });
      })
      .catch((reason: unknown) =>
        toast({ message: reason instanceof Error ? reason.message : t("done.undo_failed"), tone: "error" }),
      );

  const days: { day: string; tasks: Task[] }[] = [];
  for (const task of tasks ?? []) {
    const day = todayIso(new Date(task.done_at!));
    const last = days[days.length - 1];
    if (last?.day === day) last.tasks.push(task);
    else days.push({ day, tasks: [task] });
  }

  return (
    <>
      {!tasks && found.error ? (
        <ErrorState title={t("app.not_answering")} detail={found.error.message} onRetry={found.refresh} />
      ) : !tasks ? (
        <Skeleton rows={4} />
      ) : tasks.length === 0 ? (
        <EmptyState icon="done" hue={2} title={t("done.empty")}>
          <p>{t("done.empty_detail")}</p>
        </EmptyState>
      ) : (
        days.map(({ day, tasks: ofDay }) => (
          <section key={day} className="goals-group" aria-label={dayLabel(t, day, today)}>
            <GroupLabel count={ofDay.length}>{dayLabel(t, day, today)}</GroupLabel>
            <List>
              {ofDay.map((task) => (
                <ListRow
                  key={task.id}
                  title={task.title}
                  subtitle={[task.category, task.done_by_me === false ? t("done.by_someone") : null]
                    .filter(Boolean)
                    .join(" · ")}
                  hue={task.hue}
                  action={{ icon: "undo", label: t("done.undo_label", { title: task.title }), onClick: () => void undo(task) }}
                />
              ))}
            </List>
          </section>
        ))
      )}
    </>
  );
}
