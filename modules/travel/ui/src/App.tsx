import { withTransition } from "@openarga/app";
import { useOfflineQueue } from "@openarga/app/offline";
import { AppSettings, AppShell, Button, EmptyState, Notice, OfflineNotice, SETTINGS_TAB, Screen } from "@openarga/ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { type Atlas, queue, readAtlas, signIn } from "./api";
import { lived } from "./atlas";
import { APP, ScreenHeader } from "./Header";
import { later } from "./Later";
import { Pending, changed, useLoad } from "./Loads";
import { TodayScreen } from "./Today";
import { forgetStoredLock, lockedTrip, setLock } from "./tripApp";
import { TripsScreen } from "./Trips";
import { t } from "./lang";

const MapScreen = later(() => import("./MapScreen").then((found) => found.MapScreen));
const JourneyScreen = later(() => import("./Journey").then((found) => found.JourneyScreen));
const IdeaScreen = later(() => import("./IdeaScreen").then((found) => found.IdeaScreen));
const TripScreen = later(() => import("./TripScreen").then((found) => found.TripScreen));
const DaysScreen = later(() => import("./Days").then((found) => found.DaysScreen));
const DayMapScreen = later(() => import("./DayMap").then((found) => found.DayMapScreen));
const BookingsScreen = later(() => import("./Bookings").then((found) => found.BookingsScreen));
const TripMapScreen = later(() => import("./TripMap").then((found) => found.TripMapScreen));
const EditorScreen = later(() => import("./Editor").then((found) => found.EditorScreen));
const StatsScreen = later(() => import("./Stats").then((found) => found.StatsScreen));
const TripAppScreen = later(() => import("./TripAppScreen").then((found) => found.TripAppScreen));

const ROOT = "/travel";

export type Route =
  | { screen: "map" }
  | { screen: "today" }
  | { screen: "plans" }
  | { screen: "trips" }
  | { screen: "journey" }
  | { screen: "trip"; id: string }
  | { screen: "idea"; id: string }
  | { screen: "days"; id: string }
  | { screen: "day"; id: string; day: string }
  | { screen: "tripmap"; id: string }
  | { screen: "money"; id: string }
  | { screen: "tripapp"; id: string }
  | { screen: "notes"; id: string }
  | { screen: "journal"; id: string }
  | { screen: "tripsettings"; id: string }
  | { screen: "bookings"; id: string }
  | { screen: "edit"; id: string | null }
  | { screen: "stats" }
  | { screen: "settings" };

type Tab = "today" | "map" | "plans" | "trips" | "stats" | "settings";

const OLD: Record<string, string> = {
  hoy: "today",
  planes: "plans",
  viajes: "trips",
  viaje: "trip",
  recorrido: "journey",
  nuevo: "new",
  estadisticas: "stats",
  ajustes: "settings",
  editar: "edit",
  dias: "days",
  dinero: "money",
  notas: "notes",
  diario: "journal",
  mapa: "map",
  reservas: "bookings",
};

const english = (path: string) => path.replace(/[a-z]+/g, (part) => OLD[part] ?? part);

export function route(pathname: string): Route {
  const path = english(pathname.replace(/\/+$/, "").slice(ROOT.length));
  if (path === "/today") return { screen: "today" };
  if (path === "/plans") return { screen: "plans" };
  if (path === "/trips") return { screen: "trips" };
  const idea = /^\/ideas\/([0-9a-f-]{36})$/.exec(path);
  if (idea) return { screen: "idea", id: idea[1]! };
  if (path === "/journey") return { screen: "journey" };
  if (path === "/new") return { screen: "edit", id: null };
  if (path === "/stats") return { screen: "stats" };
  if (path === "/settings") return { screen: "settings" };
  const edit = /^\/trips\/([0-9a-f-]{36})\/edit$/.exec(path);
  if (edit) return { screen: "edit", id: edit[1]! };
  const oneDay = /^\/trips\/([0-9a-f-]{36})\/days\/(\d{4}-\d{2}-\d{2})$/.exec(path);
  if (oneDay) return { screen: "day", id: oneDay[1]!, day: oneDay[2]! };
  const days = /^\/trips\/([0-9a-f-]{36})\/days$/.exec(path);
  if (days) return { screen: "days", id: days[1]! };
  const app = /^\/trip\/([0-9a-f-]{36})$/.exec(path);
  if (app) return { screen: "tripapp", id: app[1]! };
  const section = /^\/trips\/([0-9a-f-]{36})\/(money|notes|journal|settings)$/.exec(path);
  if (section) {
    const screens = { money: "money", notes: "notes", journal: "journal", settings: "tripsettings" } as const;
    const screen = screens[section[2] as keyof typeof screens];
    return { screen, id: section[1]! };
  }
  const tripMap = /^\/trips\/([0-9a-f-]{36})\/map$/.exec(path);
  if (tripMap) return { screen: "tripmap", id: tripMap[1]! };
  const bookings = /^\/trips\/([0-9a-f-]{36})\/bookings$/.exec(path);
  if (bookings) return { screen: "bookings", id: bookings[1]! };
  const trip = /^\/trips\/([0-9a-f-]{36})$/.exec(path);
  if (trip) return { screen: "trip", id: trip[1]! };
  return { screen: "map" };
}

export function pathOf(to: Route): string {
  switch (to.screen) {
    case "map":
      return `${ROOT}/`;
    case "today":
      return `${ROOT}/today`;
    case "plans":
      return `${ROOT}/plans`;
    case "trips":
      return `${ROOT}/trips`;
    case "journey":
      return `${ROOT}/journey`;
    case "trip":
      return `${ROOT}/trips/${to.id}`;
    case "idea":
      return `${ROOT}/ideas/${to.id}`;
    case "days":
      return `${ROOT}/trips/${to.id}/days`;
    case "day":
      return `${ROOT}/trips/${to.id}/days/${to.day}`;
    case "bookings":
      return `${ROOT}/trips/${to.id}/bookings`;
    case "tripmap":
      return `${ROOT}/trips/${to.id}/map`;
    case "money":
      return `${ROOT}/trips/${to.id}/money`;
    case "tripapp":
      return `${ROOT}/trip/${to.id}`;
    case "notes":
      return `${ROOT}/trips/${to.id}/notes`;
    case "journal":
      return `${ROOT}/trips/${to.id}/journal`;
    case "tripsettings":
      return `${ROOT}/trips/${to.id}/settings`;
    case "edit":
      return to.id ? `${ROOT}/trips/${to.id}/edit` : `${ROOT}/new`;
    case "stats":
      return `${ROOT}/stats`;
    case "settings":
      return `${ROOT}/settings`;
  }
}

const TAB: Record<Route["screen"], Tab | null> = {
  map: "map",
  today: "today",
  plans: "plans",
  trips: "trips",
  journey: "trips",
  trip: "trips",
  idea: "plans",
  days: "trips",
  day: "trips",
  tripmap: null,
  money: "trips",
  tripapp: null,
  notes: "trips",
  journal: "trips",
  tripsettings: "trips",
  bookings: "trips",
  edit: null,
  stats: "stats",
  settings: "settings",
};

export type Navigate = (to: Route) => void;

const OUTSIDE = new Set<Route["screen"]>(["map", "plans", "trips", "journey", "stats", "idea"]);

export function App() {
  const [path, setPath] = useState(() => window.location.pathname);
  const read = useLoad<Atlas>("atlas", readAtlas);
  const atlas = read.data;
  const problem = !atlas && read.found.error ? read.found.error.message : "";
  const reload = changed;
  const retry = read.found.refresh;

  const offline = useOfflineQueue(queue);

  useEffect(forgetStoredLock, []);

  useEffect(() => {
    const back = () => withTransition(() => setPath(window.location.pathname));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const locked = lockedTrip(path);
  setLock(locked);
  const lockedRef = useRef(locked);
  lockedRef.current = locked;
  const navigate = useCallback<Navigate>((wanted) => {
    const inside = lockedRef.current;
    const to: Route =
      inside && OUTSIDE.has(wanted.screen) ? { screen: "tripapp", id: inside } : wanted;
    const next = pathOf(to);
    if (next === window.location.pathname) return;
    withTransition(() => {
      window.history.pushState(null, "", next);
      setPath(next);
      window.scrollTo(0, 0);
    });
  }, []);

  const trips = atlas?.trips ?? null;
  const done = useMemo(() => (trips === null ? null : lived(trips)), [trips]);
  const others = atlas?.others ?? [];
  const home = atlas?.home ?? null;
  const current = route(path);
  const unlived = "id" in current && (trips ?? []).some((one) => one.id === current.id && one.phase !== "done");
  const tab = TAB[current.screen] === "trips" && unlived ? "plans" : TAB[current.screen];
  const travelling = (trips ?? []).some((one) => one.phase === "ongoing");
  const landed = useRef(false);
  useEffect(() => {
    if (landed.current || trips === null) return;
    landed.current = true;
    if (travelling && !lockedRef.current && route(window.location.pathname).screen === "map") {
      window.history.replaceState(null, "", pathOf({ screen: "today" }));
      setPath(pathOf({ screen: "today" }));
    }
  }, [trips, travelling]);

  const notices = (
    <div className="travel-offline">
      <OfflineNotice pending={offline.pending} />
      {offline.signedOut && (
        <Notice tone="warning" title={t("app.signed_out")}>
          {t("app.sign_in_to_send")}{" "}
          <Button variant="plain" onClick={signIn}>
            {t("app.sign_in")}
          </Button>
        </Notice>
      )}
      {offline.refused.map((one) => (
        <Notice key={one.key} tone="negative" title={t("app.not_saved", { what: one.what })}>
          {one.problem}{" "}
          <Button variant="plain" onClick={() => void offline.retry(one.key!)}>
            {t("app.retry")}
          </Button>
          <Button variant="plain" onClick={() => void offline.dismiss(one.key!)}>
            {t("app.forget")}
          </Button>
        </Notice>
      ))}
    </div>
  );

  const screen = (
    <>
      {current.screen === "today" && <TodayScreen navigate={navigate} />}
      {current.screen === "map" && (
        <MapScreen trips={done} others={others} home={home} problem={problem} onRetry={retry} navigate={navigate} />
      )}
      {(current.screen === "plans" || current.screen === "trips") && (
        <TripsScreen
          kind={current.screen}
          trips={trips}
          ideas={atlas?.ideas ?? []}
          others={others}
          home={home}
          problem={problem}
          onRetry={retry}
          navigate={navigate}
          onChanged={reload}
        />
      )}
      {current.screen === "journey" &&
        (done && done.length > 0 ? (
          <JourneyScreen trips={done} home={home} navigate={navigate} />
        ) : (
          <Screen>
            <ScreenHeader title={t("app.journey")} back={{ label: t("nav.trips"), onClick: () => navigate({ screen: "trips" }) }} />
            {done ? (
              <EmptyState
                icon="globe"
                title={t("app.journey_empty")}
                action={{ label: t("stats.add_trip"), icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }}
              >
                {t("app.journey_empty_detail")}
              </EmptyState>
            ) : (
              <Pending found={read.found} label={t("trips.loading")} />
            )}
          </Screen>
        ))}
      {current.screen === "idea" && <IdeaScreen key={current.id} id={current.id} navigate={navigate} onChanged={reload} />}
      {(current.screen === "trip" || current.screen === "money" || current.screen === "notes" || current.screen === "journal") && (
        <TripScreen key={current.id} id={current.id} tab={current.screen} home={home} navigate={navigate} onChanged={reload} />
      )}
      {current.screen === "tripsettings" && (
        <TripScreen key={current.id} id={current.id} tab="settings" home={home} navigate={navigate} onChanged={reload} />
      )}
      {current.screen === "days" && <DaysScreen key={current.id} id={current.id} navigate={navigate} />}
      {current.screen === "day" && <DayMapScreen key={`${current.id}-${current.day}`} id={current.id} day={current.day} navigate={navigate} />}
      {current.screen === "bookings" && <BookingsScreen key={current.id} id={current.id} navigate={navigate} />}
      {current.screen === "tripmap" && <TripMapScreen key={current.id} id={current.id} navigate={navigate} />}
      {current.screen === "edit" && <EditorScreen id={current.id} navigate={navigate} onChanged={reload} />}
      {current.screen === "stats" && <StatsScreen trips={done} navigate={navigate} />}
      {current.screen === "settings" && <AppSettings app={APP} />}
      {current.screen === "tripapp" && <TripAppScreen key={current.id} id={current.id} navigate={navigate} />}
    </>
  );

  if (!tab || locked) {
    return (
      <>
        {notices}
        {screen}
      </>
    );
  }
  return (
    <AppShell
      label={t("app.sections")}
      active={tab}
      onSelect={(id) => navigate({ screen: id })}
      tabs={[
        ...(travelling || current.screen === "today" ? [{ id: "today" as const, label: t("today.title"), icon: "today" as const }] : []),
        { id: "map", label: t("days.map"), icon: "map" },
        { id: "plans", label: t("nav.plans"), icon: "plane" },
        { id: "trips", label: t("nav.trips"), icon: "globe" },
        { id: "stats", label: t("stats.title"), icon: "chart" },
        SETTINGS_TAB,
      ]}
    >
      {notices}
      {screen}
    </AppShell>
  );
}
