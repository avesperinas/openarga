import { configureRegional } from "@openarga/ui";
import { beforeAll } from "vitest";

import { statementLine } from "./Statements";

beforeAll(() => configureRegional({ locale: "en-GB" }));

test("each page says what it understood and how much was new", () => {
  expect(
    statementLine({
      file: "renault.html",
      entity: "Renault Bank",
      accounts: ["Current account"],
      movements: 3,
      balances: 1,
      new: 2,
    }),
  ).toBe("Renault Bank · Current account · 3 movements and 1 balance, 2 new");
  expect(statementLine({ file: "other.html", problem: "not a page that can be read" })).toBe(
    "not a page that can be read",
  );
  expect(statementLine({ file: "same.html", entity: "Finizens", accounts: [], balances: 3, new: 0 })).toBe(
    "Finizens · 3 balances, nothing new",
  );
});
