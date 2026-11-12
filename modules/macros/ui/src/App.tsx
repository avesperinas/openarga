import { withTransition } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB, ToastHost } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { GoalsScreen } from "./Goals";
import { APP } from "./Header";
import { NoticeSettings } from "./NoticeSettings";
import { MenuSettings } from "./Planning";
import { TodayScreen } from "./Today";
import { WeekScreen } from "./Week";

const ROOT = "/macros";

export type Route =
  | { tab: "today"; day?: string; add?: boolean }
  | { tab: "week" }
  | { tab: "goals" }
  | { tab: "settings" };

export function route(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "");
  const day = new RegExp(`^${ROOT}/dia/(\\d{4}-\\d{2}-\\d{2})$`).exec(path);
  if (day) return { tab: "today", day: day[1]! };
  if (path === `${ROOT}/apuntar`) return { tab: "today", add: true };
  if (path === `${ROOT}/semana`) return { tab: "week" };
  if (path === `${ROOT}/objetivo`) return { tab: "goals" };
  if (path === `${ROOT}/ajustes`) return { tab: "settings" };
  return { tab: "today" };
}

export function pathOf(to: Route): string {
  if (to.tab === "today" && to.day) return `${ROOT}/dia/${to.day}`;
  if (to.tab === "today" && to.add) return `${ROOT}/apuntar`;
  if (to.tab === "week") return `${ROOT}/semana`;
  if (to.tab === "goals") return `${ROOT}/objetivo`;
  if (to.tab === "settings") return `${ROOT}/ajustes`;
  return `${ROOT}/`;
}

type Tab = Route["tab"];

export function App() {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const back = () => withTransition(() => setPath(window.location.pathname));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const go = useCallback((to: Route, replace = false) => {
    const target = pathOf(to);
    if (target === window.location.pathname) return;
    withTransition(() => {
      if (replace) window.history.replaceState(null, "", target);
      else window.history.pushState(null, "", target);
      setPath(target);
      window.scrollTo(0, 0);
    });
  }, []);

  const current = route(path);

  return (
    <ToastHost>
      <AppShell<Tab>
        label="Secciones"
        active={current.tab}
        onSelect={(id) => go({ tab: id } as Route)}
        tabs={[
          { id: "today", label: "Hoy", icon: "today" },
          { id: "week", label: "Semana", icon: "chart" },
          { id: "goals", label: "Objetivo", icon: "target" },
          SETTINGS_TAB,
        ]}
      >
        {current.tab === "today" && (
          <TodayScreen
            day={current.day}
            add={current.add}
            onDay={(day) => go({ tab: "today", day }, true)}
            onAddDone={() => go({ tab: "today" }, true)}
            onWeek={() => go({ tab: "week" })}
          />
        )}
        {current.tab === "week" && <WeekScreen onAdd={() => go({ tab: "today", add: true })} />}
        {current.tab === "goals" && <GoalsScreen />}
        {current.tab === "settings" && (
          <AppSettings app={APP}>
            <MenuSettings />
            <NoticeSettings />
          </AppSettings>
        )}
        {current.tab === "today" && (
          <footer className="macros-version">
            <AppVersion />
          </footer>
        )}
      </AppShell>
    </ToastHost>
  );
}
