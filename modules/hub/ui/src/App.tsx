import { withTransition } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { ConnectionScreen } from "./Connection";
import { APP } from "./Header";
import { HomeScreen } from "./Home";

const ROOT = "/hub";
const CONNECTION = new RegExp(`^${ROOT}/([0-9a-f-]{36})/?$`);

export type Tab = "status" | "setup";

export type Route = { screen: Tab } | { screen: "settings" } | { screen: "connection"; id: string };

const PATHS: Record<Tab, string> = {
  status: `${ROOT}/`,
  setup: `${ROOT}/configurar`,
};

const SETTINGS = `${ROOT}/ajustes`;

export function route(pathname: string): Route {
  const match = CONNECTION.exec(pathname);
  if (match?.[1]) return { screen: "connection", id: match[1] };
  const path = pathname.replace(/\/+$/, "");
  if (path === PATHS.setup) return { screen: "setup" };
  if (path === SETTINGS) return { screen: "settings" };
  return { screen: "status" };
}

export const connectionPath = (id: string) => `${ROOT}/${id}`;

export function App() {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const back = () => withTransition(() => setPath(window.location.pathname));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const navigate = useCallback((to: string) => {
    if (to === window.location.pathname) return;
    withTransition(() => {
      window.history.pushState(null, "", to);
      setPath(to);
      window.scrollTo(0, 0);
    });
  }, []);

  const current = route(path);
  return (
    <AppShell
      label="Secciones"
      active={current.screen === "connection" ? "status" : current.screen}
      onSelect={(tab) => navigate(tab === "settings" ? SETTINGS : PATHS[tab])}
      tabs={[
        { id: "status", label: "Estado", icon: "bolt" },
        { id: "setup", label: "Configurar", icon: "plus" },
        SETTINGS_TAB,
      ]}
    >
      {current.screen === "connection" && (
        <ConnectionScreen key={current.id} id={current.id} onBack={() => navigate(PATHS.status)} />
      )}
      {current.screen === "settings" && <AppSettings app={APP} />}
      {(current.screen === "status" || current.screen === "setup") && (
        <HomeScreen
          tab={current.screen}
          onOpen={(id) => navigate(connectionPath(id))}
          onSetup={() => navigate(PATHS.setup)}
        />
      )}
    </AppShell>
  );
}
