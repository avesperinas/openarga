import { expect, test } from "vitest";

import { ruleLine, ruleProblem, trialLine } from "./Rules";

const RULE = {
  entity: "Gestora Inventada",
  product: "Cartera",
  sender: "@ejemplo.com",
  subject: "",
  anchor: "Valor de tu cartera",
  fact: "balance" as const,
};

test("una regla dice qué lee y dónde", () => {
  expect(ruleLine(RULE)).toBe("Lo que vale, tras «Valor de tu cartera»");
  expect(ruleLine({ ...RULE, fact: "deposit", anchor: "Has aportado" })).toBe("Una aportación, tras «Has aportado»");
});

test("una prueba enseña el importe, o por qué no lo entiende", () => {
  expect(trialLine({ on: "2026-09-01", subject: "x", amount: "8410.25", problem: null })).toMatch(/8410,25|8\.410,25/);
  expect(trialLine({ on: null, subject: "x", amount: null, problem: "no aparece 'Valor'" })).toBe(
    "No lo entiende: no aparece 'Valor'",
  );
});

test("una regla sin lo que necesita no se prueba ni se guarda", () => {
  expect(ruleProblem(RULE)).toBeNull();
  expect(ruleProblem({ ...RULE, entity: " " })).toBe("Falta la entidad.");
  expect(ruleProblem({ ...RULE, sender: "@" })).toContain("remitente");
  expect(ruleProblem({ ...RULE, anchor: "" })).toContain("antes del importe");
});
