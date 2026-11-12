"use client";

import { EmptyState, ErrorState, IconButton, OfflineNotice, Sheet, Skeleton, useOnline } from "@openarga/ui";
import * as React from "react";

import { type Notice, byDay, markRead, readInbox, timeOf } from "../lib/inbox";
import { appNameOf } from "../lib/preferences";
import { useDesktop } from "./Desktop";

type Loaded = { state: "loading" } | { state: "error" } | { state: "ready"; notices: Notice[] };

export function InboxBody({
  loaded,
  online,
  name,
  onRetry,
  onOpen,
  onSettings,
}: {
  loaded: Loaded;
  online: boolean;
  name: (notice: Notice) => string;
  onRetry: () => void;
  onOpen: (notice: Notice) => void;
  onSettings: () => void;
}) {
  if (loaded.state === "loading") return <Skeleton rows={4} label="Cargando los avisos" />;
  if (loaded.state === "error") {
    return online ? (
      <ErrorState title="No se han podido traer los avisos" onRetry={onRetry} />
    ) : (
      <>
        <OfflineNotice offline />
        <ErrorState title="Sin conexión no se ven los avisos" onRetry={onRetry} />
      </>
    );
  }
  if (loaded.notices.length === 0) {
    return (
      <EmptyState
        icon="bell"
        title="Ningún aviso en 30 días"
        action={{ label: "Elegir qué avisos llegan", icon: "settings", onClick: onSettings }}
      >
        Lo que te avisen las apps se queda aquí un mes, aunque no llegue al teléfono.
      </EmptyState>
    );
  }
  return (
    <div className="inbox">
      {byDay(loaded.notices).map((day) => (
        <section key={day.key} className="inbox-day" aria-label={day.label}>
          <h3 className="inbox-day-title">{day.label}</h3>
          <ul className="surface inbox-list">
            {day.notices.map((notice) => (
              <li key={notice.id}>
                <a
                  className="inbox-item"
                  href={notice.href}
                  data-unread={notice.read ? undefined : ""}
                  onClick={() => onOpen(notice)}
                >
                  <span className="inbox-item-head">
                    <span className="inbox-item-app">{name(notice)}</span>
                    <time className="inbox-item-time" dateTime={notice.sent_at}>
                      {timeOf(notice.sent_at)}
                    </time>
                  </span>
                  <span className="inbox-item-title">
                    {notice.title}
                    {!notice.read && <span className="visually-hidden"> (sin abrir)</span>}
                  </span>
                  {notice.body && <span className="inbox-item-body">{notice.body}</span>}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function Inbox() {
  const [open, setOpen] = React.useState(false);
  const [loaded, setLoaded] = React.useState<Loaded>({ state: "loading" });
  const desktop = useDesktop();
  const online = useOnline();

  const load = React.useCallback(async () => {
    setLoaded({ state: "loading" });
    try {
      setLoaded({ state: "ready", notices: await readInbox() });
    } catch {
      setLoaded({ state: "error" });
    }
  }, []);

  React.useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const opened = (notice: Notice) => {
    markRead(notice.id);
    setLoaded((now) =>
      now.state === "ready"
        ? { ...now, notices: now.notices.map((one) => (one.id === notice.id ? { ...one, read: true } : one)) }
        : now,
    );
  };

  return (
    <>
      <IconButton icon="bell" label="Avisos" variant="plain" onClick={() => setOpen(true)} />
      {open && (
        <Sheet title="Avisos" onClose={() => setOpen(false)}>
          <InboxBody
            loaded={loaded}
            online={online}
            name={(notice) => appNameOf(notice.app, notice.app_name, desktop?.preferences)}
            onRetry={() => void load()}
            onOpen={opened}
            onSettings={() => {
              setOpen(false);
              window.location.hash = "ajustes";
            }}
          />
        </Sheet>
      )}
    </>
  );
}
