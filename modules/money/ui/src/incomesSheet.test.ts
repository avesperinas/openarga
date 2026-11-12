import { describe, expect, it } from "vitest";

import { carreraNote, sourceLabel } from "./IncomesSheet";

const year = { year: 2027, space_id: null };

describe("de dónde sale cada ingreso (ADR-0104)", () => {
  it("dice la cifra de Carrera cuando la hay", () => {
    const note = carreraNote({ ...year, carrera: { me: 36000, other: null } }, "me", false);
    expect(note).toMatch(/^36\.000,00\s€ netos en 2027/u);
  });

  it("sin cifra, cuentan los tramos, y dice por qué", () => {
    const none = { ...year, carrera: { me: null, other: null } };
    expect(carreraNote(none, "me", false)).toBe("Carrera aún no tiene tu neto de 2027: cuentan tus tramos.");
    expect(carreraNote(none, "other", false)).toMatch(/^Elige abajo el espacio/);
    expect(carreraNote(none, "other", true)).toMatch(/^Aún no lo comparte/);
  });

  it("nombra cada fuente", () => {
    expect(sourceLabel("typed")).toBe("A mano");
    expect(sourceLabel("carrera")).toBe("De Carrera");
  });
});
