import "./money.css";

import { EmptyState, Notice, SETTINGS_TAB, Screen, Skeleton, TabBar, ToastHost, useT } from "@openarga/ui";
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


export function App() {
  const t = useT();
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
          title={problem === "session" ? t("app.sign_in_again") : t("app.load_failed")}
          action={problem === "session" ? { label: t("app.sign_in"), onClick: () => window.location.assign("/login") } : { label: t("common.retry"), onClick: refresh }}
        />
      </Screen>
    );
  } else if (!state) {
    body = (
      <Screen>
        <ScreenHeader title={t(`tab.${tab}`)} />
        <Skeleton rows={8} label={t("app.loading")} />
      </Screen>
    );
  } else if (!state.configured && tab !== "settings") {
    body = (
      <Screen>
        <ScreenHeader title={t(`tab.${tab}`)} />
        <EmptyState icon="wallet" title={t("app.no_accounts")} action={{ label: t("app.go_settings"), onClick: () => go("settings") }}>
          {t("app.no_accounts_body")}
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
        onMovements={({ from, to, category }) => go("movements", `?from=${from}&to=${to}&category=${category}`)}
      />
    );
  } else {
    body = <SettingsScreen state={state} onChanged={refresh} />;
  }

  return (
    <ToastHost>
      {body}
      <TabBar
        label={t("tab.label")}
        active={tab}
        onSelect={(next) => go(next)}
        items={[
          { id: "summary", label: t("tab.summary"), icon: "today" },
          { id: "movements", label: t("tab.movements"), icon: "list" },
          { id: "shared", label: t("tab.shared"), icon: "people" },
          { id: "analysis", label: t("tab.analysis"), icon: "chart" },
          SETTINGS_TAB,
        ]}
      />
    </ToastHost>
  );
}
