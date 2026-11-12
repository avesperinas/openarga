import { useResource } from "@openarga/app";
import { EmptyState, ErrorState, GroupLabel, List, ListRow, Screen, Skeleton, useToast } from "@openarga/ui";

import { type Task, changed, readDone, undoTask } from "./api";
import { ScreenHeader } from "./Header";
import { capital, daysBetween, longDate, todayIso } from "./words";

function dayLabel(iso: string, today: string): string {
  const days = daysBetween(iso, today);
  if (days === 0) return "Hoy";
  if (days === 1) return "Ayer";
  return capital(longDate(iso));
}

export function DoneScreen() {
  return (
    <Screen>
      <ScreenHeader title="Hechas" />
      <DoneTasks />
    </Screen>
  );
}

export function DoneTasks() {
  const found = useResource("tasks:done", readDone, { persist: true });
  const tasks = found.data ?? null;
  const toast = useToast();
  const today = todayIso();
  const load = changed;

  const undo = (task: Task) =>
    undoTask(task.id)
      .then(() => {
        load();
        toast({ message: `Pendiente otra vez · ${task.title}` });
      })
      .catch((reason: unknown) =>
        toast({ message: reason instanceof Error ? reason.message : "No se ha podido deshacer", tone: "error" }),
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
        <ErrorState title="KPIs no contesta" detail={found.error.message} onRetry={found.refresh} />
      ) : !tasks ? (
        <Skeleton rows={4} />
      ) : tasks.length === 0 ? (
        <EmptyState icon="done" hue={2} title="Aún no has tachado nada">
          <p>Lo que taches sale aquí, por el día en que lo hiciste.</p>
        </EmptyState>
      ) : (
        days.map(({ day, tasks: ofDay }) => (
          <section key={day} className="goals-group" aria-label={dayLabel(day, today)}>
            <GroupLabel count={ofDay.length}>{dayLabel(day, today)}</GroupLabel>
            <List>
              {ofDay.map((task) => (
                <ListRow
                  key={task.id}
                  title={task.title}
                  subtitle={[task.category, task.done_by_me === false ? "la tachó otra persona" : null]
                    .filter(Boolean)
                    .join(" · ")}
                  hue={task.hue}
                  action={{ icon: "undo", label: `Devolver a pendiente: ${task.title}`, onClick: () => void undo(task) }}
                />
              ))}
            </List>
          </section>
        ))
      )}
    </>
  );
}
