import { withTransition } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB } from "@openarga/ui";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { ArchiveScreen } from "./Archive";
import { AssessmentRedirect } from "./AssessmentRedirect";
import { CourseScreen } from "./CourseScreen";
import { APP } from "./Header";
import { HomeScreen } from "./Home";
import { NoteScreen, NotesScreen } from "./Notes";
import { SessionScreen } from "./SessionScreen";
import { SubjectScreen } from "./SubjectScreen";

const ROOT = "/study";
const ID = "([0-9a-f-]{36})";

export type CourseTab = "subjects" | "schedule" | "assessments" | "materials" | "notes";

export type Route =
  | { tab: "home" }
  | { tab: "notes" }
  | { tab: "note"; id: string }
  | { tab: "archive" }
  | { tab: "settings" }
  | { tab: "course"; id: string; section?: CourseTab }
  | { tab: "subject"; id: string }
  | { tab: "session"; id: string }
  | { tab: "assessment"; id: string };

const SECTIONS: Record<string, CourseTab> = {
  asignaturas: "subjects",
  horario: "schedule",
  evaluables: "assessments",
  materiales: "materials",
  apuntes: "notes",
};

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function route(pathname: string, _search = ""): Route {
  const path = pathname.replace(/\/+$/, "");
  const one = (name: string) => new RegExp(`^${ROOT}/${name}/${ID}$`).exec(path)?.[1];
  if (path === `${ROOT}/semana`) return { tab: "home" };
  if (path === `${ROOT}/apuntes`) return { tab: "notes" };
  if (path === `${ROOT}/archivo`) return { tab: "archive" };
  if (path === `${ROOT}/ajustes`) return { tab: "settings" };
  const course = new RegExp(`^${ROOT}/estudio/${ID}(?:/(\\w+))?$`).exec(path);
  if (course) {
    const section = course[2] ? SECTIONS[course[2]] : undefined;
    return section ? { tab: "course", id: course[1]!, section } : { tab: "course", id: course[1]! };
  }
  for (const [name, tab] of [
    ["apuntes", "note"],
    ["asignatura", "subject"],
    ["clase", "session"],
    ["evaluable", "assessment"],
  ] as const) {
    const id = one(name);
    if (id) return { tab, id };
  }
  return { tab: "home" };
}

export function pathOf(to: Route): string {
  switch (to.tab) {
    case "home":
      return `${ROOT}/`;
    case "notes":
      return `${ROOT}/apuntes`;
    case "note":
      return `${ROOT}/apuntes/${to.id}`;
    case "archive":
      return `${ROOT}/archivo`;
    case "settings":
      return `${ROOT}/ajustes`;
    case "course": {
      const section = Object.entries(SECTIONS).find(([, value]) => value === to.section)?.[0];
      return section && to.section !== "subjects" ? `${ROOT}/estudio/${to.id}/${section}` : `${ROOT}/estudio/${to.id}`;
    }
    case "subject":
      return `${ROOT}/asignatura/${to.id}`;
    case "session":
      return `${ROOT}/clase/${to.id}`;
    case "assessment":
      return `${ROOT}/evaluable/${to.id}`;
  }
}

type Navigate = (to: Route, options?: { replace?: boolean }) => void;

const NavContext = createContext<Navigate>(() => undefined);

export const useNavigate = () => useContext(NavContext);

export function App() {
  const [location, setLocation] = useState(() => ({
    path: window.location.pathname,
    search: window.location.search,
  }));

  useEffect(() => {
    const back = () =>
      withTransition(() => setLocation({ path: window.location.pathname, search: window.location.search }));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const navigate = useCallback<Navigate>((to, options) => {
    const target = pathOf(to);
    if (target === window.location.pathname + window.location.search) return;
    withTransition(() => {
      if (options?.replace) window.history.replaceState(null, "", target);
      else window.history.pushState(null, "", target);
      const url = new URL(target, window.location.origin);
      setLocation({ path: url.pathname, search: url.search });
      if (!options?.replace) window.scrollTo(0, 0);
    });
  }, []);

  const current = route(location.path, location.search);
  const tab =
    current.tab === "settings"
      ? current.tab
      : current.tab === "notes" || current.tab === "note"
        ? "notes"
        : "home";

  return (
    <NavContext.Provider value={navigate}>
      <AppShell
        label="Secciones"
        active={tab}
        onSelect={(next) => navigate({ tab: next as "home" | "notes" | "settings" })}
        tabs={[
          { id: "home", label: "Study", icon: "today" },
          { id: "notes", label: "Apuntes", icon: "edit" },
          SETTINGS_TAB,
        ]}
      >
        {current.tab === "home" && <HomeScreen />}
        {current.tab === "notes" && <NotesScreen />}
        {current.tab === "note" && <NoteScreen key={current.id} id={current.id} />}
        {current.tab === "archive" && <ArchiveScreen />}
        {current.tab === "settings" && <AppSettings app={APP} />}
        {current.tab === "course" && (
          <CourseScreen key={current.id} id={current.id} section={current.section ?? "subjects"} />
        )}
        {current.tab === "subject" && <SubjectScreen key={current.id} id={current.id} />}
        {current.tab === "session" && <SessionScreen key={current.id} id={current.id} />}
        {current.tab === "assessment" && <AssessmentRedirect key={current.id} id={current.id} />}
      </AppShell>
    </NavContext.Provider>
  );
}
