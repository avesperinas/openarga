import type { DayInput } from "./api";
import {
  addDay,
  addOption,
  addSlot,
  moveDay,
  moveSlot,
  publishProblems,
  removeDay,
  removeOption,
  toInput,
  updateSlot,
} from "./draft";
import { DIPS, SQUAT } from "./fixtures";
import { english } from "./i18n/testing";

const empty: DayInput[] = [];

describe("editing the draft", () => {
  it("from nothing: one day, one exercise and it can be published", () => {
    let days = addDay(empty, "  Legs ", "leg");
    expect(publishProblems(days, english)).toEqual(["“Legs” has no exercises."]);

    days = addSlot(days, 0, "v-smith");
    expect(days[0]).toEqual({
      name: "Legs",
      kind: "leg",
      slots: [{ target_sets: 3, rep_min: 8, rep_max: 12, allow_both: false, variant_ids: ["v-smith"] }],
    });
    expect(publishProblems(days, english)).toEqual([]);
  });

  it("without days it is not published", () => {
    expect(publishProblems(empty, english)).toEqual(["Add at least one day."]);
  });

  it("the rep range is never backwards", () => {
    const days = addSlot(addDay(empty, "A", "push"), 0, "v");
    expect(updateSlot(days, 0, 0, { rep_min: 15 })[0]?.slots[0]).toMatchObject({ rep_min: 15, rep_max: 15 });
    expect(updateSlot(days, 0, 0, { rep_max: 5 })[0]?.slots[0]).toMatchObject({ rep_min: 5, rep_max: 5 });
  });

  it("the alternatives: no repeats, never down to zero, and 'both' only with two", () => {
    let days = addSlot(addDay(empty, "A", "leg"), 0, "v-smith");
    days = addOption(days, 0, 0, "v-press");
    days = addOption(days, 0, 0, "v-press");
    days = updateSlot(days, 0, 0, { allow_both: true });
    expect(days[0]?.slots[0]).toMatchObject({ variant_ids: ["v-smith", "v-press"], allow_both: true });

    days = removeOption(days, 0, 0, "v-smith");
    days = removeOption(days, 0, 0, "v-press");
    expect(days[0]?.slots[0]).toMatchObject({ variant_ids: ["v-press"], allow_both: false });
  });

  it("moving days and exercises, without leaving the list", () => {
    let days = addDay(addDay(empty, "A", "push"), "B", "pull");
    days = moveDay(days, 1, -1);
    expect(days.map((day) => day.name)).toEqual(["B", "A"]);
    expect(moveDay(days, 0, -1)).toBe(days);
    expect(removeDay(days, 0).map((day) => day.name)).toEqual(["A"]);

    days = addSlot(addSlot(days, 0, "x"), 0, "y");
    expect(moveSlot(days, 0, 1, -1)[0]?.slots.map((slot) => slot.variant_ids[0])).toEqual(["y", "x"]);
  });

  it("the published plan is copied with its variants in order", () => {
    const input = toInput([
      { id: "d", name: "Legs", kind: "leg", position: 1, slots: [{ ...SQUAT, options: [...SQUAT.options].reverse() }, DIPS] },
    ]);
    expect(input[0]?.slots.map((slot) => slot.variant_ids)).toEqual([["v-smith", "v-press"], ["v-dips"]]);
  });
});
