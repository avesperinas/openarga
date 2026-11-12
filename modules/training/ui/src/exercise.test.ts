import type { Machine, VariantPoint } from "./api";
import { advice, normalRange, recordIds, recordStreak } from "./exercise";

const point = (id: string, e1rm: number, reps = 5, load = 100, status: VariantPoint["status"] = "counted"): VariantPoint => ({
  id,
  session_id: `s-${id}`,
  day: `2026-09-${id.padStart(2, "0")}`,
  reps,
  load,
  e1rm,
  reliable: true,
  status,
  reference: null,
  verdict: null,
});

const machine = (points: VariantPoint[], without_pr = 0): Machine => ({
  gym_id: "g",
  gym: "Centro",
  first_day: points[0]?.day ?? "",
  last_day: points[points.length - 1]?.day ?? "",
  points,
  segments: [],
  marks: [],
  best: [...points].filter((one) => one.status === "counted").sort((a, b) => b.e1rm - a.e1rm)[0] ?? null,
  records: [],
  without_pr,
  excluded: 0,
});

describe("los récords de la línea", () => {
  it("son los días que superan todo lo anterior, sin contar el primero", () => {
    expect([...recordIds([point("1", 100), point("2", 98), point("3", 101), point("4", 101)])]).toEqual(["3"]);
  });

  it("un día apartado no es récord ni sube el listón", () => {
    expect([...recordIds([point("1", 100), point("2", 140, 5, 100, "high"), point("3", 102)])]).toEqual(["3"]);
  });

  it("la racha cuenta los últimos seguidos", () => {
    expect(recordStreak([point("1", 100), point("2", 99), point("3", 101), point("4", 103)])).toBe(2);
    expect(recordStreak([point("1", 100), point("2", 101), point("3", 99)])).toBe(0);
  });
});

describe("el rango normal", () => {
  it("son los cuartiles de las últimas sesiones", () => {
    expect(normalRange([100, 102, 104, 106, 108].map((value, index) => point(String(index + 1), value)))).toEqual({
      low: 102,
      high: 106,
    });
  });

  it("con menos de cuatro no hay rango", () => {
    expect(normalRange([point("1", 100), point("2", 101), point("3", 102)])).toBeNull();
  });
});

describe("lo que dice", () => {
  it("con racha, la dice; y el peso para el récord, al paso del aparato", () => {
    const said = advice(machine([point("1", 100), point("2", 105, 5, 90), point("3", 108, 5, 92.5)]), 2.5, true);

    expect(said[0]).toBe("Dos sesiones seguidas con récord.");
    expect(said[1]).toBe("Para un récord la próxima vez: 5 × 95 kg.");
  });

  it("sin récord en tres sesiones, lo dice y propone salidas", () => {
    const said = advice(machine([point("1", 110), point("2", 100), point("3", 101), point("4", 100)], 3), 2.5, true);

    expect(said[0]).toContain("Llevas 3 sesiones sin récord aquí");
  });

  it("con peso corporal, las repeticiones con el mismo lastre", () => {
    const said = advice(machine([point("1", 100, 8, 82), point("2", 96, 8, 80)]), 2.5, false);

    expect(said).toEqual(["Para un récord la próxima vez: 8 repeticiones con el mismo lastre."]);
  });

  it("sin sesiones que cuenten no dice nada", () => {
    expect(advice(machine([]), 2.5, true)).toEqual([]);
  });
});
