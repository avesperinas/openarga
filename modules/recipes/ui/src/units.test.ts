import { UNITS, quantityLabel } from "./units";

test("las seis unidades tienen su forma corta", () => {
  expect(UNITS.map((one) => one.value)).toEqual(["g", "ml", "unit", "tbsp", "tsp", "pinch"]);
});

test("una cantidad se lee corta y en español", () => {
  expect(quantityLabel(400, "g")).toBe("400 g");
  expect(quantityLabel(1.5, "unit")).toBe("1,5 ud");
  expect(quantityLabel(2, "tbsp")).toBe("2 cda");
});
