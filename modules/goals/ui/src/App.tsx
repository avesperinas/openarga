import { useResource, withTransition } from "@openarga/app";
import { AppSettings, AppShell, List, ListRow, SETTINGS_TAB, Section, ToastHost, useT } from "@openarga/ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import { changed, readCategories } from "./api";
import { AppVersion } from "./AppVersion";
import { CategoriesScreen } from "./Categories";
import { GoalScreen } from "./GoalScreen";
import { GoalsScreen } from "./Goals";
import { APP } from "./Header";
import { HistoryScreen } from "./History";
import { HomeScreen } from "./Home";
import { CategoriesContext } from "./Parts";

const ROOT = "/goals";

export type Route =
  | { tab: "goals"; goal?: string }
  | { tab: "home"; task?: string }
  | { tab: "done" }
  | { tab: "categories" }
  | { tab: "settings" };

const UUID = "[0-9a-f-]{36}";

export function route(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "");
  const task = new RegExp(`^${ROOT}/task/(${UUID})$`).exec(path);
  if (task) return { tab: "home", task: task[1]! };
  const goal = new RegExp(`^${ROOT}/goal/(${UUID})$`).exec(path);
  if (goal) return { tab: "goals", goal: goal[1]! };
  if (path === `${ROOT}/goals`) return { tab: "goals" };
  if (path === `${ROOT}/done`) return { tab: "done" };
  if (path === `${ROOT}/categories`) return { tab: "categories" };
  if (path === `${ROOT}/settings`) return { tab: "settings" };
  return { tab: "home" };
}

export function pathOf(to: Route): string {
  if (to.tab === "goals" && to.goal) return `${ROOT}/goal/${to.goal}`;
  if (to.tab === "home" && to.task) return `${ROOT}/task/${to.task}`;
  if (to.tab === "goals") return `${ROOT}/goals`;
  if (to.tab === "done") return `${ROOT}/done`;
  if (to.tab === "categories") return `${ROOT}/categories`;
  if (to.tab === "settings") return `${ROOT}/settings`;
  return `${ROOT}/`;
}

export function App() {
  const t = useT();
  const [path, setPath] = useState(() => window.location.pathname);
  const read = useResource("categories", readCategories, { persist: true });
  const categories = useMemo(() => read.data ?? [], [read.data]);
  const reload = useCallback(() => changed(), []);

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
  const context = useMemo(() => ({ list: categories, reload }), [categories, reload]);
  const closeTask = useCallback(() => {
    if (route(window.location.pathname).tab === "home") go({ tab: "home" }, true);
  }, [go]);
  const openGoal = useCallback((goal: string) => go({ tab: "goals", goal }), [go]);

  return (
    <CategoriesContext.Provider value={context}>
      <ToastHost>
        <AppShell
          label={t("app.sections")}
          active={current.tab === "categories" ? "settings" : current.tab}
          onSelect={(id) => go({ tab: id } as Route)}
          tabs={[
            { id: "home", label: t("tab.tasks"), icon: "list" },
            { id: "goals", label: t("tab.goals"), icon: "target" },
            { id: "done", label: t("tab.history"), icon: "done" },
            SETTINGS_TAB,
          ]}
        >
          {current.tab === "goals" &&
            (current.goal ? (
              <GoalScreen key={current.goal} id={current.goal} onBack={() => go({ tab: "goals" })} />
            ) : (
              <GoalsScreen onOpen={openGoal} />
            ))}
          {current.tab === "home" && <HomeScreen openTask={current.task} onClosed={closeTask} />}
          {current.tab === "done" && <HistoryScreen onOpenGoal={openGoal} />}
          {current.tab === "settings" && (
            <AppSettings app={APP}>
              <Section title={t("settings.categories")}>
                <List>
                  <ListRow
                    title={t("settings.categories")}
                    subtitle={t("settings.categories_detail")}
                    icon="layers"
                    accessory="chevron-right"
                    onClick={() => go({ tab: "categories" })}
                  />
                </List>
              </Section>
            </AppSettings>
          )}
          {current.tab === "categories" && <CategoriesScreen />}
          {current.tab === "goals" && !current.goal && (
            <footer className="goals-version">
              <AppVersion />
            </footer>
          )}
        </AppShell>
      </ToastHost>
    </CategoriesContext.Provider>
  );
}
