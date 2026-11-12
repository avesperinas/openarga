import { describe, expect, it } from "vitest";

import { nearDefault } from "./EventScreen";
import { freshSince, freshTitle } from "./words";

describe("lo nuevo en Explorar", () => {
  it("el aviso dice desde qué día; sin él, la última semana", () => {
    expect(freshSince("2026-11-05", "2026-11-06")).toEqual({ since: "2026-11-05", fromNotice: true });
    expect(freshSince(null, "2026-11-06")).toEqual({ since: "2026-10-31", fromNotice: false });
    expect(freshSince("mañana", "2026-11-06").fromNotice).toBe(false);
    expect(freshSince("2026-12-01", "2026-11-06").fromNotice).toBe(false);
  });

  it("su título dice de cuándo es", () => {
    expect(freshTitle("2026-11-06", true, "2026-11-06")).toBe("Lo nuevo de hoy");
    expect(freshTitle("2026-11-05", true, "2026-11-06")).toBe("Lo nuevo desde el jueves 5");
    expect(freshTitle("2026-10-31", false, "2026-11-06")).toBe("Lo nuevo esta semana");
  });
});

describe("las ganas cerca de un evento", () => {
  const near = (kind: "eat" | "plan" | "getaway", n: number) =>
    Array.from({ length: n }, (_, i) => ({ id: `${kind}${i}`, name: `${kind} ${i}`, kind, km: 1 }));

  it("se abre el primer tipo que no es comer, y con solo restaurantes, nada", () => {
    expect(nearDefault([...near("eat", 17), ...near("plan", 2)])).toBe("plan");
    expect(nearDefault([...near("eat", 3), ...near("getaway", 1)])).toBe("getaway");
    expect(nearDefault(near("eat", 17))).toBeNull();
  });
});
