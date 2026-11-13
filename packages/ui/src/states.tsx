import * as React from "react";

import { Button } from "./controls";
import { IconBadge } from "./icons";
import { Notice } from "./screen";
import { say } from "./words";

export function ErrorState({
  title,
  detail,
  onRetry,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void | Promise<unknown>;
}) {
  const [busy, setBusy] = React.useState(false);
  return (
    <div className="surface empty-state" role="alert">
      <IconBadge name="alert" hue={2} />
      <p className="empty-state-title">{title ?? say("error_state.title")}</p>
      {detail && <div className="empty-state-body">{detail}</div>}
      {onRetry && (
        <Button
          variant="tinted"
          icon="repeat"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            void Promise.resolve()
              .then(onRetry)
              .catch(() => undefined)
              .finally(() => setBusy(false));
          }}
        >
          {busy ? say("error_state.retrying") : say("error_state.retry")}
        </Button>
      )}
    </div>
  );
}

function subscribe(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

export function useOnline(): boolean {
  return React.useSyncExternalStore(subscribe, () => navigator.onLine, () => true);
}

export function OfflineNotice({ pending = 0, offline }: { pending?: number; offline?: boolean }) {
  const online = useOnline();
  if (offline === undefined ? online : !offline) return null;
  return (
    <Notice tone="warning" title={say("offline.title")}>
      {pending > 0
        ? say(pending === 1 ? "offline.pending.one" : "offline.pending.other", { count: pending })
        : say("offline.saved")}
    </Notice>
  );
}
