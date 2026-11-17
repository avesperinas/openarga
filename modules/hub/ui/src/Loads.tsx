import { Unauthorised, invalidate, mutate, signIn, useResource } from "@openarga/app";
import { EmptyState, ErrorState, Skeleton } from "@openarga/ui";
import { useCallback, useEffect } from "react";
import { say } from "./words";

export const changed = () => invalidate("");

const gone = (error: Error | null) => Boolean(error?.message.includes("does not exist"));

export function useLoad<T>(key: string | null, load: () => Promise<T>) {
  const found = useResource(key, load, { persist: true });
  useEffect(() => {
    if (found.error instanceof Unauthorised) signIn();
  }, [found.error]);
  const set = useCallback(
    (next: T) => {
      if (key !== null) void mutate<T>(key, next);
      changed();
    },
    [key],
  );
  return { data: gone(found.error) ? null : (found.data ?? null), set, found };
}

export function Pending({
  found,
  rows = 5,
}: {
  found: { error: Error | null; refresh: () => Promise<void> };
  rows?: number;
}) {
  if (!found.error || found.error instanceof Unauthorised) return <Skeleton rows={rows} />;
  if (gone(found.error)) {
    return (
      <EmptyState icon="search" title={say("gone.title")}>
        {say("gone.hint")}
      </EmptyState>
    );
  }
  return <ErrorState title={say("down")} detail={found.error.message} onRetry={() => void found.refresh()} />;
}
