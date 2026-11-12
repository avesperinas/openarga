import { describe, expect, it } from "vitest";

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
    account_name: "Principal",
    institution: "Banco",
    merchant: "Supermercado Inventado",
    text: "PAGO CON TARJETA",
    counterparty: null,
    counterparty_iban: null,
    bank_category: null,
    source: "api",
    status: "auto",
    kind: "expense",
    parts: [
      { amount: -20, category: "c1", category_name: "Supermercado", nature: "expense", ownership: "shared", payer: "account", basis: "rule", equity_in: null },
    ],
    transfer: null,
    labelled: false,
    before_cutoff: false,
    entry: null,
    ...overrides,
  };
}

describe("el periodo", () => {
  it("va de un mes a otro y cruza el año", () => {
    expect(step({ kind: "month", year: 2026, month: 1 }, -1)).toEqual({ kind: "month", year: 2025, month: 12 });
    expect(bounds({ kind: "month", year: 2026, month: 2 })).toEqual({ from: "2026-02-01", to: "2026-02-28" });
    expect(periodTitle({ kind: "month", year: 2026, month: 9 })).toBe("Septiembre 2026");
  });
});

describe("los filtros", () => {
  it("buscan en el comercio y la categoría sin tildes ni mayúsculas", () => {
    expect(matches(mv({}), { ...NO_FILTERS, text: "supermercado inventado" })).toBe(true);
    expect(matches(mv({ merchant: "Cafetería" }), { ...NO_FILTERS, text: "cafeteria" })).toBe(true);
    expect(matches(mv({}), { ...NO_FILTERS, text: "farmacia" })).toBe(false);
  });

  it("separan gasto, ingreso y traspaso", () => {
    const transfer = mv({ kind: "transfer", status: "transfer", parts: [] });
    expect(matches(transfer, { ...NO_FILTERS, what: ["transfer"] })).toBe(true);
    expect(matches(mv({}), { ...NO_FILTERS, what: ["transfer"] })).toBe(false);
    expect(activeCount({ ...NO_FILTERS, what: ["transfer"], min: 10 })).toBe(2);
  });

  it("filtran por importe en valor absoluto", () => {
    expect(matches(mv({ amount: -20 }), { ...NO_FILTERS, min: 10, max: 30 })).toBe(true);
    expect(matches(mv({ amount: -50 }), { ...NO_FILTERS, max: 30 })).toBe(false);
  });
});

describe("lo que suma", () => {
  it("no cuenta traspasos y una devolución resta del gasto", () => {
    const rows = [
      mv({}),
      mv({ id: "a:2", amount: 5, parts: [{ ...(mv({}).parts[0] as Movement["parts"][number]), amount: 5 }] }),
      mv({ id: "a:3", kind: "transfer", status: "transfer", amount: -300, parts: [] }),
    ];
    expect(totals(rows)).toEqual({ income: 0, expense: 15, count: 3 });
  });

  it("agrupa por día con el neto sin traspasos", () => {
    const days = byDay([mv({}), mv({ id: "a:2", kind: "transfer", amount: -300, parts: [] }), mv({ id: "a:3", on: "2026-09-04" })]);
    expect(days.map((d) => [d.on, d.net])).toEqual([
      ["2026-09-05", -20],
      ["2026-09-04", -20],
    ]);
  });
});

describe("cómo se escribe", () => {
  it("el signo siempre delante", () => {
    expect(money(-12.5)).toMatch(/^−12,50\s€$/);
    expect(money(3)).toMatch(/^\+3,00\s€$/);
  });

  it("los importes tecleados", () => {
    expect(parseAmount("12,50")).toBe(12.5);
    expect(parseAmount("1.234,5")).toBe(1234.5);
    expect(parseAmount("12,505")).toBe(null);
  });

  it("el día y lo que es cada fila", () => {
    expect(dayTitle("2026-09-29", new Date(2026, 9, 1))).toBe("Martes, 29 de septiembre");
    expect(subtitle(mv({}))).toBe("Supermercado · compartido");
    const transfer = mv({ kind: "transfer", status: "transfer", parts: [], transfer: { account: "j", name: "Común", basis: "match" } });
    expect(title(transfer)).toBe("A Común");
    expect(subtitle(transfer)).toBe("Traspaso");
    expect(money(-3022.17)).toMatch(/^−3\.022,17\s€$/);
  });
});
