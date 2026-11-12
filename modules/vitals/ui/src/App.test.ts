import { describe, expect, it } from "vitest";

import { route, tabOf } from "./App";
import { parseSteps } from "./Settings";

describe("las direcciones de Vitals", () => {
  it("cada página tiene la suya, las de antes siguen valiendo, y cualquier otra cosa es Hoy", () => {
    expect(route("/vitals/")).toBe("today");
    expect(route("/vitals")).toBe("today");
    expect(route("/vitals/entrenar")).toBe("training");
    expect(route("/vitals/salud")).toBe("health");
    expect(route("/vitals/pasos")).toBe("steps");
    expect(route("/vitals/sueno")).toBe("sleep");
    expect(route("/vitals/peso")).toBe("weight");
    expect(route("/vitals/cuerpo")).toBe("body");
    expect(route("/vitals/analiticas")).toBe("labs");
    expect(route("/vitals/ajustes/")).toBe("settings");
    expect(route("/vitals/otra")).toBe("today");
  });

  it("las páginas de Salud dejan encendida su pestaña", () => {
    expect(tabOf(route("/vitals/analiticas"))).toBe("health");
    expect(tabOf(route("/vitals/pasos"))).toBe("health");
    expect(tabOf(route("/vitals/entrenar"))).toBe("training");
  });
});

describe("los pasos del objetivo", () => {
  it("aceptan el punto de miles y rechazan lo que no son pasos", () => {
    expect(parseSteps("8.000")).toBe(8000);
    expect(parseSteps("8000")).toBe(8000);
    expect(parseSteps("")).toBeNull();
    expect(parseSteps("50")).toBeNull();
    expect(parseSteps("muchos")).toBeNull();
  });
});
