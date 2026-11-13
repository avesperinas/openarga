import { configureRegional } from "@openarga/ui";

import { english as t } from "./i18n/testing";
import { amount, grams, kcal, macroLine, pantryLine, sourceLabel } from "./macros";

beforeEach(() => configureRegional({ locale: "en-US" }));
afterEach(() => configureRegional({ locale: "es-ES" }));

test("a number reads as it is written, without filler decimals", () => {
  expect(amount(61)).toBe("61");
  expect(amount(1.5)).toBe("1.5");
  expect(amount(14.153)).toBe("14.2");
});

test("what is not known is a gap, never a zero", () => {
  expect(amount(null)).toBe("—");
  expect(amount(undefined)).toBe("—");
});

test("the macro line has all four, per 100 g", () => {
  const line = macroLine({ kcal: 61, protein: 1.5, fat: 0.3, carbs: 14.15, fiber: 1.8, salt: 0.05 }, t);

  expect(line).toBe("61 kcal · 1.5 P · 0.3 F · 14.2 C");
});

test("where the figure came from is said, and whether you touched it", () => {
  expect(sourceLabel("usda", false, t)).toBe("USDA");
  expect(sourceLabel("off", false, t)).toBe("Open Food Facts");
  expect(sourceLabel("usda", true, t)).toBe("USDA, corrected");
  expect(sourceLabel("manual", false, t)).toBe("yours");
});

describe("the phone's figures", () => {
  it("kcal without decimals and with thousands, grams with one decimal only below 10", () => {
    expect(kcal(1560.4)).toBe("1,560");
    expect(grams(4.66)).toBe("4.7");
    expect(grams(32.5)).toBe("33");
    expect(grams(0)).toBe("0");
  });

  it("the pantry row has the macros without the kcal", () => {
    expect(pantryLine({ kcal: 86, protein: 1.6, fat: 0.1, carbs: 20.1, fiber: 0, salt: 0 }, t)).toBe(
      "P 1.6 · F 0.1 · C 20 · per 100 g",
    );
  });

  it("and in Spanish, with Spanish numbers", () => {
    configureRegional({ locale: "es-ES" });
    expect(kcal(1560.4)).toBe("1.560");
    expect(grams(4.66)).toBe("4,7");
  });
});
