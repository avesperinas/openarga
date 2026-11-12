import { Card, EmptyState, GroupLabel, Hint, List, ListRow, OfflineNotice, Screen } from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import { AddFor } from "./Add";
import { AppVersion } from "./AppVersion";
import { type AppSources, type Category, type Connection, type Provider, readApps, readCatalogue, readConnections } from "./api";
import type { Tab } from "./App";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { StatementUpload } from "./Statements";

export function whereItLives(provider: Provider, connected = false): string {
  if (provider.by_mail) return "Por correo";
  if (provider.available && provider.created_in) return `Desde ${provider.created_in}`;
  if (provider.available) return provider.single && connected ? "Conectado" : "Añadir";
  if (provider.lives_in) return `En ${provider.lives_in}`;
  return "Próximamente";
}

function pathOf(app: string): string {
  return `/${app.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()}`;
}

export function appPath(provider: Provider): string | null {
  const app = provider.lives_in ?? provider.created_in;
  return app ? pathOf(app) : null;
}

const TITLES: Record<Tab, string> = { status: "Estado", setup: "Configurar" };

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
    const wanted = new URLSearchParams(window.location.search).get("anadir");
    const provider = home.catalogue.flatMap((category) => category.providers).find((item) => item.id === wanted);
    if (provider?.available) setAdding(provider);
  }, [home]);

  return (
    <Screen>
      <ScreenHeader title={TITLES[tab]} />
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
        title="Nada conectado aquí todavía"
        action={onSetup ? { label: "Conectar una fuente", onClick: onSetup } : undefined}
      >Este es el sitio de todo lo que entra de fuera: tus bancos, tus exchanges, tu correo y tu
          cuenta de Claude. Irán llegando una a una desde la app que las usa hoy, sin que tengas que
          volver a conectar nada.</EmptyState>
    );
  }
  const attention = connections.find((connection) => connection.reason);
  return (
    <Card title="Tus conexiones">
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
              {app.inlets.length > 0 && <GroupLabel>Consultas</GroupLabel>}
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
        <ProviderSection title="Otras fuentes" providers={others} connections={connections} onAdd={onAdd} onOpen={onOpen} />
      )}
    </>
  );
}

export const RETURNS: Record<string, string> = {
  cancelado: "No se ha conectado: la autorización se canceló en el banco.",
  desconocido: "No se ha conectado: la vuelta del banco no casa con ninguna petición tuya.",
  fallo: "No se ha conectado: el banco no abrió la sesión. Vuelve a intentarlo.",
};

export const GOOGLE_RETURNS: Record<string, string> = {
  cancelado: "No se ha conectado: la autorización se canceló en Google.",
  desconocido: "No se ha conectado: la vuelta de Google no casa con ninguna petición tuya.",
  fallo: "No se ha conectado: Google no dio el permiso. Comprueba el Client ID, el secret y que la dirección de vuelta está dada de alta, y vuelve a intentarlo.",
};

export const CLAUDE_RETURNS: Record<string, string> = {
  cancelado: "No se ha dado el permiso: se canceló al entrar.",
  fallo: "No se ha dado el permiso: la vuelta no casa con ninguna petición tuya o ha caducado.",
};

function Returned() {
  const params = new URLSearchParams(window.location.search);
  const said =
    RETURNS[params.get("banco") ?? ""] ?? GOOGLE_RETURNS[params.get("google") ?? ""] ?? CLAUDE_RETURNS[params.get("claude") ?? ""];
  return said ? (
    <Hint tone="warning">
      {said}
    </Hint>
  ) : null;
}
