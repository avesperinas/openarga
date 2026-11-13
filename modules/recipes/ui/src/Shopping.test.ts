import { english as t } from "./i18n/testing";
import { initiallyChosen, summary } from "./Shopping";
import type { Ingredient } from "./api";

const ingredient = (position: number, optional = false): Ingredient => ({
  position,
  name: `Ingredient ${position}`,
  food_id: null,
  category_id: "other",
  quantity: 100,
  unit: "g",
  note: null,
  optional,
  grams: 100,
});

test("on opening everything is ticked except what is optional", () => {
  expect(initiallyChosen([ingredient(1), ingredient(2, true), ingredient(3)])).toEqual([1, 3]);
});

test("the summary says what was added and what was already there", () => {
  const answer = {
    added: [
      { name: "Leek", already_on_list: false },
      { name: "Potato", already_on_list: false },
      { name: "Oil", already_on_list: true },
    ],
    pending: 5,
  };

  expect(summary(answer, t)).toBe("2 added · 1 was already there");
});

test("if everything was already there, it says so without counting anything added", () => {
  expect(summary({ added: [{ name: "Milk", already_on_list: true }], pending: 1 }, t)).toBe("1 was already there");
});
