import { invalidate, mutate, useResource } from "@openarga/app";
import { EmptyState, ErrorState, Skeleton } from "@openarga/ui";
import { useCallback } from "react";

export const changed = () => invalidate("");

const gone = (error: Error | null) => Boolean(error?.message.startsWith("no existe"));

export function useLoad<T>(key: string | null, load: () => Promise<T>) {
  const found = useResource(key, load, { persist: true });
  const set = useCallback(
    (next: T) => {
      if (key !== null) void mutate<T>(key, next);
      changed();
    },
    [key],
  );
  return { data: gone(found.error) ? null : (found.data ?? null), set, reload: changed, found };
}

export function Pending({
  found,
  rows = 6,
  label,
}: {
  found: { error: Error | null; refresh: () => Promise<void> };
  rows?: number;
  label?: string;
}) {
  if (!found.error) return <Skeleton rows={rows} label={label} />;
  if (gone(found.error)) {
    return (
      <EmptyState icon="search" title="Ya no está">
        Se borró o ya no lo compartes.
      </EmptyState>
    );
  }
  return <ErrorState title="Travel no contesta" detail={found.error.message} onRetry={() => void found.refresh()} />;
}
