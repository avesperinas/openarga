import { describe, expect, it } from "vitest";

import type { Baseline, Load } from "./api";
import { baselineTile, byName, byWeek, elapsed, fromFirstLoad, groupLine, minutesLabel, rollingMean, zoneShares } from "./workouts";

const base: Baseline = {
  id: "resting_heart_rate",
  name: "FC en reposo",
  unit: "lpm",
  digits: 0,
  day: "2026-10-13",
  value: 64,
  mean: 56,
  low: 54,
  high: 58,
  status: "above",
  days: 30,
};

describe("tu normal", () => {
  it("fuera de la banda se dice en ámbar, sin juicio", () => {
    expect(baselineTile(base)).toEqual({
      value: "64 lpm",
      foot: "por encima de tu normal · 54 lpm – 58 lpm",
      tone: "warning",
    });
  });

  it("dentro, sin color; sin 14 días, sin comparar; sin dato, se dice", () => {
    expect(baselineTile({ ...base, value: 56, status: "inside" }).tone).toBe("neutral");
    expect(baselineTile({ ...base, status: null, low: null, high: null, days: 9 }).foot).toBe(
      "aún sin tu normal (9 de 14 días)",
    );
    expect(baselineTile({ ...base, value: null }).foot).toBe("sin dato de hoy ni de ayer");
  });

  it("el sueño va en horas y la temperatura con su signo", () => {
    expect(baselineTile({ ...base, unit: "min", value: 425, low: 400, high: 460, status: "inside" }).value).toBe("7 h 05");
    expect(baselineTile({ ...base, unit: "°C", digits: 1, value: 0.4, status: "inside" }).value).toBe("+0,4 °C");
  });
});

describe("las cuentas de un entreno", () => {
  it("minutos y segundos como se leen", () => {
    expect(minutesLabel(45)).toBe("45 min");
    expect(minutesLabel(87)).toBe("1 h 27");
    expect(elapsed(725)).toBe("12:05");
  });

  it("una noche media de un grupo en una línea", () => {
    expect(groupLine({ nights: 4, asleep: 425, deep: 62, hrv: 38 })).toBe("7 h 05 · profundo 1 h 02 · VFC 38 ms · 4 noches");
    expect(groupLine({ nights: 0, asleep: null, deep: null, hrv: null })).toBe("sin noches");
  });

});

const week = (start: string, load: number, workouts = 1, zones?: number[]) => ({ start, workouts, minutes: workouts * 60, load, zones });

describe("la carga por semana", () => {
  const load: Load = {
    this_week: 240,
    mean_4: 520,
    weeks: [week("2026-09-28", 0, 0), week("2026-10-05", 0, 2), week("2026-10-12", 800), week("2026-10-19", 550), week("2026-10-26", 760), week("2026-11-02", 240)],
  };

  it("empieza en la primera semana con carga", () => {
    expect(fromFirstLoad(load).weeks.map((one) => one.start)).toEqual(["2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02"]);
  });

  it("la media es de las cuatro de antes, y sin cuatro no hay", () => {
    const means = rollingMean(load);
    expect(means.slice(0, 4)).toEqual([null, null, null, null]);
    expect(means[4]).toBe(Math.round((0 + 0 + 800 + 550) / 4));
  });

  it("las zonas de las cuatro últimas, en minutos y en parte del total", () => {
    const zoned: Load = { ...load, weeks: [week("2026-10-26", 1, 1, [30, 10, 0, 0, 0]), week("2026-11-02", 1, 1, [10, 30, 20, 0, 0])] };
    const { minutes, shares } = zoneShares(zoned);
    expect(minutes).toEqual([40, 40, 20, 0, 0]);
    expect(shares[0]).toBeCloseTo(0.4);
  });
});

describe("lo que haces y los entrenos por semana", () => {
  const workout = (name: string, start: string, minutes: number) => ({
    id: `${name}-${start}`,
    kind: "activity" as const,
    name,
    start,
    end: start,
    minutes,
    href: null,
    from_band: true,
    kcal: null,
    heart: { avg: null, max: null, zones: [], load: 0, recovery_2min: null, source: null },
  });
  const now = new Date("2026-11-05T12:00:00");
  const list = [
    workout("Tenis", "2026-11-04T18:00:00", 90),
    workout("Fuerza", "2026-11-03T19:00:00", 60),
    workout("Tenis", "2026-10-28T18:00:00", 80),
    workout("Bici", "2026-09-01T10:00:00", 120),
  ];

  it("por nombre, de los últimos 30 días y de más minutos a menos", () => {
    expect(byName(list, now)).toEqual([
      { name: "Tenis", count: 2, minutes: 170 },
      { name: "Fuerza", count: 1, minutes: 60 },
    ]);
  });

  it("por semana de lunes, esta primero y con su cuenta", () => {
    const weeks = byWeek(list, now);
    expect(weeks[0]?.label).toBe("Esta semana · 2");
    expect(weeks[1]?.items.map((one) => one.name)).toEqual(["Tenis"]);
  });
});
