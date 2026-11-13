import { SETTINGS_TAB, TabBar, useT } from "@openarga/ui";
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
  training: `${ROOT}/training`,
  sleep: `${ROOT}/sleep`,
  health: `${ROOT}/health`,
  steps: `${ROOT}/steps`,
  weight: `${ROOT}/weight`,
  body: `${ROOT}/body`,
  labs: `${ROOT}/labs`,
  heartday: `${ROOT}/health/heart-day`,
  rhythm: `${ROOT}/health/rhythm`,
  figure: `${ROOT}/health/figure`,
  settings: `${ROOT}/settings`,
};

const FIGURE = new RegExp(`^${ROOT}/health/figure/([a-z0-9_]+)$`);

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
  const t = useT();
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
        label={t("tabs.label")}
        active={tabOf(current)}
        onSelect={(tab) => navigate(PATHS[tab])}
        items={[
          { id: "today", label: t("tabs.today"), icon: "today" },
          { id: "training", label: t("tabs.training"), icon: "flame" },
          { id: "sleep", label: t("tabs.sleep"), icon: "moon" },
          { id: "health", label: t("tabs.health"), icon: "heart" },
          SETTINGS_TAB,
        ]}
      />
    </>
  );
}
