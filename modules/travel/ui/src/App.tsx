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

export function route(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "").slice(ROOT.length);
  if (path === "/hoy") return { screen: "today" };
  if (path === "/planes") return { screen: "plans" };
  if (path === "/viajes") return { screen: "trips" };
  const idea = /^\/ideas\/([0-9a-f-]{36})$/.exec(path);
  if (idea) return { screen: "idea", id: idea[1]! };
  if (path === "/recorrido") return { screen: "journey" };
  if (path === "/nuevo") return { screen: "edit", id: null };
  if (path === "/estadisticas") return { screen: "stats" };
  if (path === "/ajustes") return { screen: "settings" };
  const edit = /^\/viajes\/([0-9a-f-]{36})\/editar$/.exec(path);
  if (edit) return { screen: "edit", id: edit[1]! };
  const oneDay = /^\/viajes\/([0-9a-f-]{36})\/dias\/(\d{4}-\d{2}-\d{2})$/.exec(path);
  if (oneDay) return { screen: "day", id: oneDay[1]!, day: oneDay[2]! };
  const days = /^\/viajes\/([0-9a-f-]{36})\/dias$/.exec(path);
  if (days) return { screen: "days", id: days[1]! };
  const app = /^\/viaje\/([0-9a-f-]{36})$/.exec(path);
  if (app) return { screen: "tripapp", id: app[1]! };
  const section = /^\/viajes\/([0-9a-f-]{36})\/(dinero|notas|diario|ajustes)$/.exec(path);
  if (section) {
    const screens = { dinero: "money", notas: "notes", diario: "journal", ajustes: "tripsettings" } as const;
    const screen = screens[section[2] as keyof typeof screens];
    return { screen, id: section[1]! };
  }
  const tripMap = /^\/viajes\/([0-9a-f-]{36})\/mapa$/.exec(path);
  if (tripMap) return { screen: "tripmap", id: tripMap[1]! };
  const bookings = /^\/viajes\/([0-9a-f-]{36})\/reservas$/.exec(path);
  if (bookings) return { screen: "bookings", id: bookings[1]! };
  const trip = /^\/viajes\/([0-9a-f-]{36})$/.exec(path);
  if (trip) return { screen: "trip", id: trip[1]! };
  return { screen: "map" };
}

export function pathOf(to: Route): string {
  switch (to.screen) {
    case "map":
      return `${ROOT}/`;
    case "today":
      return `${ROOT}/hoy`;
    case "plans":
      return `${ROOT}/planes`;
    case "trips":
      return `${ROOT}/viajes`;
    case "journey":
      return `${ROOT}/recorrido`;
    case "trip":
      return `${ROOT}/viajes/${to.id}`;
    case "idea":
      return `${ROOT}/ideas/${to.id}`;
    case "days":
      return `${ROOT}/viajes/${to.id}/dias`;
    case "day":
      return `${ROOT}/viajes/${to.id}/dias/${to.day}`;
    case "bookings":
      return `${ROOT}/viajes/${to.id}/reservas`;
    case "tripmap":
      return `${ROOT}/viajes/${to.id}/mapa`;
    case "money":
      return `${ROOT}/viajes/${to.id}/dinero`;
    case "tripapp":
      return `${ROOT}/viaje/${to.id}`;
    case "notes":
      return `${ROOT}/viajes/${to.id}/notas`;
    case "journal":
      return `${ROOT}/viajes/${to.id}/diario`;
    case "tripsettings":
      return `${ROOT}/viajes/${to.id}/ajustes`;
    case "edit":
      return to.id ? `${ROOT}/viajes/${to.id}/editar` : `${ROOT}/nuevo`;
    case "stats":
      return `${ROOT}/estadisticas`;
    case "settings":
      return `${ROOT}/ajustes`;
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
        <Notice tone="warning" title="Sin sesión">
          Inicia sesión para enviar lo apuntado sin conexión.{" "}
          <Button variant="plain" onClick={signIn}>
            Entrar
          </Button>
        </Notice>
      )}
      {offline.refused.map((one) => (
        <Notice key={one.key} tone="negative" title={`No se pudo guardar ${one.what}`}>
          {one.problem}{" "}
          <Button variant="plain" onClick={() => void offline.retry(one.key!)}>
            Reintentar
          </Button>
          <Button variant="plain" onClick={() => void offline.dismiss(one.key!)}>
            Olvidarlo
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
            <ScreenHeader title="Recorrido" back={{ label: "Viajes", onClick: () => navigate({ screen: "trips" }) }} />
            {done ? (
              <EmptyState
                icon="globe"
                title="Aún no hay nada que recorrer"
                action={{ label: "Añadir un viaje", icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }}
              >
                El recorrido pinta los viajes hechos, uno detrás de otro.
              </EmptyState>
            ) : (
              <Pending found={read.found} label="Cargando los viajes" />
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
      label="Secciones"
      active={tab}
      onSelect={(id) => navigate({ screen: id })}
      tabs={[
        ...(travelling || current.screen === "today" ? [{ id: "today" as const, label: "Hoy", icon: "today" as const }] : []),
        { id: "map", label: "Mapa", icon: "map" },
        { id: "plans", label: "Planes", icon: "plane" },
        { id: "trips", label: "Viajes", icon: "globe" },
        { id: "stats", label: "Cifras", icon: "chart" },
        SETTINGS_TAB,
      ]}
    >
      {notices}
      {screen}
    </AppShell>
  );
}
