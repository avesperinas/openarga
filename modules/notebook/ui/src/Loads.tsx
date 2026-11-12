import { invalidate, type ResourceOptions, useResource } from "@openarga/app";
import { EmptyState, ErrorState, Skeleton } from "@openarga/ui";

import { gone } from "./api";

export const changed = () => invalidate("");

export function useLoad<T>(key: string | null, load: () => Promise<T>, options: ResourceOptions<T> = {}) {
  const found = useResource(key, load, options);
  return { data: gone(found.error) ? null : (found.data ?? null), found };
}

export function Pending({
  found,
  rows = 6,
  missing = "Ya no está",
}: {
  found: { error: Error | null; refresh: () => Promise<void> };
  rows?: number;
  missing?: string;
}) {
  if (!found.error) return <Skeleton rows={rows} />;
  if (gone(found.error)) {
    return (
      <EmptyState icon="note" title={missing}>
        Puede que esté en la papelera, o que se haya movido.
      </EmptyState>
    );
  }
  return <ErrorState title="Notebook no contesta" detail={found.error.message} onRetry={() => void found.refresh()} />;
}
