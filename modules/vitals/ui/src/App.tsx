import { SETTINGS_TAB, TabBar } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { FigureScreen, HeartDayScreen, RhythmScreen } from "./Figure";
import { LabsScreen } from "./Labs";
import { SettingsScreen } from "./Settings";
import { SleepScreen } from "./Sleep";
import { StepsScreen } from "./Steps";
import { type Place, SummaryScreen } from "./Summary";
import { TodayScreen } from "./Today";
import { TrainingScreen } from "./Training";
import { WeightScreen } from "./Weight";

const ROOT = "/vitals";

type Page =
  | "today"
  | "training"
  | "sleep"
  | "health"
  | "steps"
  | "weight"
  | "body"
  | "labs"
  | "heartday"
  | "rhythm"
  | "figure"
  | "settings";
type Tab = "today" | "training" | "sleep" | "health" | "settings";

const PATHS: Record<Page, string> = {
  today: `${ROOT}/`,
  training: `${ROOT}/entrenar`,
  sleep: `${ROOT}/sueno`,
  health: `${ROOT}/salud`,
  steps: `${ROOT}/pasos`,
  weight: `${ROOT}/peso`,
  body: `${ROOT}/cuerpo`,
  labs: `${ROOT}/analiticas`,
  heartday: `${ROOT}/salud/vitals-del-dia`,
  rhythm: `${ROOT}/salud/ritmo`,
  figure: `${ROOT}/salud/cifra`,
  settings: `${ROOT}/ajustes`,
};

const FIGURE = new RegExp(`^${ROOT}/salud/cifra/([a-z0-9_]+)$`);

export function figureOf(pathname: string): string | null {
  return FIGURE.exec(pathname.replace(/\/+$/, ""))?.[1] ?? null;
}

const TAB_OF: Record<Page, Tab> = {
  today: "today",
  training: "training",
  sleep: "sleep",
  health: "health",
  steps: "health",
  weight: "health",
  body: "health",
  labs: "health",
  heartday: "health",
  rhythm: "health",
  figure: "health",
  settings: "settings",
};

export function route(pathname: string): Page {
  if (figureOf(pathname)) return "figure";
  const path = pathname.replace(/\/+$/, "");
  const found = (Object.keys(PATHS) as Page[]).find((page) => page !== "today" && PATHS[page] === path);
  return found ?? "today";
}

export function tabOf(page: Page): Tab {
  return TAB_OF[page];
}

export function App() {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const back = () => setPath(window.location.pathname);
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const navigate = useCallback((to: string) => {
    if (to === window.location.pathname) return;
    window.history.pushState(null, "", to);
    setPath(to);
    window.scrollTo(0, 0);
  }, []);

  const current = route(path);
  const go = (place: Place) => navigate(PATHS[place]);
  const toHealth = () => navigate(PATHS.health);

  return (
    <>
      {current === "today" && <TodayScreen go={(place) => navigate(PATHS[place])} />}
      {current === "training" && <TrainingScreen />}
      {current === "sleep" && <SleepScreen onSettings={() => navigate(PATHS.settings)} />}
      {(current === "health" || current === "body") && (
        <SummaryScreen go={go} openFigure={(id) => navigate(`${PATHS.figure}/${id}`)} />
      )}
      {current === "steps" && <StepsScreen onSettings={() => navigate(PATHS.settings)} onBack={toHealth} />}
      {current === "weight" && <WeightScreen onBack={toHealth} />}
      {current === "labs" && <LabsScreen onBack={toHealth} />}
      {current === "heartday" && <HeartDayScreen onBack={toHealth} />}
      {current === "rhythm" && <RhythmScreen onBack={toHealth} />}
      {current === "figure" && <FigureScreen id={figureOf(path) ?? ""} onBack={toHealth} />}
      {current === "settings" && <SettingsScreen />}
      <TabBar
        label="Secciones"
        active={tabOf(current)}
        onSelect={(tab) => navigate(PATHS[tab])}
        items={[
          { id: "today", label: "Hoy", icon: "today" },
          { id: "training", label: "Entrenar", icon: "flame" },
          { id: "sleep", label: "Dormir", icon: "moon" },
          { id: "health", label: "Salud", icon: "heart" },
          SETTINGS_TAB,
        ]}
      />
    </>
  );
}
