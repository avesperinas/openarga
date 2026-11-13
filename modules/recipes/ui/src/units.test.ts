import { configureRegional } from "@openarga/ui";

import { english as t, spanish } from "./i18n/testing";
import { UNITS, quantityLabel } from "./units";

afterEach(() => configureRegional({ locale: "es-ES" }));

test("the six units each have their short form", () => {
  expect(UNITS).toEqual(["g", "ml", "unit", "tbsp", "tsp", "pinch"]);
});

test("a quantity reads short, in the person's language", () => {
  configureRegional({ locale: "en-US" });
  expect(quantityLabel(400, "g", t)).toBe("400 g");
  expect(quantityLabel(1.5, "unit", t)).toBe("1.5 u");
  expect(quantityLabel(2, "tbsp", t)).toBe("2 tbsp");
  configureRegional({ locale: "es-ES" });
  expect(quantityLabel(1.5, "unit", spanish)).toBe(`1,5 ${spanish("unit_short.unit")}`);
});
