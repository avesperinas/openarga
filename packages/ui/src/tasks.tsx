"use client";

import * as React from "react";

import { dayLabel } from "./calendar";
import { Icon } from "./icons";
import { type Hue, useWidgetLayout, useWidgetSize } from "./Widget";
import { dates } from "./regional";

const DAY_MS = 86_400_000;

export interface TaskData {
  id: string;
  title: string;
  due?: string;
  overdue?: boolean;
  done?: boolean;
  detail?: string;
  hue?: number;
}

export interface WidgetTasksProps {
  tasks: TaskData[];
  count?: number;
  onToggle?: (id: string, done: boolean) => Promise<boolean>;
  now?: Date;
}

const midnight = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());

export function dueLabel(due: string, now: Date = new Date()): string {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(due);
  const at = dateOnly
    ? (() => {
        const [y, m, d] = due.split("-").map(Number) as [number, number, number];
        return new Date(y, m - 1, d);
      })()
    : new Date(due);
  if (Number.isNaN(at.getTime())) return "";
  const days = Math.round((midnight(at).getTime() - midnight(now).getTime()) / DAY_MS);
  if (days < -1) return `Hace ${-days} días`;
  if (days === -1) return "Ayer";
  if (days === 0) {
    return dateOnly
      ? "Hoy"
      : dates({ hour: "2-digit", minute: "2-digit" }).format(at);
  }
  return dayLabel(at, now);
}

function Check({
  task,
  done,
  onToggle,
}: {
  task: TaskData;
  done: boolean;
  onToggle?: () => void;
}) {
  const label = done ? `Desmarcar ${task.title}` : `Marcar hecha ${task.title}`;
  return onToggle ? (
    <button
      type="button"
      className="task-check"
      data-hue={task.hue as Hue | undefined}
      data-done={done || undefined}
      aria-label={label}
      aria-pressed={done}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onToggle();
      }}
    >
      {done && <Icon name="done" />}
    </button>
  ) : (
    <span className="task-check" data-hue={task.hue as Hue | undefined} aria-hidden="true" />
  );
}

function useToggles(onToggle: WidgetTasksProps["onToggle"]) {
  const [flipped, setFlipped] = React.useState<Record<string, boolean>>({});
  const toggle = React.useCallback(
    (task: TaskData) => {
      if (!onToggle) return undefined;
      return () => {
        const next = !(flipped[task.id] ?? task.done ?? false);
        setFlipped((current) => ({ ...current, [task.id]: next }));
        void onToggle(task.id, next).then((ok) => {
          if (!ok) {
            setFlipped((current) => {
              const rest = { ...current };
              delete rest[task.id];
              return rest;
            });
          }
        });
      };
    },
    [flipped, onToggle],
  );
  const isDone = (task: TaskData) => flipped[task.id] ?? task.done ?? false;
  return { toggle, isDone };
}

function Row({
  task,
  done,
  onToggle,
  now,
}: {
  task: TaskData;
  done: boolean;
  onToggle?: () => void;
  now: Date;
}) {
  const when = task.due ? dueLabel(task.due, now) : "";
  return (
    <li className="task" data-done={done || undefined} data-overdue={task.overdue || undefined}>
      <Check task={task} done={done} onToggle={onToggle} />
      <span className="task-body">
        <span className="task-title">{task.title}</span>
        {(when || task.detail) && (
          <span className="task-meta">
            {when && <span className="task-due">{when}</span>}
            {task.detail && <span className="task-detail">{task.detail}</span>}
          </span>
        )}
      </span>
    </li>
  );
}

const ROWS = { narrow: 3, square: 3, tall: 8, wide: 6, large: 14 } as const;

export function WidgetTasks({ tasks, count, onToggle, now: given }: WidgetTasksProps) {
  const layout = useWidgetLayout();
  const size = useWidgetSize();
  const now = given ?? new Date();
  const { toggle, isDone } = useToggles(onToggle);
  const total = count ?? tasks.length;
  const overdue = tasks.filter((task) => task.overdue).length;

  if (tasks.length === 0) return <p className="widget-empty">Nada pendiente</p>;

  if (layout === "tiny") {
    return (
      <div className="list-count" data-tone={overdue ? "warning" : undefined}>
        <p className="widget-value kpi-figure">{total}</p>
        <p className="list-count-first">{overdue ? `${overdue} ${overdue === 1 ? "vencida" : "vencidas"}` : "por hacer"}</p>
      </div>
    );
  }

  if (layout === "strip") {
    const first = tasks.find((task) => !isDone(task)) ?? tasks[0]!;
    const rest = total - 1;
    return (
      <div className="list-strip">
        <ul className="tasks">
          <Row task={first} done={isDone(first)} onToggle={toggle(first)} now={now} />
        </ul>
        {rest > 0 && size !== "2x1" && <span className="list-strip-more">+{rest}</span>}
      </div>
    );
  }

  const shown = tasks.slice(0, ROWS[layout]);
  const more = total - shown.length;

  if (layout === "large") {
    const groups: { label: string; items: TaskData[] }[] = [];
    const today = midnight(now).getTime();
    for (const task of shown) {
      const label = task.overdue
        ? "Vencidas"
        : !task.due
          ? "Sin fecha"
          : midnight(new Date(task.due.length === 10 ? `${task.due}T00:00` : task.due)).getTime() === today
            ? "Hoy"
            : "Más adelante";
      const last = groups[groups.length - 1];
      if (last?.label === label) last.items.push(task);
      else groups.push({ label, items: [task] });
    }
    return (
      <div className="tasks-groups">
        {groups.map((group) => (
          <section key={group.label} className="tasks-group" data-overdue={group.label === "Vencidas" || undefined}>
            <h3 className="upnext-day-label">{group.label}</h3>
            <ul className="tasks">
              {group.items.map((task) => (
                <Row key={task.id} task={task} done={isDone(task)} onToggle={toggle(task)} now={now} />
              ))}
            </ul>
          </section>
        ))}
        {more > 0 && <p className="widget-footnote">y {more} más</p>}
      </div>
    );
  }

  return (
    <>
      <ul className="tasks" data-columns={layout === "wide" || undefined}>
        {shown.map((task) => (
          <Row key={task.id} task={task} done={isDone(task)} onToggle={toggle(task)} now={now} />
        ))}
      </ul>
      {more > 0 && layout !== "square" && <p className="widget-footnote">y {more} más</p>}
    </>
  );
}
