import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { configureRegional } from "@openarga/ui";

import { contract, delta, signedPercent } from "./analysisParts";
import { atEnd, bounds, defaults, fromSearch, periodTitle, pickable, previousLabel, step, toSearch } from "./analysisState";
import { fromLink } from "./filters";

const today = new Date(2026, 9, 1);
const base = defaults(today);

beforeAll(() => configureRegional({ locale: "en-GB", timeZone: "Europe/Madrid", currency: "EUR" }));
afterAll(() => configureRegional({ locale: "es-ES", timeZone: "Europe/Madrid", currency: "EUR" }));

describe("the Analysis period", () => {
  it("each kind of period spans its days", () => {
    expect(bounds({ ...base, kind: "month", at: "2026-02" }, 2021, today)).toEqual({ from: "2026-02-01", to: "2026-02-28" });
    expect(bounds({ ...base, kind: "quarter", at: "2026-08" }, 2021, today)).toEqual({ from: "2026-07-01", to: "2026-09-30" });
    expect(bounds({ ...base, kind: "year", at: "2025-05" }, 2021, today)).toEqual({ from: "2025-01-01", to: "2025-12-31" });
    expect(bounds({ ...base, kind: "last12", at: "2026-09" }, 2021, today)).toEqual({ from: "2025-10-01", to: "2026-09-30" });
    expect(bounds({ ...base, kind: "range", from: "2026-03-10", to: "2026-01-05" }, 2021, today)).toEqual({
      from: "2026-01-05",
      to: "2026-03-10",
    });
    expect(bounds({ ...base, kind: "all" }, 2021, today)).toEqual({ from: "2021-01-01", to: "2026-10-01" });
  });

  it("the arrows move by month, quarter or year, and stop at today", () => {
    expect(step({ ...base, kind: "quarter", at: "2026-08" }, -1).at).toBe("2026-05");
    expect(step({ ...base, kind: "year", at: "2026-01" }, 1).at).toBe("2027-01");
    expect(step({ ...base, kind: "month", at: "2026-01" }, -1).at).toBe("2025-12");
    expect(atEnd({ ...base, kind: "month", at: "2026-10" }, today)).toBe(true);
    expect(atEnd({ ...base, kind: "month", at: "2026-09" }, today)).toBe(false);
  });

  it("its title reads well", () => {
    expect(periodTitle({ ...base, kind: "month", at: "2026-09" }, 2021, today)).toBe("September 2026");
    expect(periodTitle({ ...base, kind: "quarter", at: "2026-08" }, 2021, today)).toBe("Q3 2026");
    expect(periodTitle({ ...base, kind: "last12", at: "2026-09" }, 2021, today)).toBe("Oct 2025 – Sept 2026");
    expect(periodTitle({ ...base, kind: "all" }, 2021, today)).toBe("Since 2021");
    expect(previousLabel("year")).toBe("the previous year");
  });
});

describe("the address", () => {
  it("what is chosen goes and comes back, and the defaults are not written", () => {
    expect(toSearch(base, today)).toBe("");
    const chosen = {
      ...base,
      view: "flow" as const,
      kind: "last12" as const,
      at: "2026-08",
      whole: true,
      cycle: false,
      home: true,
      percent: true,
      rent: false,
    };
    const search = toSearch(chosen, today);
    expect(search).toContain("view=flow");
    expect(search).toContain("home=yes");
    expect(search).toContain("as=percent");
    expect(search).toContain("rent=expense");
    expect(fromSearch(search, today)).toEqual(chosen);
  });

  it("the chosen product types and accounts go and come back", () => {
    const chosen = { ...base, view: "invest" as const, groups: ["Funds", "Pension"], accounts: ["fund-a"] };
    const search = toSearch(chosen, today);
    expect(search).toContain("product=Funds&product=Pension");
    expect(search).toContain("account=fund-a");
    expect(fromSearch(search, today)).toEqual(chosen);
  });

  it("what is not understood goes back to the default", () => {
    expect(fromSearch("?view=nothing&month=2026-13&period=x", today)).toEqual(base);
  });

  it("from Analysis, Movements opens the month and the category", () => {
    const link = fromLink("?from=2026-09-01&to=2026-09-30&category=abc");
    expect(link?.period).toEqual({ kind: "month", year: 2026, month: 9 });
    expect(link?.filters.categories).toEqual(["abc"]);
    const long = fromLink("?from=2021-01-01&to=2026-09-30");
    expect(long?.period).toEqual({ kind: "range", from: "2025-10-01", to: "2026-09-30" });
    expect(fromLink("")).toBeNull();
  });
});

describe("the comparisons", () => {
  it("signed, with a tone by what is good, in the person's language", () => {
    const up = delta(1100, 1000, "the previous month");
    expect(up.text.replace(/\s/g, " ")).toBe("+€100 (+10%) against the previous month");
    expect(up.tone).toBe("positive");
    expect(delta(1100, 1000, "the previous month", false).tone).toBe("negative");
    expect(delta(500, 0, "the previous month").text).toBe("No data for the previous month");
    expect(signedPercent(-0.0831)).toBe("−8.3%");
    expect(signedPercent(null)).toBe("—");
  });

  it("in Spanish, “a el” and “de el” contract", () => {
    configureRegional({ locale: "es-ES" });
    try {
      expect(delta(500, 0, "el mes anterior").text).toBe("Sin dato del mes anterior");
      expect(contract("frente a el 30/09/2025")).toBe("frente al 30/09/2025");
    } finally {
      configureRegional({ locale: "en-GB" });
    }
  });
});

describe("the types and accounts that can be picked", () => {
  const accounts = [
    { key: "payroll", name: "Payroll", group: "Cash", asset_class: "cash" },
    { key: "fund", name: "Fund", group: "Funds", asset_class: "investment" },
    { key: "plan", name: "Plan", group: "Pension", asset_class: "investment" },
    { key: "flat", name: "Flat", group: "Property", asset_class: "real_estate" },
  ];

  it("in Net worth, all; in Investment, only products; the home, only if included", () => {
    expect(pickable(accounts, "worth", false, []).groups).toEqual(["Cash", "Funds", "Pension"]);
    expect(pickable(accounts, "invest", false, []).groups).toEqual(["Funds", "Pension"]);
    expect(pickable(accounts, "invest", true, []).groups).toEqual(["Funds", "Pension", "Property"]);
  });

  it("with types chosen, only the accounts of those types", () => {
    expect(pickable(accounts, "worth", false, ["Funds"]).accounts).toEqual([{ value: "fund", label: "Fund" }]);
  });
});
