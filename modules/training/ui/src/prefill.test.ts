import { DIPS, LAST_PRESS, LAST_SMITH, SQUAT } from "./fixtures";
import { describeSets, preferredVariant, prefill, shortDay, unusualLoad } from "./prefill";

describe("the preselected chip", () => {
  it("is the last variant used, not the first of the plan", () => {
    expect(preferredVariant(SQUAT, [LAST_SMITH, LAST_PRESS], [])).toBe("v-press");
  });

  it("without history it is the first of the plan", () => {
    expect(preferredVariant(SQUAT, [], [])).toBe("v-smith");
  });

  it("if today already started with one, it is that one", () => {
    const today = [{ id: "e", plan_slot_id: SQUAT.id, variant_id: "v-smith", variant: "", position: 1, sets: [] }];
    expect(preferredVariant(SQUAT, [LAST_PRESS], today)).toBe("v-smith");
  });
});

describe("the prefilled set", () => {
  const smith = SQUAT.options[0];

  it("is the same set as last time", () => {
    expect(prefill(3, SQUAT, smith, LAST_SMITH, [])).toEqual({ load: 60, reps: 7 });
  });

  it("if today has one set more than last time, it repeats the last one there was", () => {
    expect(prefill(3, SQUAT, SQUAT.options[1], LAST_PRESS, [])).toEqual({ load: 140, reps: 9 });
  });

  it("without history, the previous set of today; and without anything, the bottom of the range", () => {
    const today = [{ number: 1, reps: 9, weight: 50, added_load: null, completed: true, confirmed_at: "x" }];
    expect(prefill(2, SQUAT, smith, undefined, today)).toEqual({ load: 50, reps: 9 });
    expect(prefill(1, SQUAT, smith, undefined, [])).toEqual({ load: null, reps: 6 });
  });

  it("with bodyweight what is prefilled is the added load", () => {
    expect(prefill(1, DIPS, DIPS.options[0], undefined, [])).toEqual({ load: 0, reps: 8 });
  });
});

describe("how sets read", () => {
  it("with the same load they are grouped", () => {
    expect(describeSets(LAST_SMITH.sets, false, "en")).toBe("8, 8, 7 × 60 kg");
  });

  it("if the load changes, each with its own", () => {
    const sets = [
      { ...LAST_SMITH.sets[0]!, weight: 60 },
      { ...LAST_SMITH.sets[1]!, weight: 62.5, reps: 6 },
    ];
    expect(describeSets(sets, false, "en")).toBe("8 × 60 kg · 6 × 62.5 kg");
    expect(describeSets([...LAST_SMITH.sets, { ...LAST_SMITH.sets[2]!, number: 4, weight: 65 }], false, "en")).toBe(
      "8, 8, 7 × 60 kg · 7 × 65 kg",
    );
  });

  it("with added load it adds up, and without it they are only reps", () => {
    const sets = [
      { number: 1, reps: 10, weight: null, added_load: 10, completed: true, confirmed_at: "x" },
      { number: 2, reps: 9, weight: null, added_load: 10, completed: true, confirmed_at: "x" },
    ];
    expect(describeSets(sets, true, "en")).toBe("10, 9 + 10 kg");
    expect(describeSets(sets.map((set) => ({ ...set, added_load: null })), true, "en")).toBe("10, 9");
  });

  it("the day is short, without a dot, in the language of the person", () => {
    expect(shortDay("2026-09-12", "en")).toBe("Sep 12");
    expect(shortDay("2026-09-12", "es")).not.toContain(".");
  });
});

describe("the warning of an odd weight", () => {
  const press = SQUAT.options[1];
  const here = { ...LAST_PRESS, gym_id: "g1" };

  it("fires if it is more than 30 % away from last time on this machine, and says what it was", () => {
    expect(unusualLoad({ load: 200, reps: 8 }, here, press, "g1")).toBe(140);
    expect(unusualLoad({ load: 90, reps: 8 }, here, press, "g1")).toBe(140);
  });

  it("does not fire with the usual nor with a normal jump", () => {
    expect(unusualLoad({ load: 140, reps: 10 }, here, press, "g1")).toBeNull();
    expect(unusualLoad({ load: 150, reps: 8 }, here, press, "g1")).toBeNull();
  });

  it("at another gym it is another machine, and it does not compare", () => {
    expect(unusualLoad({ load: 200, reps: 8 }, here, press, "g2")).toBeNull();
  });

  it("with added load it does not fire: going from 10 to 20 kg is normal", () => {
    const dips = { ...here, sets: here.sets.map((set) => ({ ...set, weight: null, added_load: 10 })) };
    expect(unusualLoad({ load: 20, reps: 8 }, dips, DIPS.options[0], "g1")).toBeNull();
  });
});
