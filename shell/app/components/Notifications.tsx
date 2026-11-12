"use client";

import { Button, ConfirmDelete, Hint, List, ListRow, Notice, Section, SelectField, Switch } from "@openarga/ui";
import * as React from "react";

import {
  type Device,
  type NotificationSettings,
  NotificationError,
  deviceDetail,
  enableHere,
  readNotifications,
  recentDetail,
  removeDevice,
  sendTest,
  setKind,
  setQuiet,
  support,
  testSaid,
} from "../lib/notifications";

const HOURS = Array.from({ length: 24 }, (_, hour) => {
  const value = `${String(hour).padStart(2, "0")}:00`;
  return { value, label: value };
});
const NONE = "none";

export function Notifications() {
  const [settings, setSettings] = React.useState<NotificationSettings | null>(null);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [said, setSaid] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [removing, setRemoving] = React.useState<Device | null>(null);
  const here = React.useMemo(support, []);

  const reload = React.useCallback(
    () => readNotifications().then(setSettings, (error: Error) => setProblem(error.message)),
    [],
  );
  React.useEffect(() => {
    void reload();
  }, [reload]);

  const run = async <T,>(action: () => Promise<T>, done?: string | ((result: T) => string)) => {
    setBusy(true);
    setProblem(null);
    setSaid(null);
    try {
      const result = await action();
      if (done) setSaid(typeof done === "string" ? done : done(result));
      await reload();
    } catch (error) {
      setProblem(error instanceof NotificationError ? error.message : "No se ha podido hacer.");
    } finally {
      setBusy(false);
    }
  };

  if (!settings) {
    return (
      <Section title="Avisos">
        <Hint>{problem ?? "Cargando…"}</Hint>
      </Section>
    );
  }

  const apps = groupByApp(settings);
  const quietFrom = settings.quiet_from?.slice(0, 5) ?? NONE;
  const quietTo = settings.quiet_to?.slice(0, 5) ?? "08:00";

  return (
    <Section title="Avisos">
      {!settings.configured && <Hint tone="warning">Los avisos aún no están configurados en el servidor.</Hint>}
      {problem && <Notice tone="warning">{problem}</Notice>}
      {!!settings.late && (
        <Notice tone="warning">
          {settings.late === 1 ? "Hay un aviso" : `Hay ${settings.late} avisos`} sin salir desde hace más de una hora.
        </Notice>
      )}
      {said && <Hint>{said}</Hint>}

      {here === "install" && (
        <Hint>
          En el iPhone los avisos solo llegan con arga instalada: en Safari, Compartir → Añadir a pantalla de inicio,
          y vuelve aquí desde el icono.
        </Hint>
      )}
      {here === "none" && <Hint>Este navegador no recibe avisos.</Hint>}
      {settings.configured && settings.public_key && here === "ready" && (
        <div className="settings-fields">
          <Button
            variant="tinted"
            disabled={busy}
            onClick={() => run(() => enableHere(settings.public_key as string), "Activados en este dispositivo.")}
          >
            Activar en este dispositivo
          </Button>
        </div>
      )}

      {settings.devices.length > 0 && (
        <>
          <List>
            {settings.devices.map((device) => (
              <ListRow
                key={device.id}
                title={device.name}
                detail={deviceDetail(device)}
                accessory="trash"
                onClick={() => setRemoving(device)}
              />
            ))}
          </List>
          <div className="settings-fields">
            <Button disabled={busy || !settings.configured} onClick={() => run(sendTest, testSaid)}>
              Probar
            </Button>
          </div>
        </>
      )}

      {apps.map(([app, name, kinds]) => (
        <div key={app} className="settings-fields">
          <Hint>{name}</Hint>
          {kinds.map((kind) => (
            <div key={kind.kind} className="settings-row">
              <span>{kind.label}</span>
              <Switch
                label={`${name}: ${kind.label}`}
                checked={kind.enabled}
                disabled={busy}
                onChange={(enabled) => run(() => setKind(app, kind.kind, enabled))}
              />
            </div>
          ))}
        </div>
      ))}

      <div className="settings-fields">
        <SelectField
          label="Silencio desde"
          options={[{ value: NONE, label: "Sin silencio" }, ...HOURS]}
          value={quietFrom}
          onChange={(from) => run(() => (from === NONE ? setQuiet(null, null) : setQuiet(from, quietTo)))}
        />
        {quietFrom !== NONE && (
          <SelectField label="Hasta" options={HOURS} value={quietTo} onChange={(to) => run(() => setQuiet(quietFrom, to))} />
        )}
      </div>
      <Hint>Lo que caiga en el silencio llega al acabar, no se pierde.</Hint>

      {!!settings.recent?.length && (
        <div className="settings-fields">
          <Hint>Lo último</Hint>
          <List>
            {settings.recent.map((one, index) => (
              <ListRow key={`${one.app}-${one.due_at}-${index}`} title={one.title} detail={recentDetail(one)} />
            ))}
          </List>
        </div>
      )}

      {removing && (
        <ConfirmDelete
          title="¿Dejar de avisar en este dispositivo?"
          subject={removing.name}
          consequence="Se puede volver a activar desde él cuando quieras."
          action="Dejar de avisar"
          onConfirm={() => run(() => removeDevice(removing.id)).then(() => setRemoving(null))}
          onCancel={() => setRemoving(null)}
        />
      )}
    </Section>
  );
}

export function groupByApp(settings: NotificationSettings): [string, string, NotificationSettings["kinds"]][] {
  const out = new Map<string, [string, string, NotificationSettings["kinds"]]>();
  for (const kind of settings.kinds) {
    const entry = out.get(kind.app) ?? [kind.app, kind.app_name, []];
    entry[2].push(kind);
    out.set(kind.app, entry);
  }
  return [...out.values()];
}
