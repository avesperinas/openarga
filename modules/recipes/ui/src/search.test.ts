import { describe, expect, it } from "vitest";

import { closeness, fold, ranked } from "./search";

const BANANA = "Pl\u00e1tano";

describe("searching without accents (T-V26)", () => {
  it("drops capitals, accents, diaereses and tildes", () => {
    expect(fold("\u00d1oquis of PUMPKIN, sm\u00e0ll, ping\u00fcino")).toBe("noquis of pumpkin, small, pinguino");
  });

  it("the same scale as the API", () => {
    expect(closeness("platano", BANANA)).toBe(0);
    expect(closeness("plat", BANANA)).toBe(1);
    expect(closeness("plat", `Shake with ${BANANA}`)).toBe(2);
    expect(closeness("tano", `Shake with ${BANANA}`)).toBe(3);
    expect(closeness("kiwi", BANANA)).toBeNull();
  });

  it("what starts the same goes first; by alias or by the source's name", () => {
    const foods = [
      { alias: null, name: `${BANANA} shake` },
      { alias: BANANA, name: "Bananas, raw" },
      { alias: null, name: `Chocolate with ${BANANA}` },
      { alias: null, name: "Kiwi" },
    ];
    const label = (one: (typeof foods)[number]) => one.alias ?? one.name;
    expect(ranked(foods, "platano", (one) => [one.alias, one.name], label).map(label)).toEqual([
      BANANA,
      `${BANANA} shake`,
      `Chocolate with ${BANANA}`,
    ]);
    expect(ranked(foods, "banana", (one) => [one.alias, one.name], label).map(label)).toEqual([BANANA]);
  });
});
