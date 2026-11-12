import { useResource, withTransition } from "@openarga/app";
import { AppSettings, AppShell, List, ListRow, SETTINGS_TAB, Section, ToastHost } from "@openarga/ui";
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
  const task = new RegExp(`^${ROOT}/tarea/(${UUID})$`).exec(path);
  if (task) return { tab: "home", task: task[1]! };
  const goal = new RegExp(`^${ROOT}/meta/(${UUID})$`).exec(path);
  if (goal) return { tab: "goals", goal: goal[1]! };
  if (path === `${ROOT}/metas`) return { tab: "goals" };
  if (path === `${ROOT}/hechas`) return { tab: "done" };
  if (path === `${ROOT}/categorias`) return { tab: "categories" };
  if (path === `${ROOT}/ajustes`) return { tab: "settings" };
  return { tab: "home" };
}

export function pathOf(to: Route): string {
  if (to.tab === "goals" && to.goal) return `${ROOT}/meta/${to.goal}`;
  if (to.tab === "home" && to.task) return `${ROOT}/tarea/${to.task}`;
  if (to.tab === "goals") return `${ROOT}/metas`;
  if (to.tab === "done") return `${ROOT}/hechas`;
  if (to.tab === "categories") return `${ROOT}/categorias`;
  if (to.tab === "settings") return `${ROOT}/ajustes`;
  return `${ROOT}/`;
}

export function App() {
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
          label="Secciones"
          active={current.tab === "categories" ? "settings" : current.tab}
          onSelect={(id) => go({ tab: id } as Route)}
          tabs={[
            { id: "home", label: "Tareas", icon: "list" },
            { id: "goals", label: "KPIs", icon: "target" },
            { id: "done", label: "Histórico", icon: "done" },
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
              <Section title="Categorías">
                <List>
                  <ListRow
                    title="Categorías"
                    subtitle="Las mismas para los KPIs y las tareas: nombre, color, orden y compartir"
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
