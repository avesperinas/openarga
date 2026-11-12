import { renderToString } from "react-dom/server";

import type { Catalogue } from "./api";
import { MusclePicker, cycleMuscle, describeMuscles, fromLevels, hasPrimary, onePrimary, toLevels } from "./Muscles";

const CATALOGUE: Catalogue = {
  exercises: [],
  gyms: [],
  muscles: [
    { id: "chest", name: "Pecho", region: "upper" },
    { id: "triceps", name: "Tríceps", region: "upper" },
    { id: "front_delts", name: "Deltoide anterior", region: "upper" },
    { id: "quads", name: "Cuádriceps", region: "lower" },
  ],
};

describe("los músculos de un ejercicio", () => {
  it("principal es 1 y secundario 0,5, en los dos sentidos", () => {
    const muscles = { chest: 1, triceps: 0.5 } as const;
    expect(toLevels(muscles)).toEqual({ chest: "primary", triceps: "secondary" });
    expect(fromLevels(toLevels(muscles))).toEqual(muscles);
  });

  it("sin principal no cuenta como completo", () => {
    expect(hasPrimary({})).toBe(false);
    expect(hasPrimary({ triceps: 0.5 })).toBe(false);
    expect(hasPrimary({ chest: 1 })).toBe(true);
  });

  it("un principal nuevo deja al anterior de secundario, sin quitarlo", () => {
    expect(onePrimary({ lats: "primary" }, { lats: "primary", upper_back: "primary" })).toEqual({
      lats: "secondary",
      upper_back: "primary",
    });
    expect(onePrimary({ lats: "primary" }, { lats: "primary", biceps: "secondary" })).toEqual({
      lats: "primary",
      biceps: "secondary",
    });
  });

  it("el resumen pone primero los principales", () => {
    expect(describeMuscles({ triceps: 0.5, chest: 1, front_delts: 0.5 }, CATALOGUE)).toBe(
      "Pecho · Tríceps, Deltoide anterior",
    );
  });

  it("se eligen por zona", () => {
    const html = renderToString(<MusclePicker catalogue={CATALOGUE} value={{ quads: 1 }} onChange={() => undefined} />);
    expect(html).toContain("Tren superior");
    expect(html).toContain("Tren inferior");
    expect(html).not.toContain(">Core<");
    expect(html).toContain('aria-label="Cuádriceps: principal"');
  });

  it("en el cuerpo, tocar recorre principal, secundario y nada (T-B05)", () => {
    expect(cycleMuscle({}, "chest")).toEqual({ chest: 1 });
    expect(cycleMuscle({ chest: 1 }, "chest")).toEqual({ chest: 0.5 });
    expect(cycleMuscle({ chest: 0.5 }, "chest")).toEqual({});
    expect(cycleMuscle({ chest: 1 }, "triceps")).toEqual({ chest: 0.5, triceps: 1 });
  });

  it("pinta lo elegido sobre el cuerpo, cada músculo un botón con su nivel", () => {
    const html = renderToString(<MusclePicker catalogue={CATALOGUE} value={{ chest: 1 }} onChange={() => undefined} />);
    expect(html).toContain('aria-label="Qué trabaja, de frente"');
    expect(html).toMatch(/data-muscle="chest"[^>]*role="button"[^>]*aria-label="Pecho: principal"/);
  });
});
