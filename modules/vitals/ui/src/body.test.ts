import { describe, expect, it } from "vitest";

import { figureFoot, figureValue, profileRows, rolling } from "./body";
import type { Figure } from "./api";

const resting: Figure = {
  id: "resting_heart_rate",
  group: "heart",
  name: "FC en reposo",
  unit: "lpm",
  digits: 0,
  kind: "mean",
  about: "",
  latest: { day: "2026-09-24", value: 58 },
  mean_30: 57.6,
  mean_365: 59.1,
  days: 300,
};

describe("figureValue", () => {
  it("rounds to the figure's digits and adds its unit", () => {
    expect(figureValue(resting, 57.6)).toBe("58 lpm");
    expect(figureValue({ unit: "km", digits: 1 }, 5.26)).toBe("5,3 km");
    expect(figureValue({ unit: "", digits: 0 }, 3)).toBe("3");
  });

  it("says long minutes in hours", () => {
    expect(figureValue({ unit: "min", digits: 0 }, 452)).toBe("7 h 32 min");
    expect(figureValue({ unit: "min", digits: 0 }, 480)).toBe("8 h");
    expect(figureValue({ unit: "min", digits: 0 }, 45)).toBe("45 min");
  });
});

describe("figureFoot", () => {
  it("prefers the 30-day mean and falls back to the year", () => {
    expect(figureFoot(resting)).toBe("media 30 días: 58 lpm");
    expect(figureFoot({ ...resting, mean_30: null })).toBe("media del año: 59 lpm");
  });
});

describe("rolling", () => {
  it("averages up to seven points back", () => {
    const points = [1, 2, 3, 4, 5, 6, 7, 8].map((value, index) => ({ day: `2026-09-0${index + 1}`, value }));
    const smooth = rolling(points);
    expect(smooth[0]!.average).toBe(1);
    expect(smooth[7]!.average).toBe(5);
  });
});

describe("profileRows", () => {
  it("leaves out what is not known", () => {
    const rows = profileRows({
      blood_type: "0-",
      sex: "female",
      birth_date: "1990-01-01",
      age: 36,
      height_cm: 170,
      cardio_medications: null,
    });
    expect(rows).toEqual([
      { label: "Grupo sanguíneo", value: "0-" },
      { label: "Edad", value: "36 años" },
      { label: "Sexo", value: "Mujer" },
      { label: "Altura", value: "1,70 m" },
    ]);
  });
});

describe("la media que no cruza el cambio de aparato", () => {
  it("cada lado del día del cambio tiene la suya", () => {
    const points = [
      { day: "2026-10-18", value: 80 },
      { day: "2026-10-19", value: 80 },
      { day: "2026-10-20", value: 40 },
      { day: "2026-10-21", value: 42 },
    ];
    expect(rolling(points, 7, "2026-10-20").map((one) => one.average)).toEqual([80, 80, 40, 41]);
    expect(rolling(points, 7).map((one) => one.average)).toEqual([80, 80, 200 / 3, 60.5]);
  });
});
