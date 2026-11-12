import { initiallyChosen, summary } from "./Shopping";
import type { Ingredient } from "./api";

const ingredient = (position: number, optional = false): Ingredient => ({
  position,
  name: `Ingrediente ${position}`,
  food_id: null,
  category_id: "other",
  quantity: 100,
  unit: "g",
  note: null,
  optional,
  grams: 100,
});

test("al abrir se marca todo menos lo opcional", () => {
  expect(initiallyChosen([ingredient(1), ingredient(2, true), ingredient(3)])).toEqual([1, 3]);
});

test("el resumen dice lo apuntado y lo que ya estaba", () => {
  const answer = {
    added: [
      { name: "Puerro", already_on_list: false },
      { name: "Patata", already_on_list: false },
      { name: "Aceite", already_on_list: true },
    ],
    pending: 5,
  };

  expect(summary(answer)).toBe("2 apuntados · 1 ya estaba");
});

test("si todo estaba ya, lo dice sin contar nada apuntado", () => {
  expect(summary({ added: [{ name: "Leche", already_on_list: true }], pending: 1 })).toBe("1 ya estaba");
});
