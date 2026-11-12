import { amount, grams, kcal, macroLine, pantryLine, sourceLabel } from "./macros";

test("un número se lee como se escribe en español y sin decimales de relleno", () => {
  expect(amount(61)).toBe("61");
  expect(amount(1.5)).toBe("1,5");
  expect(amount(14.153)).toBe("14,2");
});

test("lo que no se sabe es un hueco, nunca un cero", () => {
  expect(amount(null)).toBe("—");
  expect(amount(undefined)).toBe("—");
});

test("la línea de macros lleva las cuatro, por 100 g", () => {
  const line = macroLine({ kcal: 61, protein: 1.5, fat: 0.3, carbs: 14.15, fiber: 1.8, salt: 0.05 });

  expect(line).toBe("61 kcal · 1,5 P · 0,3 G · 14,2 H");
});

test("de dónde salió el dato se dice, y si lo tocaste tú también", () => {
  expect(sourceLabel("usda", false)).toBe("USDA");
  expect(sourceLabel("off", false)).toBe("OpenFoodFacts");
  expect(sourceLabel("usda", true)).toBe("USDA, corregido");
  expect(sourceLabel("manual", false)).toBe("tuyo");
});

describe("las cifras del móvil", () => {
  it("kcal sin decimales y con punto de miles, gramos con un decimal solo por debajo de 10", () => {
    expect(kcal(1560.4)).toBe("1.560");
    expect(grams(4.66)).toBe("4,7");
    expect(grams(32.5)).toBe("33");
    expect(grams(0)).toBe("0");
  });

  it("la fila de la despensa lleva las macros sin las kcal", () => {
    expect(pantryLine({ kcal: 86, protein: 1.6, fat: 0.1, carbs: 20.1, fiber: 0, salt: 0 })).toBe("P 1,6 · G 0,1 · H 20 · por 100 g");
  });
});
