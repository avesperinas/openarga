import { describe, expect, it } from "vitest";

import { clock, longDay, money, shortDay, todayIso } from "../src/format";

describe("fechas, horas y dinero, en España y a la hora de aquí", () => {
  it("hoy es el día de Madrid, no el de UTC", () => {
    expect(todayIso(new Date("2025-12-31T23:30:00Z"))).toBe("2026-01-01");
  });

  it("un día sin hora se lee tal cual, sin moverse de día", () => {
    expect(shortDay("2026-09-20")).toBe("20 sept");
  });

  it("un instante se lee en Madrid, con la primera en mayúscula", () => {
    expect(longDay("2026-09-22T23:30:00Z")).toBe("Miércoles, 23 de septiembre");
    expect(clock("2026-09-22T07:05:00Z")).toBe("09:05");
  });

  it("el dinero con céntimos solo si los hay", () => {
    expect(money(1234.5)).toBe("1234,50\u00a0€");
    expect(money(20)).toBe("20\u00a0€");
    expect(money(Number.NaN)).toBe("—");
  });
});
