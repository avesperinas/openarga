import { useRoute } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB, ToastHost } from "@openarga/ui";

import { APP } from "./Header";
import { HistoryScreen } from "./History";
import { ShoppingScreen } from "./Shopping";

const ROOT = "/shopping";

type Tab = "list" | "history" | "settings";

const PATHS: Record<Tab, string> = {
  list: `${ROOT}/`,
  history: `${ROOT}/historial`,
  settings: `${ROOT}/ajustes`,
};

const pathOf = (tab: Tab) => PATHS[tab];

export function route(pathname: string): Tab {
  const path = pathname.replace(/\/+$/, "");
  if (path === PATHS.history) return "history";
  if (path === PATHS.settings) return "settings";
  return "list";
}

export function App() {
  const [current, navigate] = useRoute(route, pathOf);

  return (
    <ToastHost>
      <AppShell
        label="Secciones"
        active={current}
        onSelect={navigate}
        tabs={[
          { id: "list", label: "Lista", icon: "basket" },
          { id: "history", label: "Historial", icon: "calendar" },
          SETTINGS_TAB,
        ]}
      >
        {current === "list" && <ShoppingScreen />}
        {current === "history" && <HistoryScreen onList={() => navigate("list")} />}
        {current === "settings" && <AppSettings app={APP} />}
      </AppShell>
    </ToastHost>
  );
}
