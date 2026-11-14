import { mutate, useResource, withTransition } from "@openarga/app";
import { AppSettings, AppShell, ChatFab, SETTINGS_TAB } from "@openarga/ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PROFILE, type Profile, readProfile } from "./api";
import { ChatList, ThreadScreen } from "./Chat";
import { APP, AppContext } from "./Header";
import { InboxScreen } from "./Inbox";
import { InsightScreen } from "./InsightScreen";
import { LibraryScreen } from "./Library";
import { OnboardingScreen } from "./Onboarding";
import { PillScreen } from "./Pill";
import { ProfileSettings } from "./ProfileSettings";
import { TodayScreen } from "./Today";
import { YouScreen } from "./You";

const ROOT = "/insights";

type Tab = "today" | "inbox" | "library" | "you" | "chat" | "settings";

const PATHS: Record<Tab, string> = {
  today: `${ROOT}/`,
  inbox: `${ROOT}/inbox`,
  library: `${ROOT}/library`,
  you: `${ROOT}/you`,
  chat: `${ROOT}/chat`,
  settings: `${ROOT}/settings`,
};
const START = `${ROOT}/start`;

const UUID = "([0-9a-f-]{36})";

const OLD: Record<string, string> = {
  consejos: "inbox",
  biblioteca: "library",
  tu: "you",
  hablar: "chat",
  ajustes: "settings",
  conocerte: "start",
  consejo: "insight",
  pildora: "pill",
  nueva: "new",
};

const english = (path: string) => path.replace(/[a-z]+/g, (part) => OLD[part] ?? part);

export type Route =
  | { tab: "today"; pill: string | null }
  | { tab: "inbox"; insight: string | null }
  | { tab: "library" }
  | { tab: "you"; start: boolean }
  | { tab: "chat"; thread: string | null; fresh: boolean }
  | { tab: "settings" };

export function route(pathname: string): Route {
  const path = english(pathname.replace(/\/+$/, ""));
  if (path === PATHS.settings) return { tab: "settings" };
  if (path === PATHS.chat) return { tab: "chat", thread: null, fresh: false };
  if (path === `${PATHS.chat}/new`) return { tab: "chat", thread: null, fresh: true };
  const talking = new RegExp(`^/insights/chat/${UUID}$`).exec(path);
  if (talking) return { tab: "chat", thread: talking[1] ?? null, fresh: false };
  if (path === PATHS.inbox) return { tab: "inbox", insight: null };
  const opened = new RegExp(`^/insights/insight/${UUID}$`).exec(path);
  if (opened) return { tab: "inbox", insight: opened[1] ?? null };
  if (path === PATHS.library) return { tab: "library" };
  if (path === PATHS.you) return { tab: "you", start: false };
  if (path === START) return { tab: "you", start: true };
  const pill = new RegExp(`^/insights/pill/${UUID}$`).exec(path);
  return { tab: "today", pill: pill?.[1] ?? null };
}

export function App() {
  const [path, setPath] = useState(() => window.location.pathname);
  const profile = useResource(PROFILE, readProfile, { persist: true }).data;

  useEffect(() => {
    const back = () => withTransition(() => setPath(window.location.pathname));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const navigate = useCallback((to: string) => {
    if (to === window.location.pathname + window.location.search) return;
    withTransition(() => {
      window.history.pushState(null, "", to);
      setPath(window.location.pathname);
      window.scrollTo(0, 0);
    });
  }, []);

  const app = useMemo(() => ({ ...APP, name: profile?.name ?? APP.name }), [profile]);
  const current = route(path);
  const openPill = (id: string) => navigate(`${ROOT}/pill/${id}`);
  const openInsight = (id: string) => navigate(`${ROOT}/insight/${id}`);

  return (
    <AppContext.Provider value={app}>
      <AppShell
        label="Secciones"
        active={current.tab}
        onSelect={(tab) => navigate(PATHS[tab as Tab])}
        tabs={[
          { id: "today", label: "Hoy", icon: "today" },
          { id: "inbox", label: "Consejos", icon: "paw" },
          { id: "library", label: "Biblioteca", icon: "book" },
          { id: "you", label: "Tú", icon: "spark" },
          SETTINGS_TAB,
        ]}
      >
        {current.tab === "today" && current.pill === null && (
          <TodayScreen onOpenPill={openPill} onOpenInsight={openInsight} onStart={() => navigate(START)} />
        )}
        {current.tab === "today" && current.pill !== null && (
          <PillScreen key={current.pill} id={current.pill} onBack={() => navigate(PATHS.today)} onOpen={openPill} />
        )}
        {current.tab === "inbox" && current.insight === null && (
          <InboxScreen onOpen={openInsight} onSettings={() => navigate(PATHS.you)} />
        )}
        {current.tab === "inbox" && current.insight !== null && (
          <InsightScreen
            id={current.insight}
            onBack={() => navigate(PATHS.inbox)}
            onAnswer={(id) => navigate(`${PATHS.chat}/new?insight=${id}`)}
          />
        )}
        {current.tab === "library" && <LibraryScreen onOpenPill={openPill} />}
        {current.tab === "you" && !current.start && (
          <YouScreen onStart={() => navigate(START)} onSettings={() => navigate(PATHS.settings)} />
        )}
        {current.tab === "you" && current.start && (
          <OnboardingScreen onBack={() => navigate(PATHS.today)} onDone={() => navigate(PATHS.you)} />
        )}
        {current.tab === "chat" && current.thread === null && !current.fresh && (
          <ChatList onOpen={(id) => navigate(`${PATHS.chat}/${id}`)} onNew={() => navigate(`${PATHS.chat}/new`)} />
        )}
        {current.tab === "chat" && (current.thread !== null || current.fresh) && (
          <ThreadScreen
            key={current.thread ?? "new"}
            id={current.thread}
            insightId={current.fresh ? new URLSearchParams(window.location.search).get("insight") ?? new URLSearchParams(window.location.search).get("consejo") : null}
            onBack={() => navigate(PATHS.chat)}
            onStarted={(id) => {
              window.history.replaceState(null, "", `${PATHS.chat}/${id}`);
              setPath(window.location.pathname);
            }}
          />
        )}
        {current.tab === "settings" && (
          <AppSettings app={app}>
            <ProfileSettings onSaved={(saved: Profile) => void mutate(PROFILE, saved)} />
          </AppSettings>
        )}
      </AppShell>
      {current.tab !== "chat" && current.tab !== "settings" && (
        <ChatFab label={`Hablar con ${app.name}`} onClick={() => navigate(PATHS.chat)} />
      )}
    </AppContext.Provider>
  );
}
