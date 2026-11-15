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
import { t } from "./lang";

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

const SECTIONS: readonly CourseTab[] = ["subjects", "schedule", "assessments", "materials", "notes"];

const OLD: Record<string, string> = {
  semana: "week",
  apuntes: "notes",
  archivo: "archive",
  ajustes: "settings",
  estudio: "course",
  asignatura: "subject",
  clase: "session",
  evaluable: "assessment",
  asignaturas: "subjects",
  horario: "schedule",
  evaluables: "assessments",
  materiales: "materials",
};

const english = (path: string) => path.replace(/[a-z]+/g, (part) => OLD[part] ?? part);

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function route(pathname: string, _search = ""): Route {
  const path = english(pathname.replace(/\/+$/, ""));
  const one = (name: string) => new RegExp(`^${ROOT}/${name}/${ID}$`).exec(path)?.[1];
  if (path === `${ROOT}/week`) return { tab: "home" };
  if (path === `${ROOT}/notes`) return { tab: "notes" };
  if (path === `${ROOT}/archive`) return { tab: "archive" };
  if (path === `${ROOT}/settings`) return { tab: "settings" };
  const course = new RegExp(`^${ROOT}/course/${ID}(?:/(\\w+))?$`).exec(path);
  if (course) {
    const section = SECTIONS.find((one) => one === course[2]);
    return section ? { tab: "course", id: course[1]!, section } : { tab: "course", id: course[1]! };
  }
  for (const [name, tab] of [
    ["notes", "note"],
    ["subject", "subject"],
    ["session", "session"],
    ["assessment", "assessment"],
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
      return `${ROOT}/notes`;
    case "note":
      return `${ROOT}/notes/${to.id}`;
    case "archive":
      return `${ROOT}/archive`;
    case "settings":
      return `${ROOT}/settings`;
    case "course":
      return to.section && to.section !== "subjects" ? `${ROOT}/course/${to.id}/${to.section}` : `${ROOT}/course/${to.id}`;
    case "subject":
      return `${ROOT}/subject/${to.id}`;
    case "session":
      return `${ROOT}/session/${to.id}`;
    case "assessment":
      return `${ROOT}/assessment/${to.id}`;
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
        label={t("nav.sections")}
        active={tab}
        onSelect={(next) => navigate({ tab: next as "home" | "notes" | "settings" })}
        tabs={[
          { id: "home", label: t("app.name"), icon: "today" },
          { id: "notes", label: t("notes.title"), icon: "edit" },
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
