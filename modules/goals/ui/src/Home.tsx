import { mutate, useResource } from "@openarga/app";
import {
  Card,
  ChoiceChips,
  CreateButton,
  EmptyState,
  ErrorState,
  GroupLabel,
  List,
  OfflineNotice,
  RingFigure,
  Screen,
  Section,
  SegmentedControl,
  Skeleton,
  useToast,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Task, changed, completeTask, readDone, readPending, readTask, undoTask } from "./api";
import { ScreenHeader } from "./Header";
import { TaskRow, useCategories } from "./Parts";
import { TaskSheet } from "./TaskSheet";
import { capital, count, grouped, longDate, todayIso, whenLabel } from "./words";

type View = "date" | "category";
const VIEW_KEY = "goals.view";
const ALL = "all";

function rememberedView(): View {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "category" ? "category" : "date";
  } catch {
    return "date";
  }
}

export const TASKS = "tasks";

export function todayRing(pending: Task[], done: Task[], today: string) {
  const doneToday = done.filter((task) => task.done_at !== null && todayIso(new Date(task.done_at)) === today).length;
  const due = pending.filter((task) => task.status === "today" || task.status === "overdue").length;
  const overdue = pending.filter((task) => task.status === "overdue").length;
  const total = doneToday + due;
  const left = [`${count(pending.length, "pendiente", "pendientes")} en total`];
  if (overdue > 0) left.unshift(count(overdue, "vencida", "vencidas"));
  return {
    share: total > 0 ? doneToday / total : null,
    value: total > 0 ? `${doneToday}/${total}` : "0",
    label: total > 0 ? "hechas hoy" : "Nada para hoy",
    detail: left.join(" · "),
    tone: overdue > 0 ? ("warning" as const) : undefined,
  };
}

export function HomeScreen({ openTask, onClosed }: { openTask?: string; onClosed: () => void }) {
  const { list: categories } = useCategories();
  const found = useResource(TASKS, readPending, { persist: true });
  const tasks = found.data ?? null;
  const finished = useResource("tasks:done", readDone, { persist: true }).data ?? [];
  const [view, setView] = useState<View>(rememberedView);
  const [filter, setFilter] = useState(ALL);
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const [newIn, setNewIn] = useState<string | undefined>(undefined);
  const toast = useToast();
  const today = todayIso();

  const load = changed;

  useEffect(() => {
    if (!openTask) return;
    readTask(openTask)
      .then(setEditing)
      .catch(() => onClosed());
  }, [openTask, onClosed]);

  const changeView = (next: View) => {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
    }
  };

  const done = (task: Task) => {
    void mutate<Task[]>(TASKS, (current) => current?.filter((one) => one.id !== task.id) ?? []);
    completeTask(task.id)
      .then(({ next }) => {
        load();
        const then = next ? `. La siguiente, ${whenLabel(next, today)}` : "";
        toast({
          message: `Hecha · ${task.title}${then}`,
          action: { label: "Deshacer", run: () => void undoTask(task.id).then(load) },
        });
      })
      .catch((reason: unknown) => {
        load();
        toast({ message: reason instanceof Error ? reason.message : "No se ha podido tachar", tone: "error" });
      });
  };

  const close = () => {
    setEditing(null);
    setNewIn(undefined);
    onClosed();
  };

  const add = (category?: string) => {
    setNewIn(category);
    setEditing("new");
  };

  const shown = tasks?.filter((task) => filter === ALL || task.category_id === filter) ?? [];
  const row = (task: Task, showCategory = true, showDay = true) => (
    <TaskRow
      key={task.id}
      task={task}
      today={today}
      showCategory={showCategory}
      showDay={showDay}
      onOpen={() => setEditing(task)}
      onDone={() => done(task)}
    />
  );

  return (
    <Screen>
      <ScreenHeader eyebrow={capital(longDate(today))} title="Tareas" />
      <OfflineNotice />

      {!tasks && found.error ? (
        <ErrorState title="KPIs no contesta" detail={found.error.message} onRetry={found.refresh} />
      ) : !tasks ? (
        <Skeleton rows={5} />
      ) : tasks.length === 0 ? (
        <EmptyState
          icon="list"
          hue={3}
          title="Nada pendiente"
          action={{ label: "Apuntar una tarea", icon: "plus", onClick: () => add() }}
        >
          <p>Lo que apuntes sale aquí por fecha, con lo vencido arriba.</p>
        </EmptyState>
      ) : (
        <>
          <Card>
            <RingFigure size="medium" {...todayRing(tasks, finished, today)} />
          </Card>
          <SegmentedControl<View>
            label="Ordenar"
            options={[
              { value: "date", label: "Por fecha" },
              { value: "category", label: "Por categoría" },
            ]}
            value={view}
            onChange={changeView}
          />

          {view === "date" ? (
            <>
              {categories.length > 1 && (
                <ChoiceChips
                  label="Categoría"
                  options={[
                    { value: ALL, label: "Todas" },
                    ...categories.map((one) => ({ value: one.id, label: one.name })),
                  ]}
                  value={filter}
                  onChange={setFilter}
                />
              )}
              {shown.length === 0 ? (
                <EmptyState icon="done" hue={2} title="Nada pendiente aquí" />
              ) : (
                grouped(shown, today).map((group) => (
                  <section key={group.id} className="goals-group" aria-label={group.label}>
                    <GroupLabel count={group.tasks.length} tone={group.id === "overdue" ? "warning" : undefined}>
                      {group.label}
                    </GroupLabel>
                    <List>
                      {group.tasks.map((task) =>
                        row(task, filter === ALL, group.id !== "today" && group.id !== "tomorrow"),
                      )}
                    </List>
                  </section>
                ))
              )}
            </>
          ) : (
            categories
              .filter((category) => tasks.some((task) => task.category_id === category.id))
              .map((category) => (
                <Section
                  key={category.id}
                  title={category.name}
                  count={tasks.filter((task) => task.category_id === category.id).length}
                  action={{ label: "Añadir", icon: "plus", onClick: () => add(category.id) }}
                >
                  <List>{tasks.filter((task) => task.category_id === category.id).map((task) => row(task, false))}</List>
                </Section>
              ))
          )}
        </>
      )}

      <CreateButton label="Tarea" onClick={() => add(view === "date" && filter !== ALL ? filter : undefined)} />

      {editing && (
        <TaskSheet
          key={editing === "new" ? "new" : editing.id}
          task={editing === "new" ? undefined : editing}
          category={newIn}
          today={today}
          onClose={close}
          onSaved={() => {
            close();
            load();
          }}
        />
      )}
    </Screen>
  );
}
