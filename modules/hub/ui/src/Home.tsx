import { Card, EmptyState, GroupLabel, Hint, List, ListRow, OfflineNotice, Screen } from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import { AddFor } from "./Add";
import { AppVersion } from "./AppVersion";
import { type AppSources, type Category, type Connection, type Provider, readApps, readCatalogue, readConnections } from "./api";
import type { Tab } from "./App";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { StatementUpload } from "./Statements";
import { say } from "./words";

export function whereItLives(provider: Provider, connected = false): string {
  if (provider.by_mail) return say("where.mail");
  if (provider.available && provider.created_in) return say("where.from", { app: provider.created_in });
  if (provider.available) return provider.single && connected ? say("where.connected") : say("where.add");
  if (provider.lives_in) return say("add.inlet", { app: provider.lives_in });
  return say("where.soon");
}

function pathOf(app: string): string {
  return `/${app.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()}`;
}

export function appPath(provider: Provider): string | null {
  const app = provider.lives_in ?? provider.created_in;
  return app ? pathOf(app) : null;
}


export function HomeScreen({
  tab,
  onOpen,
  onSetup,
}: {
  tab: Tab;
  onOpen: (id: string) => void;
  onSetup: () => void;
}) {
  const { data: home, found } = useLoad("home", async () => {
    const [catalogue, connections, apps] = await Promise.all([readCatalogue(), readConnections(), readApps()]);
    return { catalogue, connections, apps };
  });
  const [adding, setAdding] = useState<Provider | null>(null);

  const asked = useRef(false);
  useEffect(() => {
    if (!home || asked.current) return;
    asked.current = true;
    const wanted = new URLSearchParams(window.location.search).get("add");
    const provider = home.catalogue.flatMap((category) => category.providers).find((item) => item.id === wanted);
    if (provider?.available) setAdding(provider);
  }, [home]);

  return (
    <Screen>
      <ScreenHeader title={say(tab === "status" ? "tabs.status" : "tabs.setup")} />
      <OfflineNotice />
      <Returned />
      {!home && <Pending found={found} />}
      {home && tab === "status" && <Yours connections={home.connections} onOpen={onOpen} onSetup={onSetup} />}
      {home && tab === "setup" && <StatementUpload />}
      {home && tab === "setup" && (
        <ByApp
          apps={home.apps}
          catalogue={home.catalogue}
          connections={home.connections}
          onAdd={setAdding}
          onOpen={onOpen}
        />
      )}
      {adding && <AddFor provider={adding} onClose={() => setAdding(null)} onCreated={onOpen} />}
      <AppVersion />
    </Screen>
  );
}

export function Yours({
  connections,
  onOpen = () => undefined,
  onSetup,
}: {
  connections: Connection[];
  onOpen?: (id: string) => void;
  onSetup?: () => void;
}) {
  if (connections.length === 0) {
    return (
      <EmptyState
        icon="bolt"
        title={say("yours.empty")}
        action={onSetup ? { label: say("yours.connect"), onClick: onSetup } : undefined}
      >
        {say("yours.empty.hint")}
      </EmptyState>
    );
  }
  const attention = connections.find((connection) => connection.reason);
  return (
    <Card title={say("yours.title")}>
      <List>
        {connections.map((connection) => (
          <ConnectionRow key={connection.id} connection={connection} onOpen={onOpen} />
        ))}
      </List>
      {attention && (
        <Hint announce>
          {attention.reason}
        </Hint>
      )}
    </Card>
  );
}

function ConnectionRow({ connection, onOpen }: { connection: Connection; onOpen: (id: string) => void }) {
  return (
    <ListRow
      title={connection.label}
      detail={connection.brief}
      tone={connection.tone}
      accessory="chevron-right"
      onClick={() => onOpen(connection.id)}
    />
  );
}

export function providerAction(
  provider: Provider,
  connections: Connection[],
): { kind: "add" } | { kind: "open"; id: string } | { kind: "app"; path: string } | null {
  if (provider.available && provider.created_in) return { kind: "app", path: appPath(provider)! };
  if (provider.available) {
    const mine = connections.find((connection) => connection.provider === provider.id);
    return provider.single && mine ? { kind: "open", id: mine.id } : { kind: "add" };
  }
  const path = appPath(provider);
  return path ? { kind: "app", path } : null;
}

export function ProviderRows({
  providers,
  connections = [],
  onAdd = () => undefined,
  onOpen = () => undefined,
}: {
  providers: Provider[];
  connections?: Connection[];
  onAdd?: (provider: Provider) => void;
  onOpen?: (id: string) => void;
}) {
  return (
    <List>
      {providers.flatMap((provider) => {
        const mine = connections
          .filter((connection) => connection.provider === provider.id)
          .map((connection) => <ConnectionRow key={connection.id} connection={connection} onOpen={onOpen} />);
        const action = providerAction(provider, connections);
        if (action?.kind === "open") return mine;
        const go = () => {
          if (action?.kind === "add") onAdd(provider);
          if (action?.kind === "app") window.location.assign(action.path);
        };
        return [
          ...mine,
          <ListRow
            key={provider.id}
            title={provider.name}
            detail={whereItLives(provider)}
            accessory={action ? (action.kind === "add" ? "plus" : "chevron-right") : undefined}
            disabled={!action}
            onClick={action ? go : undefined}
          />,
        ];
      })}
    </List>
  );
}

export function ProviderSection({
  title,
  providers,
  connections = [],
  onAdd,
  onOpen,
}: {
  title: string;
  providers: Provider[];
  connections?: Connection[];
  onAdd?: (provider: Provider) => void;
  onOpen?: (id: string) => void;
}) {
  return (
    <Card title={title}>
      <ProviderRows providers={providers} connections={connections} onAdd={onAdd} onOpen={onOpen} />
    </Card>
  );
}

export function providersOf(ids: string[], catalogue: Category[]): Provider[] {
  const all = catalogue.flatMap((category) => category.providers);
  return ids.flatMap((id) => all.filter((item) => item.id === id || item.id.startsWith(`${id}.`)));
}

export function ByApp({
  apps,
  catalogue,
  connections = [],
  onAdd,
  onOpen,
}: {
  apps: AppSources;
  catalogue: Category[];
  connections?: Connection[];
  onAdd?: (provider: Provider) => void;
  onOpen?: (id: string) => void;
}) {
  const others = providersOf(apps.others, catalogue);
  return (
    <>
      {apps.apps.map((app) => (
        <Card key={app.module} title={app.name}>
          {app.inlets.map((inlet) => (
            <div key={inlet.key} className="hub-group">
              {(app.inlets.length > 1 || app.services.length > 0) && <GroupLabel>{inlet.title}</GroupLabel>}
              <ProviderRows providers={providersOf(inlet.providers, catalogue)} connections={connections} onAdd={onAdd} onOpen={onOpen} />
            </div>
          ))}
          {app.services.length > 0 && (
            <div className="hub-group">
              {app.inlets.length > 0 && <GroupLabel>{say("byapp.services")}</GroupLabel>}
              <ProviderRows
                providers={providersOf(
                  app.services.map((one) => one.provider),
                  catalogue,
                )}
                connections={connections}
                onAdd={onAdd}
                onOpen={onOpen}
              />
            </div>
          )}
        </Card>
      ))}
      {others.length > 0 && (
        <ProviderSection title={say("byapp.others")} providers={others} connections={connections} onAdd={onAdd} onOpen={onOpen} />
      )}
    </>
  );
}

const RETURNS = ["cancelled", "unknown", "failed"];

export function returned(params: URLSearchParams): string | null {
  for (const source of ["bank", "google"]) {
    const said = params.get(source) ?? "";
    if (RETURNS.includes(said)) return say(`returned.${source}.${said}`);
  }
  return null;
}

function Returned() {
  const said = returned(new URLSearchParams(window.location.search));
  return said ? (
    <Hint tone="warning">
      {said}
    </Hint>
  ) : null;
}
