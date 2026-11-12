import { Hint, ListRow } from "@openarga/ui";
import { createContext, useCallback, useContext, useState } from "react";

import type { Category, Task } from "./api";
import { clock, whenLabel } from "./words";

export const CategoriesContext = createContext<{ list: Category[]; reload: () => void }>({
  list: [],
  reload: () => undefined,
});
export const useCategories = () => useContext(CategoriesContext);

export function TaskRow({
  task,
  today,
  onOpen,
  onDone,
  showCategory = true,
  showDay = true,
}: {
  task: Task;
  today: string;
  onOpen: () => void;
  onDone: () => void;
  showCategory?: boolean;
  showDay?: boolean;
}) {
  const subtitle = [
    showCategory ? task.category : null,
    showDay ? whenLabel(task, today) : task.due_time ? clock(task.due_time) : null,
    task.repeats,
    task.space_id ? "compartida" : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <ListRow
      title={task.title}
      subtitle={subtitle || undefined}
      hue={task.hue}
      tone={task.status === "overdue" ? "warning" : undefined}
      onClick={onOpen}
      action={{ icon: "done", label: `Hecha: ${task.title}`, kind: "check", onClick: onDone }}
    />
  );
}

export function useBusy() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (action: () => Promise<void>, fallback: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : fallback);
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, run };
}

export function Problem({ error }: { error: string | null }) {
  return error ? <Hint tone="warning">{error}</Hint> : null;
}
