import { useResource, useRoute } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB } from "@openarga/ui";
import { useCallback } from "react";

import { type Genre, readGenres } from "./api";
import { BookScreen } from "./BookScreen";
import { APP } from "./Header";
import { LibraryScreen } from "./Library";
import { StatsScreen } from "./Stats";

const ROOT = "/library";

export type Route = { tab: "shelf" } | { tab: "stats" } | { tab: "settings" } | { tab: "book"; id: string };

export function route(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "");
  if (path === `${ROOT}/stats`) return { tab: "stats" };
  if (path === `${ROOT}/settings`) return { tab: "settings" };
  const book = new RegExp(`^${ROOT}/books/([0-9a-f-]{36})$`).exec(path);
  if (book) return { tab: "book", id: book[1]! };
  return { tab: "shelf" };
}

export function pathOf(to: Route): string {
  if (to.tab === "stats") return `${ROOT}/stats`;
  if (to.tab === "settings") return `${ROOT}/settings`;
  if (to.tab === "book") return `${ROOT}/books/${to.id}`;
  return `${ROOT}/`;
}

export function App() {
  const [current, navigate] = useRoute(route, pathOf);
  const genres: Genre[] = useResource("genres", readGenres, { staleMs: Infinity, persist: true }).data ?? [];

  const openBook = useCallback((id: string) => navigate({ tab: "book", id }), [navigate]);

  return (
    <AppShell
      label="Secciones"
      active={current.tab === "stats" || current.tab === "settings" ? current.tab : "shelf"}
      onSelect={(tab) => navigate({ tab })}
      tabs={[
        { id: "shelf", label: "Estantería", icon: "book" },
        { id: "stats", label: "Estadísticas", icon: "chart" },
        SETTINGS_TAB,
      ]}
      detail={
        current.tab === "book" && (
          <BookScreen key={current.id} id={current.id} genres={genres} onBack={() => navigate({ tab: "shelf" })} />
        )
      }
    >
      {(current.tab === "shelf" || current.tab === "book") && (
        <LibraryScreen genres={genres} onOpen={(book) => openBook(book.id)} />
      )}
      {current.tab === "stats" && <StatsScreen onOpen={openBook} onShelf={() => navigate({ tab: "shelf" })} />}
      {current.tab === "settings" && <AppSettings app={APP} />}
    </AppShell>
  );
}
