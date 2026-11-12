import { describe, expect, it } from "vitest";

import { parseAmount } from "./ExpenseForm";
import { paidLine } from "./words";

describe("apuntar un gasto", () => {
  it("el importe se lee a la española y a la inglesa", () => {
    expect(parseAmount("1.200,50")).toBe(1200.5);
    expect(parseAmount("1200.5")).toBe(1200.5);
    expect(parseAmount("12000")).toBe(12000);
    expect(parseAmount("12.000")).toBe(12000);
    expect(parseAmount("1.234.567")).toBe(1234567);
    expect(parseAmount("12.5")).toBe(12.5);
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("-3")).toBeNull();
  });

  it("lo pagado en su moneda se dice; uno de la hoja en euros, no", () => {
    expect(paidLine({ amount: 12000, currency: "JPY", fx_rate: 0.00565 })).toBe("12.000 JPY");
    expect(paidLine({ amount: 200, currency: "EUR", fx_rate: null })).toBeNull();
  });
});
