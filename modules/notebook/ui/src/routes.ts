export const ROOT = "/notebook";
const ID = "([0-9a-f-]{36})";

export type Route =
  | { screen: "home" }
  | { screen: "note"; id: string }
  | { screen: "search"; q: string; tag: string }
  | { screen: "trash" }
  | { screen: "today" }
  | { screen: "import" }
  | { screen: "graph" }
  | { screen: "review" }
  | { screen: "settings" };

const SCREENS: Record<string, Route["screen"]> = {
  notes: "home",
  notas: "home",
  trash: "trash",
  papelera: "trash",
  today: "today",
  hoy: "today",
  import: "import",
  importar: "import",
  review: "review",
  repasar: "review",
  settings: "settings",
  ajustes: "settings",
};

export function route(pathname: string, search = ""): Route {
  const path = pathname.replace(/\/+$/, "");
  const params = new URLSearchParams(search);
  const note = new RegExp(`^${ROOT}/(?:note|nota)/${ID}$`).exec(path);
  if (note) return { screen: "note", id: note[1]! };
  const name = path.startsWith(`${ROOT}/`) ? path.slice(ROOT.length + 1) : "";
  if (name === "search" || name === "buscar") return { screen: "search", q: params.get("q") ?? "", tag: params.get("tag") ?? "" };
  const screen = SCREENS[name];
  return screen ? ({ screen } as Route) : { screen: "graph" };
}

export function pathOf(to: Route): string {
  switch (to.screen) {
    case "home":
      return `${ROOT}/notes`;
    case "note":
      return `${ROOT}/note/${to.id}`;
    case "search": {
      const params = new URLSearchParams();
      if (to.q) params.set("q", to.q);
      if (to.tag) params.set("tag", to.tag);
      const query = params.toString();
      return `${ROOT}/search${query ? `?${query}` : ""}`;
    }
    case "graph":
      return `${ROOT}/`;
    default:
      return `${ROOT}/${to.screen}`;
  }
}
