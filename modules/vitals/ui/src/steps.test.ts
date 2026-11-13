import { describe, expect, it } from "vitest";

import { bucketLabel, perBucket, startOf, stepsTone, yearEnd, yearsOf } from "./steps";

describe("steps per week and per month", () => {
  it("the week starts on Monday and the month on its first day", () => {
    expect(startOf("2026-09-27", "week")).toBe("2026-09-21");
    expect(startOf("2026-09-21", "week")).toBe("2026-09-21");
    expect(startOf("2026-09-27", "month")).toBe("2026-09-01");
  });

  it("the average is of the days with data, not of the seven", () => {
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

  it("colours against the goal, and without a goal it does not judge", () => {
    expect(stepsTone(9000, 8000)).toBe("positive");
    expect(stepsTone(5000, 8000)).toBe("warning");
    expect(stepsTone(2000, 8000)).toBe("negative");
    expect(stepsTone(2000, null)).toBe("neutral");
  });

  it("every month and year shows, from the first", () => {
    const days = Array.from({ length: 30 }, (_, index) => ({
      day: `${2017 + Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}-15`,
      steps: 1000 * (index + 1),
    }));

    expect(perBucket(days, "month")).toHaveLength(30);
    expect(perBucket(days, "year").map((one) => one.start)).toEqual(["2017-01-01", "2018-01-01", "2019-01-01"]);
    expect(bucketLabel("2019-01-01", "year", "en")).toBe("2019");
    expect(yearsOf(days)).toEqual(["2019", "2018", "2017"]);
  });

  it("a year calendar ends today if it is the current one, and on 31 December otherwise", () => {
    expect(yearEnd("2026", "2026-09-26")).toBe("2026-09-26");
    expect(yearEnd("2024", "2026-09-26")).toBe("2024-12-31");
  });
});
