import { statementLine } from "./Statements";

test("de cada página se dice qué entendió y cuánto era nuevo", () => {
  expect(
    statementLine({
      file: "renault.html",
      entity: "Renault Bank",
      accounts: ["Cuenta Contigo"],
      movements: 3,
      balances: 1,
      new: 2,
    }),
  ).toBe("Renault Bank · Cuenta Contigo · 3 movimientos y 1 saldo, 2 nuevos");
  expect(statementLine({ file: "otra.html", problem: "no es una página que se sepa leer" })).toBe(
    "no es una página que se sepa leer",
  );
  expect(statementLine({ file: "igual.html", entity: "Finizens", accounts: [], balances: 3, new: 0 })).toBe(
    "Finizens · 3 saldos, nada nuevo",
  );
});
