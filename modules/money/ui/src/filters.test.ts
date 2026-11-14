import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { configureRegional } from "@openarga/ui";

import type { Movement } from "./api";
import { NO_FILTERS, activeCount, bounds, byDay, matches, periodTitle, step, totals } from "./filters";
import { dayTitle, money, parseAmount, subtitle, title } from "./format";

function mv(overrides: Partial<Movement>): Movement {
  return {
    id: "a:1",
    on: "2026-09-05",
    value_on: null,
    amount: -20,
    account: "main",
    account_name: "Main",
    institution: "Bank",
    merchant: "Invented Grocer",
    text: "PAGO CON TARJETA",
    counterparty: null,
    counterparty_iban: null,
    bank_category: null,
    source: "api",
    status: "auto",
    kind: "expense",
    parts: [
      { amount: -20, category: "c1", category_name: "Groceries", nature: "expense", ownership: "shared", payer: "account", basis: "rule", equity_in: null },
    ],
    transfer: null,
    labelled: false,
    before_cutoff: false,
    entry: null,
    ...overrides,
  };
}

const ENGLISH = { locale: "en-GB", timeZone: "Europe/Madrid", currency: "EUR" };
const SPANISH = { locale: "es-ES", timeZone: "Europe/Madrid", currency: "EUR" };

beforeAll(() => configureRegional(ENGLISH));
afterAll(() => configureRegional(SPANISH));

describe("the period", () => {
  it("goes from one month to another and crosses the year", () => {
    expect(step({ kind: "month", year: 2026, month: 1 }, -1)).toEqual({ kind: "month", year: 2025, month: 12 });
    expect(bounds({ kind: "month", year: 2026, month: 2 })).toEqual({ from: "2026-02-01", to: "2026-02-28" });
    expect(periodTitle({ kind: "month", year: 2026, month: 9 })).toBe("September 2026");
  });
});

describe("the filters", () => {
  it("search the merchant and the category without accents or case", () => {
    expect(matches(mv({}), { ...NO_FILTERS, text: "invented grocer" })).toBe(true);
    expect(matches(mv({ merchant: "Caf\u00e9 Central" }), { ...NO_FILTERS, text: "cafe" })).toBe(true);
    expect(matches(mv({}), { ...NO_FILTERS, text: "pharmacy" })).toBe(false);
  });

  it("separate expense, income and transfer", () => {
    const transfer = mv({ kind: "transfer", status: "transfer", parts: [] });
    expect(matches(transfer, { ...NO_FILTERS, what: ["transfer"] })).toBe(true);
    expect(matches(mv({}), { ...NO_FILTERS, what: ["transfer"] })).toBe(false);
    expect(activeCount({ ...NO_FILTERS, what: ["transfer"], min: 10 })).toBe(2);
  });

  it("filter by absolute amount", () => {
    expect(matches(mv({ amount: -20 }), { ...NO_FILTERS, min: 10, max: 30 })).toBe(true);
    expect(matches(mv({ amount: -50 }), { ...NO_FILTERS, max: 30 })).toBe(false);
  });
});

describe("what it adds up to", () => {
  it("does not count transfers, and a refund subtracts from spending", () => {
    const rows = [
      mv({}),
      mv({ id: "a:2", amount: 5, parts: [{ ...(mv({}).parts[0] as Movement["parts"][number]), amount: 5 }] }),
      mv({ id: "a:3", kind: "transfer", status: "transfer", amount: -300, parts: [] }),
    ];
    expect(totals(rows)).toEqual({ income: 0, expense: 15, count: 3 });
  });

  it("groups by day with the net without transfers", () => {
    const days = byDay([mv({}), mv({ id: "a:2", kind: "transfer", amount: -300, parts: [] }), mv({ id: "a:3", on: "2026-09-04" })]);
    expect(days.map((d) => [d.on, d.net])).toEqual([
      ["2026-09-05", -20],
      ["2026-09-04", -20],
    ]);
  });
});

describe("how it is written", () => {
  it("the sign always first, in the person's currency", () => {
    expect(money(-12.5)).toBe("−€12.50");
    expect(money(3)).toBe("+€3.00");
    configureRegional({ currency: "USD" });
    try {
      expect(money(-3022.17)).toBe("−US$3,022.17");
    } finally {
      configureRegional(ENGLISH);
    }
  });

  it("typed amounts", () => {
    expect(parseAmount("12.50")).toBe(12.5);
    expect(parseAmount("1,234.5")).toBe(1234.5);
    expect(parseAmount("€7")).toBe(7);
    expect(parseAmount("12.505")).toBe(null);
  });

  it("the day and what each row is", () => {
    expect(dayTitle("2026-09-29", new Date(2026, 9, 1))).toBe("Tuesday 29 September");
    expect(subtitle(mv({}))).toBe("Groceries · shared");
    const transfer = mv({ kind: "transfer", status: "transfer", parts: [], transfer: { account: "j", name: "Joint", basis: "match" } });
    expect(title(transfer)).toBe("To Joint");
    expect(subtitle(transfer)).toBe("Transfer");
  });

  it("in Spanish, amounts and days the Spanish way", () => {
    configureRegional(SPANISH);
    try {
      expect(money(-3022.17)).toMatch(/^−3\.022,17\s€$/);
      expect(parseAmount("1.234,5")).toBe(1234.5);
      expect(parseAmount("12,505")).toBe(null);
      expect(dayTitle("2026-09-29", new Date(2026, 9, 1))).toBe("Martes, 29 de septiembre");
    } finally {
      configureRegional(ENGLISH);
    }
  });
});
