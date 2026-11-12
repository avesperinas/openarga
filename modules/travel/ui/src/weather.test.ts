import { describe, expect, it } from "vitest";

import { dayLine, goodMonths, sky } from "./weather";

const month = (month: number, max_c: number, rain_days: number) => ({ month, max_c, min_c: max_c - 8, rain_mm: rain_days * 5, rain_days });

describe("el tiempo", () => {
  it("los meses buenos: ni frío ni calor, y que no llueva mucho", () => {
    expect(goodMonths([month(1, 8, 7), month(6, 27, 14), month(8, 32, 13), month(11, 16, 7)])).toEqual([11]);
  });

  it("el día en una línea, con la lluvia solo si es probable", () => {
    expect(dayLine({ day: "2027-11-01", code: 0, sky: "despejado", max_c: 17.2, min_c: 8, rain_chance: 5 })).toBe("☀️ 17° / 8°");
    expect(dayLine({ day: "2027-11-02", code: 63, sky: "lluvia", max_c: 15, min_c: 9, rain_chance: 80 })).toBe(
      "🌧️ 15° / 9° · 80 % lluvia",
    );
    expect(sky(null)).toBe("");
  });
});
