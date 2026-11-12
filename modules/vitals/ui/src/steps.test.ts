import { describe, expect, it } from "vitest";

import { bucketLabel, perBucket, startOf, stepsTone, yearEnd, yearsOf } from "./steps";

describe("los pasos por semana y por mes", () => {
  it("la semana empieza en lunes y el mes en su día 1", () => {
    expect(startOf("2026-09-27", "week")).toBe("2026-09-21");
    expect(startOf("2026-09-21", "week")).toBe("2026-09-21");
    expect(startOf("2026-09-27", "month")).toBe("2026-09-01");
  });

  it("la media es de los días con dato, no de los siete", () => {
    const buckets = perBucket(
      [
        { day: "2026-09-21", steps: 6000 },
        { day: "2026-09-23", steps: 10000 },
        { day: "2026-09-28", steps: 4000 },
      ],
      "week",
    );

    expect(buckets).toEqual([
      { start: "2026-09-21", mean: 8000, days: 2 },
      { start: "2026-09-28", mean: 4000, days: 1 },
    ]);
  });

  it("colorea contra el objetivo, y sin objetivo no juzga", () => {
    expect(stepsTone(9000, 8000)).toBe("positive");
    expect(stepsTone(5000, 8000)).toBe("warning");
    expect(stepsTone(2000, 8000)).toBe("negative");
    expect(stepsTone(2000, null)).toBe("neutral");
  });

  it("los meses y los años se ven todos, desde el primero", () => {
    const days = Array.from({ length: 30 }, (_, index) => ({
      day: `${2017 + Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}-15`,
      steps: 1000 * (index + 1),
    }));

    expect(perBucket(days, "month")).toHaveLength(30);
    expect(perBucket(days, "year").map((one) => one.start)).toEqual(["2017-01-01", "2018-01-01", "2019-01-01"]);
    expect(bucketLabel("2019-01-01", "year")).toBe("2019");
    expect(yearsOf(days)).toEqual(["2019", "2018", "2017"]);
  });

  it("el calendario de un año acaba hoy si es el de ahora, y el 31 de diciembre si no", () => {
    expect(yearEnd("2026", "2026-09-26")).toBe("2026-09-26");
    expect(yearEnd("2024", "2026-09-26")).toBe("2024-12-31");
  });
});
