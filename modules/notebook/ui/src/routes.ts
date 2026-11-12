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

export function route(pathname: string, search = ""): Route {
  const path = pathname.replace(/\/+$/, "");
  const params = new URLSearchParams(search);
  const note = new RegExp(`^${ROOT}/nota/${ID}$`).exec(path);
  if (note) return { screen: "note", id: note[1]! };
  if (path === `${ROOT}/buscar`) return { screen: "search", q: params.get("q") ?? "", tag: params.get("tag") ?? "" };
  if (path === `${ROOT}/papelera`) return { screen: "trash" };
  if (path === `${ROOT}/hoy`) return { screen: "today" };
  if (path === `${ROOT}/importar`) return { screen: "import" };
  if (path === `${ROOT}/notas`) return { screen: "home" };
  if (path === `${ROOT}/repasar`) return { screen: "review" };
  if (path === `${ROOT}/ajustes`) return { screen: "settings" };
  return { screen: "graph" };
}

export function pathOf(to: Route): string {
  switch (to.screen) {
    case "home":
      return `${ROOT}/notas`;
    case "note":
      return `${ROOT}/nota/${to.id}`;
    case "search": {
      const params = new URLSearchParams();
      if (to.q) params.set("q", to.q);
      if (to.tag) params.set("tag", to.tag);
      const query = params.toString();
      return `${ROOT}/buscar${query ? `?${query}` : ""}`;
    }
    case "trash":
      return `${ROOT}/papelera`;
    case "today":
      return `${ROOT}/hoy`;
    case "import":
      return `${ROOT}/importar`;
    case "graph":
      return `${ROOT}/`;
    case "review":
      return `${ROOT}/repasar`;
    case "settings":
      return `${ROOT}/ajustes`;
  }
}
