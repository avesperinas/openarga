import { withTransition } from "@openarga/app";
import { AppSettings, AppShell, SETTINGS_TAB } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { EditorScreen } from "./Editor";
import { APP } from "./Header";
import { PantryScreen } from "./Pantry";
import { RecipeScreen } from "./Recipe";
import { RecipesScreen } from "./Recipes";

const ROOT = "/recipes";
const RECIPE = new RegExp(`^${ROOT}/receta/([0-9a-f-]{36})(/editar)?/?$`);

type Tab = "recipes" | "pantry" | "settings";

export type Route =
  | { screen: Tab }
  | { screen: "recipe"; id: string }
  | { screen: "edit"; id: string }
  | { screen: "new" };

const PATHS: Record<Tab, string> = {
  recipes: `${ROOT}/`,
  pantry: `${ROOT}/despensa`,
  settings: `${ROOT}/ajustes`,
};

export function route(pathname: string): Route {
  const match = RECIPE.exec(pathname);
  if (match?.[1]) return match[2] ? { screen: "edit", id: match[1] } : { screen: "recipe", id: match[1] };
  const path = pathname.replace(/\/+$/, "");
  if (path === `${ROOT}/nueva`) return { screen: "new" };
  if (path === PATHS.pantry) return { screen: "pantry" };
  if (path === PATHS.settings) return { screen: "settings" };
  return { screen: "recipes" };
}

export function App() {
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
  const openRecipe = (id: string) => navigate(`${ROOT}/receta/${id}`);

  if (current.screen === "recipe") {
    return (
      <RecipeScreen
        key={current.id}
        id={current.id}
        onBack={() => navigate(PATHS.recipes)}
        onEdit={(id) => navigate(`${ROOT}/receta/${id}/editar`)}
      />
    );
  }
  if (current.screen === "edit" || current.screen === "new") {
    const id = current.screen === "edit" ? current.id : undefined;
    return (
      <EditorScreen
        key={id ?? "nueva"}
        id={id}
        onDone={(saved) => replace(`${ROOT}/receta/${saved}`)}
        onCancel={() => navigate(id ? `${ROOT}/receta/${id}` : PATHS.recipes)}
      />
    );
  }

  return (
    <AppShell
      label="Secciones"
      active={current.screen}
      onSelect={(tab) => navigate(PATHS[tab as Tab])}
      tabs={[
        { id: "recipes", label: "Recetario", icon: "book" },
        { id: "pantry", label: "Despensa", icon: "basket" },
        SETTINGS_TAB,
      ]}
    >
      {current.screen === "recipes" && (
        <RecipesScreen onOpen={openRecipe} onNew={() => navigate(`${ROOT}/nueva`)} />
      )}
      {current.screen === "pantry" && <PantryScreen />}
      {current.screen === "settings" && <AppSettings app={APP} />}
    </AppShell>
  );
}
