import { useRoute } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB, Skeleton } from "@openarga/ui";
import { Suspense, lazy } from "react";

import { AgendaScreen } from "./Agenda";
import { AgendaSettings } from "./AgendaSettings";
import { EventScreen } from "./EventScreen";
import { ExploreScreen } from "./Explore";
import { APP } from "./Header";
import { WishScreen } from "./WishScreen";
import { WishesScreen } from "./Wishes";

const MapScreen = lazy(() => import("./MapScreen").then((found) => ({ default: found.MapScreen })));

const ROOT = "/outings";
const UUID = "([0-9a-f-]{36})";

export type Route =
  | { tab: "agenda" }
  | { tab: "explore" }
  | { tab: "map" }
  | { tab: "wishes" }
  | { tab: "settings" }
  | { tab: "event"; id: string; from?: "explore" }
  | { tab: "wish"; id: string };

export function route(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "");
  if (path === `${ROOT}/ajustes`) return { tab: "settings" };
  if (path === `${ROOT}/ganas`) return { tab: "wishes" };
  if (path === `${ROOT}/mapa`) return { tab: "map" };
  if (path === `${ROOT}/explorar`) return { tab: "explore" };
  const wish = new RegExp(`^${ROOT}/ganas/${UUID}$`).exec(path);
  if (wish) return { tab: "wish", id: wish[1]! };
  const event = new RegExp(`^${ROOT}/eventos/${UUID}$`).exec(path);
  if (event) return { tab: "event", id: event[1]! };
  const explored = new RegExp(`^${ROOT}/explorar/${UUID}$`).exec(path);
  if (explored) return { tab: "event", id: explored[1]!, from: "explore" };
  return { tab: "agenda" };
}

export function pathOf(to: Route): string {
  if (to.tab === "settings") return `${ROOT}/ajustes`;
  if (to.tab === "wishes") return `${ROOT}/ganas`;
  if (to.tab === "map") return `${ROOT}/mapa`;
  if (to.tab === "explore") return `${ROOT}/explorar`;
  if (to.tab === "event" && to.from === "explore") return `${ROOT}/explorar/${to.id}`;
  if (to.tab === "wish") return `${ROOT}/ganas/${to.id}`;
  if (to.tab === "event") return `${ROOT}/eventos/${to.id}`;
  return `${ROOT}/`;
}

const TAB_OF: Record<Route["tab"], "agenda" | "explore" | "map" | "wishes" | "settings"> = {
  agenda: "agenda",
  explore: "explore",
  map: "map",
  event: "agenda",
  wishes: "wishes",
  wish: "wishes",
  settings: "settings",
};

export function App() {
  const [current, navigate] = useRoute(route, pathOf);

  return (
    <AppShell
      label="Secciones"
      active={current.tab === "event" && current.from === "explore" ? "explore" : TAB_OF[current.tab]}
      onSelect={(tab) => navigate({ tab })}
      tabs={[
        { id: "agenda", label: "Agenda", icon: "calendar" },
        { id: "explore", label: "Explorar", icon: "search" },
        { id: "map", label: "Mapa", icon: "map" },
        { id: "wishes", label: "Ganas", icon: "bookmark" },
        SETTINGS_TAB,
      ]}
    >
      {current.tab === "agenda" && (
        <AgendaScreen
          onOpen={(event) => navigate({ tab: "event", id: event.id })}
          onOpenId={(id) => navigate({ tab: "event", id })}
          onExplore={() => navigate({ tab: "explore" })}
        />
      )}
      {current.tab === "explore" && (
        <ExploreScreen onOpen={(event) => navigate({ tab: "event", id: event.id, from: "explore" })} />
      )}
      {current.tab === "event" && (
        <EventScreen
          key={current.id}
          id={current.id}
          backLabel={current.from === "explore" ? "Explorar" : "Agenda"}
          onBack={() => navigate({ tab: current.from === "explore" ? "explore" : "agenda" })}
          onWish={(id) => navigate({ tab: "wish", id })}
        />
      )}
      {current.tab === "map" && (
        <Suspense fallback={<Skeleton rows={3} />}>
          <MapScreen onWish={(id) => navigate({ tab: "wish", id })} onEvent={(id) => navigate({ tab: "event", id })} onAdd={() => navigate({ tab: "wishes" })} />
        </Suspense>
      )}
      {current.tab === "wishes" && <WishesScreen onOpen={(wish) => navigate({ tab: "wish", id: wish.id })} />}
      {current.tab === "wish" && (
        <WishScreen
          key={current.id}
          id={current.id}
          onBack={() => navigate({ tab: "wishes" })}
          onEvent={(id) => navigate({ tab: "event", id })}
        />
      )}
      {current.tab === "settings" && (
        <AppSettings app={APP}>
          <AgendaSettings />
        </AppSettings>
      )}
    </AppShell>
  );
}
