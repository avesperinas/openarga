import { useRoute } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB, Skeleton } from "@openarga/ui";
import { Suspense, lazy } from "react";

import { AgendaScreen } from "./Agenda";
import { AgendaSettings } from "./AgendaSettings";
import { EventScreen } from "./EventScreen";
import { ExploreScreen } from "./Explore";
import { APP } from "./Header";
import { t } from "./lang";
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
  if (path === `${ROOT}/settings`) return { tab: "settings" };
  if (path === `${ROOT}/wishes`) return { tab: "wishes" };
  if (path === `${ROOT}/map`) return { tab: "map" };
  if (path === `${ROOT}/explore`) return { tab: "explore" };
  const wish = new RegExp(`^${ROOT}/wishes/${UUID}$`).exec(path);
  if (wish) return { tab: "wish", id: wish[1]! };
  const event = new RegExp(`^${ROOT}/events/${UUID}$`).exec(path);
  if (event) return { tab: "event", id: event[1]! };
  const explored = new RegExp(`^${ROOT}/explore/${UUID}$`).exec(path);
  if (explored) return { tab: "event", id: explored[1]!, from: "explore" };
  return { tab: "agenda" };
}

export function pathOf(to: Route): string {
  if (to.tab === "settings") return `${ROOT}/settings`;
  if (to.tab === "wishes") return `${ROOT}/wishes`;
  if (to.tab === "map") return `${ROOT}/map`;
  if (to.tab === "explore") return `${ROOT}/explore`;
  if (to.tab === "event" && to.from === "explore") return `${ROOT}/explore/${to.id}`;
  if (to.tab === "wish") return `${ROOT}/wishes/${to.id}`;
  if (to.tab === "event") return `${ROOT}/events/${to.id}`;
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
      label={t("app.sections")}
      active={current.tab === "event" && current.from === "explore" ? "explore" : TAB_OF[current.tab]}
      onSelect={(tab) => navigate({ tab })}
      tabs={[
        { id: "agenda", label: t("tab.agenda"), icon: "calendar" },
        { id: "explore", label: t("tab.explore"), icon: "search" },
        { id: "map", label: t("tab.map"), icon: "map" },
        { id: "wishes", label: t("tab.wishes"), icon: "bookmark" },
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
          backLabel={current.from === "explore" ? t("tab.explore") : t("tab.agenda")}
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
