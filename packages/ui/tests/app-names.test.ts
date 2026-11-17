import { describe, expect, it } from "vitest";

import { APP_NAMES, APP_NAME_MAX, appNameOf } from "../src/app-names";

describe("app names", () => {
  it("with nothing chosen, or with the standard set, the manifest's", () => {
    expect(appNameOf("planner", "Planner")).toBe("Planner");
    expect(appNameOf("vitals", "Vitals", { app_names: "standard" })).toBe("Vitals");
  });

  it("each set renames its own and leaves what it does not know as it was", () => {
    expect(appNameOf("vitals", "Vitals", { app_names: "arga" })).toBe("Pulso");
    expect(appNameOf("vitals", "Vitals", { app_names: "greek" })).toBe("Asclepius");
    expect(appNameOf("recipes", "Recipes", { app_names: "arga" })).toBe("Recipes");
    expect(appNameOf("nuevo", "Nuevo", { app_names: "greek" })).toBe("Nuevo");
  });

  it("yours, and the usual one where you wrote nothing", () => {
    const mine = { app_names: "custom" as const, custom_app_names: { planner: "Agenda", vitals: "  " } };

    expect(appNameOf("planner", "Planner", mine)).toBe("Agenda");
    expect(appNameOf("vitals", "Vitals", mine)).toBe("Vitals");
    expect(appNameOf("study", "Study", mine)).toBe("Study");
  });

  it("no name in a set repeats or goes past what fits", () => {
    for (const names of Object.values(APP_NAMES)) {
      const all = Object.values(names);
      expect(new Set(all).size).toBe(all.length);
      for (const name of all) expect(name.length).toBeLessThanOrEqual(APP_NAME_MAX);
    }
  });
});
