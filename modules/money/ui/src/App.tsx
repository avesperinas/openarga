import "./money.css";

import { EmptyState, Notice, SETTINGS_TAB, Screen, Skeleton, TabBar, ToastHost } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { ScreenHeader } from "./Header";
import { type State, Unauthorised, api } from "./api";
import { AnalysisScreen } from "./Analysis";
import { MovementsScreen } from "./Movements";
import { SummaryScreen } from "./Summary";
import { SettingsScreen } from "./Settings";
import { SharedScreen } from "./Shared";

export const ROOT = "/money";

export type Tab = "summary" | "movements" | "shared" | "analysis" | "settings";

export const PATHS: Record<Tab, string> = {
  summary: `${ROOT}`,
  movements: `${ROOT}/movements`,
  shared: `${ROOT}/shared`,
  analysis: `${ROOT}/analysis`,
  settings: `${ROOT}/settings`,
};

export function tabOf(pathname: string): Tab {
  const path = pathname.replace(/\/+$/, "");
  if (path === PATHS.movements) return "movements";
  if (path === PATHS.shared) return "shared";
  if (path === PATHS.analysis) return "analysis";
  if (path === PATHS.settings) return "settings";
  return "summary";
}

const TITLES: Record<Tab, string> = {
  summary: "Resumen",
  movements: "Movimientos",
  shared: "Compartido",
  analysis: "Análisis",
  settings: "Ajustes",
};

export function App() {
  const [tab, setTab] = useState<Tab>(() => tabOf(window.location.pathname));
  const [state, setState] = useState<State | null>(null);
  const [problem, setProblem] = useState<"session" | "failed" | null>(null);

  const refresh = useCallback(() => {
    api.state().then(
      (s) => {
        setState(s);
        setProblem(null);
      },
      (e) => setProblem(e instanceof Unauthorised ? "session" : "failed"),
    );
  }, []);

  useEffect(refresh, [refresh]);

  useEffect(() => {
    const back = () => setTab(tabOf(window.location.pathname));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const go = (next: Tab, search = "") => {
    if (next === tab && !search) return;
    window.history.pushState(null, "", `${PATHS[next]}${search}`);
    setTab(next);
    window.scrollTo(0, 0);
  };

  let body: React.ReactNode;
  if (problem) {
    body = (
      <Screen>
        <ScreenHeader title="Money" />
        <Notice
          tone="negative"
          title={problem === "session" ? "Tienes que volver a entrar" : "No se ha podido cargar Money"}
          action={problem === "session" ? { label: "Entrar", onClick: () => window.location.assign("/login") } : { label: "Reintentar", onClick: refresh }}
        />
      </Screen>
    );
  } else if (!state) {
    body = (
      <Screen>
        <ScreenHeader title={TITLES[tab]} />
        <Skeleton rows={8} label="Cargando Money" />
      </Screen>
    );
  } else if (!state.configured && tab !== "settings") {
    body = (
      <Screen>
        <ScreenHeader title={TITLES[tab]} />
        <EmptyState icon="wallet" title="Aún no hay cuentas" action={{ label: "Ir a Ajustes", onClick: () => go("settings") }}>
          Importa tu configuración (cuentas, categorías y reglas) y Money interpretará los movimientos que traen tus
          bancos.
        </EmptyState>
      </Screen>
    );
  } else if (tab === "summary") {
    body = <SummaryScreen state={state} onPending={() => go("movements", "?status=pending")} />;
  } else if (tab === "movements") {
    body = <MovementsScreen state={state} onChanged={refresh} />;
  } else if (tab === "shared") {
    body = <SharedScreen state={state} onChanged={refresh} />;
  } else if (tab === "analysis") {
    body = (
      <AnalysisScreen
        state={state}
        onMovements={({ from, to, category }) => go("movements", `?desde=${from}&hasta=${to}&categoria=${category}`)}
      />
    );
  } else {
    body = <SettingsScreen state={state} onChanged={refresh} />;
  }

  return (
    <ToastHost>
      {body}
      <TabBar
        label="Secciones"
        active={tab}
        onSelect={(next) => go(next)}
        items={[
          { id: "summary", label: "Resumen", icon: "today" },
          { id: "movements", label: "Movimientos", icon: "list" },
          { id: "shared", label: "Compartido", icon: "people" },
          { id: "analysis", label: "Análisis", icon: "chart" },
          SETTINGS_TAB,
        ]}
      />
    </ToastHost>
  );
}
