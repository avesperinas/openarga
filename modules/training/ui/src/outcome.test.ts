import type { LastTime, LoggedSet } from "./api";
import { english, spanish } from "./i18n/testing";
import { bestSet, compare } from "./outcome";

const set = (number: number, reps: number, weight: number | null, added_load: number | null = null): LoggedSet => ({
  number,
  reps,
  weight,
  added_load,
  completed: true,
  confirmed_at: "2026-09-14T17:00:00Z",
});

const last = (day: string, ...sets: LoggedSet[]): LastTime => ({ variant_id: "v", day, sets });
const DAY = "2026-09-14";
const BEFORE = "2026-09-07";

describe("the best set", () => {
  it("is the one with most estimated strength, not most kilos", () => {
    expect(bestSet([set(1, 10, 60), set(2, 3, 65)], false)?.number).toBe(1);
  });

  it("does not count those not done", () => {
    expect(bestSet([{ ...set(1, 8, 100), completed: false }, set(2, 8, 60)], false)?.number).toBe(2);
  });

  it("without load, with bodyweight, is the one with most reps", () => {
    expect(bestSet([set(1, 8, null), set(2, 10, null)], true)?.number).toBe(2);
  });
});

describe("against the previous time", () => {
  it("with the same load it tells the reps", () => {
    expect(compare([set(1, 9, 60)], last(BEFORE, set(1, 8, 60)), false, DAY, english, "en")).toEqual({ text: "+1 rep", direction: "up" });
  });

  it("with another load it tells the kilos", () => {
    expect(compare([set(1, 8, 62.5)], last(BEFORE, set(1, 8, 60)), false, DAY, english, "en")).toEqual({ text: "+2.5 kg", direction: "up" });
  });

  it("if adding kilos cost too many reps, it goes down even though the kilos go up", () => {
    expect(compare([set(1, 4, 62.5)], last(BEFORE, set(1, 10, 60)), false, DAY, english, "en")).toEqual({
      text: "+2.5 kg",
      direction: "down",
    });
  });

  it("the same is flat", () => {
    expect(compare([set(1, 8, 60)], last(BEFORE, set(1, 8, 60)), false, DAY, english, "en")?.direction).toBe("flat");
  });

  it("with added load it compares the added load", () => {
    expect(compare([set(1, 6, null, 15)], last(BEFORE, set(1, 6, null, 10)), true, DAY, english, "en")?.text).toBe("+5 kg");
  });

  it("without a previous time, or with a later one, it is the first time", () => {
    expect(compare([set(1, 8, 60)], undefined, false, DAY, english, "en")?.direction).toBe("first");
    expect(compare([set(1, 8, 60)], last("2026-09-21", set(1, 8, 50)), false, DAY, english, "en")?.direction).toBe("first");
  });

  it("without sets done there is nothing to compare", () => {
    expect(compare([], last(BEFORE, set(1, 8, 60)), false, DAY, english, "en")).toBeNull();
  });
});

describe("in Spanish", () => {
  it("writes the decimal and the first time in the language of the person", () => {
    expect(compare([set(1, 8, 62.5)], last(BEFORE, set(1, 8, 60)), false, DAY, spanish, "es")?.text).toBe("+2,5 kg");
    expect(compare([set(1, 8, 60)], undefined, false, DAY, spanish, "es")?.text).toBe(spanish("compare.first"));
  });
});
