import { describe, expect, it } from "vitest";

import { EMPTY_DRAFT, bodyOf, decimalOf, draftOf, looksLikeIsin, symbolOf } from "./positionsForm";

const TODAY = "2030-06-15";

describe("the position form", () => {
  it("reads an ISIN or a ticker in capitals without spaces", () => {
    expect(symbolOf(" ie00b4l5y983 ")).toBe("IE00B4L5Y983");
    expect(looksLikeIsin("IE00B4L5Y983")).toBe(true);
    expect(looksLikeIsin("SPY")).toBe(false);
  });

  it("reads decimals with the person's mark and a limit of places", () => {
    expect(decimalOf("1.234,5678", 4, ",")).toBe("1234.5678");
    expect(decimalOf("1,234.56", 2, ".")).toBe("1234.56");
    expect(decimalOf("12,345", 4, ",")).toBe("12.345");
    expect(decimalOf("1.234", 2, ",")).toBe("1234");
    expect(decimalOf("1,2345", 2, ",")).toBeNull();
    expect(decimalOf("abc", 2, ",")).toBeNull();
    expect(decimalOf("", 2, ",")).toBeNull();
    expect(decimalOf("-3", 2, ",")).toBeNull();
  });

  it("builds the body with units and cost, and no price unless one is written", () => {
    const draft = { ...EMPTY_DRAFT, symbol: "ie00b4l5y983", name: " World ", units: "10,5", cost: "800" };
    expect(bodyOf(draft, ",", TODAY)).toEqual({ symbol: "IE00B4L5Y983", name: "World", units: "10.5", cost: "800" });
  });

  it("asks for units above zero, a cost and a symbol", () => {
    const ok = { ...EMPTY_DRAFT, symbol: "SPY", units: "1", cost: "10" };
    expect(bodyOf(ok, ".", TODAY)).not.toBeNull();
    expect(bodyOf({ ...ok, symbol: " " }, ".", TODAY)).toBeNull();
    expect(bodyOf({ ...ok, units: "0" }, ".", TODAY)).toBeNull();
    expect(bodyOf({ ...ok, cost: "" }, ".", TODAY)).toBeNull();
  });

  it("takes a price only with a day that is not in the future", () => {
    const ok = { ...EMPTY_DRAFT, symbol: "SPY", units: "1", cost: "10", price: "90.5", priceOn: "2030-06-10" };
    expect(bodyOf(ok, ".", TODAY)).toMatchObject({ price: "90.5", price_on: "2030-06-10" });
    expect(bodyOf({ ...ok, priceOn: "" }, ".", TODAY)).toBeNull();
    expect(bodyOf({ ...ok, priceOn: "2030-07-01" }, ".", TODAY)).toBeNull();
    expect(bodyOf({ ...ok, price: "x" }, ".", TODAY)).toBeNull();
  });

  it("starts the form from a stored position", () => {
    expect(draftOf({ symbol: "SPY", name: "S&P", units: 2.5, cost: 100 })).toEqual({
      ...EMPTY_DRAFT,
      symbol: "SPY",
      name: "S&P",
      units: "2.5",
      cost: "100",
    });
  });
});
