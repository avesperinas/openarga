import { withTransition } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB, useT } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { EditorScreen } from "./Editor";
import { APP } from "./Header";
import { PantryScreen } from "./Pantry";
import { RecipeScreen } from "./Recipe";
import { RecipesScreen } from "./Recipes";

const ROOT = "/recipes";
const RECIPE = new RegExp(`^${ROOT}/recipe/([0-9a-f-]{36})(/edit)?/?$`);

type Tab = "recipes" | "pantry" | "settings";

export type Route =
  | { screen: Tab }
  | { screen: "recipe"; id: string }
  | { screen: "edit"; id: string }
  | { screen: "new" };

const PATHS: Record<Tab, string> = {
  recipes: `${ROOT}/`,
  pantry: `${ROOT}/pantry`,
  settings: `${ROOT}/settings`,
};

export function route(pathname: string): Route {
  const match = RECIPE.exec(pathname);
  if (match?.[1]) return match[2] ? { screen: "edit", id: match[1] } : { screen: "recipe", id: match[1] };
  const path = pathname.replace(/\/+$/, "");
  if (path === `${ROOT}/new`) return { screen: "new" };
  if (path === PATHS.pantry) return { screen: "pantry" };
  if (path === PATHS.settings) return { screen: "settings" };
  return { screen: "recipes" };
}

export function App() {
  const t = useT();
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const back = () => withTransition(() => setPath(window.location.pathname));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const navigate = useCallback((to: string) => {
    if (to === window.location.pathname) return;
    withTransition(() => {
      window.history.pushState(null, "", to);
      setPath(to);
      window.scrollTo(0, 0);
    });
  }, []);

  const replace = useCallback((to: string) => {
    withTransition(() => {
      window.history.replaceState(null, "", to);
      setPath(to);
      window.scrollTo(0, 0);
    });
  }, []);

  const current = route(path);
  const openRecipe = (id: string) => navigate(`${ROOT}/recipe/${id}`);

  if (current.screen === "recipe") {
    return (
      <RecipeScreen
        key={current.id}
        id={current.id}
        onBack={() => navigate(PATHS.recipes)}
        onEdit={(id) => navigate(`${ROOT}/recipe/${id}/edit`)}
      />
    );
  }
  if (current.screen === "edit" || current.screen === "new") {
    const id = current.screen === "edit" ? current.id : undefined;
    return (
      <EditorScreen
        key={id ?? "new"}
        id={id}
        onDone={(saved) => replace(`${ROOT}/recipe/${saved}`)}
        onCancel={() => navigate(id ? `${ROOT}/recipe/${id}` : PATHS.recipes)}
      />
    );
  }

  return (
    <AppShell
      label={t("tabs.label")}
      active={current.screen}
      onSelect={(tab) => navigate(PATHS[tab as Tab])}
      tabs={[
        { id: "recipes", label: t("tabs.recipes"), icon: "book" },
        { id: "pantry", label: t("tabs.pantry"), icon: "basket" },
        SETTINGS_TAB,
      ]}
    >
      {current.screen === "recipes" && (
        <RecipesScreen onOpen={openRecipe} onNew={() => navigate(`${ROOT}/new`)} />
      )}
      {current.screen === "pantry" && <PantryScreen />}
      {current.screen === "settings" && <AppSettings app={APP} />}
    </AppShell>
  );
}
