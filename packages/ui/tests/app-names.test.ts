import { describe, expect, it } from "vitest";

import { APP_NAMES, APP_NAME_MAX, appNameOf } from "../src/app-names";

describe("los nombres de las apps", () => {
  it("sin elegir nada, o con el estándar, el del manifiesto", () => {
    expect(appNameOf("planner", "Planner")).toBe("Planner");
    expect(appNameOf("vitals", "Vitals", { app_names: "standard" })).toBe("Vitals");
  });

  it("cada juego renombra lo suyo y deja lo que no conoce como estaba", () => {
    expect(appNameOf("vitals", "Vitals", { app_names: "arga" })).toBe("Pulso");
    expect(appNameOf("vitals", "Vitals", { app_names: "greek" })).toBe("Asclepius");
    expect(appNameOf("recipes", "Recipes", { app_names: "arga" })).toBe("Recipes");
    expect(appNameOf("nuevo", "Nuevo", { app_names: "greek" })).toBe("Nuevo");
  });

  it("los tuyos, y el de siempre donde no has escrito nada", () => {
    const mine = { app_names: "custom" as const, custom_app_names: { planner: "Agenda", vitals: "  " } };

    expect(appNameOf("planner", "Planner", mine)).toBe("Agenda");
    expect(appNameOf("vitals", "Vitals", mine)).toBe("Vitals");
    expect(appNameOf("study", "Study", mine)).toBe("Study");
  });

  it("ningún nombre de un juego se repite ni pasa de lo que cabe", () => {
    for (const names of Object.values(APP_NAMES)) {
      const all = Object.values(names);
      expect(new Set(all).size).toBe(all.length);
      for (const name of all) expect(name.length).toBeLessThanOrEqual(APP_NAME_MAX);
    }
  });
});
