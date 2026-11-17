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
import { say } from "../words";

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
      setProblem(error instanceof NotificationError ? error.message : say("spaces.error"));
    } finally {
      setBusy(false);
    }
  };

  if (!settings) {
    return (
      <Section title={say("notifications.title")}>
        <Hint>{problem ?? say("notifications.loading")}</Hint>
      </Section>
    );
  }

  const apps = groupByApp(settings);
  const quietFrom = settings.quiet_from?.slice(0, 5) ?? NONE;
  const quietTo = settings.quiet_to?.slice(0, 5) ?? "08:00";

  return (
    <Section title={say("notifications.title")}>
      {!settings.configured && <Hint tone="warning">{say("notifications.unconfigured")}</Hint>}
      {problem && <Notice tone="warning">{problem}</Notice>}
      {!!settings.late && (
        <Notice tone="warning">
          {settings.late === 1 ? say("notifications.late.one") : say("notifications.late", { n: settings.late })}
        </Notice>
      )}
      {said && <Hint>{said}</Hint>}

      {here === "install" && (
        <Hint>{say("notifications.install")}</Hint>
      )}
      {here === "none" && <Hint>{say("notifications.unsupported")}</Hint>}
      {settings.configured && settings.public_key && here === "ready" && (
        <div className="settings-fields">
          <Button
            variant="tinted"
            disabled={busy}
            onClick={() => run(() => enableHere(settings.public_key as string), say("notifications.enabled"))}
          >
            {say("notifications.enable")}
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
              {say("notifications.test")}
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
          label={say("notifications.quiet.from")}
          options={[{ value: NONE, label: say("notifications.quiet.none") }, ...HOURS]}
          value={quietFrom}
          onChange={(from) => run(() => (from === NONE ? setQuiet(null, null) : setQuiet(from, quietTo)))}
        />
        {quietFrom !== NONE && (
          <SelectField label={say("notifications.quiet.to")} options={HOURS} value={quietTo} onChange={(to) => run(() => setQuiet(quietFrom, to))} />
        )}
      </div>
      <Hint>{say("notifications.quiet.hint")}</Hint>

      {!!settings.recent?.length && (
        <div className="settings-fields">
          <Hint>{say("notifications.recent")}</Hint>
          <List>
            {settings.recent.map((one, index) => (
              <ListRow key={`${one.app}-${one.due_at}-${index}`} title={one.title} detail={recentDetail(one)} />
            ))}
          </List>
        </div>
      )}

      {removing && (
        <ConfirmDelete
          title={say("notifications.remove.title")}
          subject={removing.name}
          consequence={say("notifications.remove.consequence")}
          action={say("notifications.remove.action")}
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
