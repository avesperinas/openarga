import type { Machine, VariantPoint } from "./api";
import { advice, normalRange, recordIds, recordStreak } from "./exercise";
import { english } from "./i18n/testing";

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
  gym: "Gym",
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

describe("the records of the line", () => {
  it("are the days that beat everything before, not counting the first", () => {
    expect([...recordIds([point("1", 100), point("2", 98), point("3", 101), point("4", 101)])]).toEqual(["3"]);
  });

  it("a day set aside is no record and does not raise the bar", () => {
    expect([...recordIds([point("1", 100), point("2", 140, 5, 100, "high"), point("3", 102)])]).toEqual(["3"]);
  });

  it("the streak counts the latest in a row", () => {
    expect(recordStreak([point("1", 100), point("2", 99), point("3", 101), point("4", 103)])).toBe(2);
    expect(recordStreak([point("1", 100), point("2", 101), point("3", 99)])).toBe(0);
  });
});

describe("the normal range", () => {
  it("is the quartiles of the latest sessions", () => {
    expect(normalRange([100, 102, 104, 106, 108].map((value, index) => point(String(index + 1), value)))).toEqual({
      low: 102,
      high: 106,
    });
  });

  it("with fewer than four there is no range", () => {
    expect(normalRange([point("1", 100), point("2", 101), point("3", 102)])).toBeNull();
  });
});

describe("what it says", () => {
  it("with a streak, it says so; and the weight for a record, at the step of the machine", () => {
    const said = advice(machine([point("1", 100), point("2", 105, 5, 90), point("3", 108, 5, 92.5)]), 2.5, true, english, "en");

    expect(said[0]).toBe("2 sessions in a row with a record.");
    expect(said[1]).toBe("For a record next time: 5 × 95 kg.");
  });

  it("without a record in three sessions, it says so and proposes ways out", () => {
    const said = advice(machine([point("1", 110), point("2", 100), point("3", 101), point("4", 100)], 3), 2.5, true, english, "en");

    expect(said[0]).toContain("3 sessions without a record here");
  });

  it("with bodyweight, the reps with the same added load", () => {
    const said = advice(machine([point("1", 100, 8, 82), point("2", 96, 8, 80)]), 2.5, false, english, "en");

    expect(said).toEqual(["For a record next time: 8 reps with the same added load."]);
  });

  it("without sessions that count it says nothing", () => {
    expect(advice(machine([]), 2.5, true, english, "en")).toEqual([]);
  });
});
