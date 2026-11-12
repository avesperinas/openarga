import { SETTINGS_TAB, TabBar } from "@openarga/ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import { signIn } from "./api";
import { HistoryScreen } from "./History";
import { NextRedirect } from "./Next";
import { PlanScreen } from "./Plan";
import { sharedQueue } from "./offline";
import type { SyncQueue } from "./queue";
import { SessionScreen } from "./Session";
import { SettingsScreen } from "./Settings";
import { StatsScreen } from "./Stats";
import { TodayScreen } from "./Today";

const ROOT = "/training";
const SESSION = new RegExp(`^${ROOT}/sesion/([0-9a-f-]{36})/?$`);

type Tab = "today" | "history" | "stats" | "plan" | "settings";

export type Route = { screen: Tab } | { screen: "session"; id: string } | { screen: "next" };

const PATHS: Record<Tab, string> = {
  today: `${ROOT}/`,
  history: `${ROOT}/calendario`,
  stats: `${ROOT}/stats`,
  plan: `${ROOT}/plan`,
  settings: `${ROOT}/ajustes`,
};

export function route(pathname: string): Route {
  const match = SESSION.exec(pathname);
  if (match?.[1]) return { screen: "session", id: match[1] };
  const path = pathname.replace(/\/+$/, "");
  if (path === PATHS.history) return { screen: "history" };
  if (path === PATHS.stats) return { screen: "stats" };
  if (path === PATHS.plan) return { screen: "plan" };
  if (path === PATHS.settings) return { screen: "settings" };
  if (path === `${ROOT}/siguiente`) return { screen: "next" };
  return { screen: "today" };
}

export function App({ queue: given }: { queue?: SyncQueue }) {
  const queue = useMemo(() => given ?? sharedQueue(), [given]);
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => queue.listen((event) => event.type === "signed-out" && signIn()), [queue]);

  useEffect(() => {
    const back = () => setPath(window.location.pathname);
    const online = () => void queue.flush();
    window.addEventListener("popstate", back);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("popstate", back);
      window.removeEventListener("online", online);
    };
  }, [queue]);

  const navigate = useCallback((to: string) => {
    if (to === window.location.pathname) return;
    window.history.pushState(null, "", to);
    setPath(to);
    window.scrollTo(0, 0);
  }, []);

  const replace = useCallback((to: string) => {
    window.history.replaceState(null, "", to);
    setPath(to);
  }, []);
  const toSession = useCallback((id: string) => replace(`${ROOT}/sesion/${id}`), [replace]);
  const toToday = useCallback(() => replace(PATHS.today), [replace]);

  const openSession = (id: string) => navigate(`${ROOT}/sesion/${id}`);
  const current = route(path);
  if (current.screen === "next") return <NextRedirect onSession={toSession} onToday={toToday} />;

  if (current.screen === "session") {
    return (
      <SessionScreen key={current.id} id={current.id} queue={queue} onExit={() => navigate(PATHS.today)} />
    );
  }

  return (
    <>
      {current.screen === "today" && (
        <TodayScreen
          onOpenSession={openSession}
          onOpenPlan={() => navigate(PATHS.plan)}
          onOpenHistory={() => navigate(PATHS.history)}
        />
      )}
      {current.screen === "history" && <HistoryScreen onOpenSession={openSession} />}
      {current.screen === "stats" && <StatsScreen onOpenSession={openSession} />}
      {current.screen === "plan" && <PlanScreen />}
      {current.screen === "settings" && <SettingsScreen />}
      <TabBar
        label="Secciones"
        active={current.screen}
        onSelect={(tab) => navigate(PATHS[tab])}
        items={[
          { id: "today", label: "Hoy", icon: "today" },
          { id: "history", label: "Calendario", icon: "calendar" },
          { id: "stats", label: "Stats", icon: "chart" },
          { id: "plan", label: "Plan", icon: "edit" },
          SETTINGS_TAB,
        ]}
      />
    </>
  );
}
