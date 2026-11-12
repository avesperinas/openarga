import { describe, expect, it } from "vitest";

import { contract, delta, signedPercent } from "./analysisParts";
import { atEnd, bounds, defaults, fromSearch, periodTitle, pickable, previousLabel, step, toSearch } from "./analysisState";
import { fromLink } from "./filters";

const today = new Date(2026, 9, 1);
const base = defaults(today);

describe("el periodo de Análisis", () => {
  it("cada clase de periodo abarca sus días", () => {
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

  it("las flechas van de mes, de trimestre o de año, y no pasan de hoy", () => {
    expect(step({ ...base, kind: "quarter", at: "2026-08" }, -1).at).toBe("2026-05");
    expect(step({ ...base, kind: "year", at: "2026-01" }, 1).at).toBe("2027-01");
    expect(step({ ...base, kind: "month", at: "2026-01" }, -1).at).toBe("2025-12");
    expect(atEnd({ ...base, kind: "month", at: "2026-10" }, today)).toBe(true);
    expect(atEnd({ ...base, kind: "month", at: "2026-09" }, today)).toBe(false);
  });

  it("su título se lee", () => {
    expect(periodTitle({ ...base, kind: "month", at: "2026-09" }, 2021, today)).toBe("Septiembre 2026");
    expect(periodTitle({ ...base, kind: "quarter", at: "2026-08" }, 2021, today)).toBe("3.er trimestre 2026");
    expect(periodTitle({ ...base, kind: "last12", at: "2026-09" }, 2021, today)).toBe("Oct 2025 – Sep 2026");
    expect(previousLabel("year")).toBe("el año anterior");
  });
});

describe("la dirección", () => {
  it("lo elegido va y vuelve, y lo de por defecto no se escribe", () => {
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
    expect(search).toContain("vista=flujo");
    expect(search).toContain("vivienda=si");
    expect(search).toContain("en=porcentaje");
    expect(search).toContain("alquiler=gasto");
    expect(fromSearch(search, today)).toEqual(chosen);
  });

  it("los tipos de producto y las cuentas elegidas van y vuelven", () => {
    const chosen = { ...base, view: "invest" as const, groups: ["Fondos", "Pensión"], accounts: ["fondo-a"] };
    const search = toSearch(chosen, today);
    expect(search).toContain("producto=Fondos&producto=Pensi%C3%B3n");
    expect(search).toContain("cuenta=fondo-a");
    expect(fromSearch(search, today)).toEqual(chosen);
  });

  it("lo que no se entiende vuelve al valor por defecto", () => {
    expect(fromSearch("?vista=nada&mes=2026-13&periodo=x", today)).toEqual(base);
  });

  it("desde Análisis, Movimientos abre el mes y la categoría", () => {
    const link = fromLink("?desde=2026-09-01&hasta=2026-09-30&categoria=abc");
    expect(link?.period).toEqual({ kind: "month", year: 2026, month: 9 });
    expect(link?.filters.categories).toEqual(["abc"]);
    const long = fromLink("?desde=2021-01-01&hasta=2026-09-30");
    expect(long?.period).toEqual({ kind: "range", from: "2025-10-01", to: "2026-09-30" });
    expect(fromLink("")).toBeNull();
  });
});

describe("las comparaciones", () => {
  it("con signo, con tono según lo que es bueno, y en buen castellano", () => {
    const up = delta(1100, 1000, "el mes anterior");
    expect(up.text.replace(/\s/g, " ")).toBe("+100 € (+10 %) frente al mes anterior");
    expect(up.tone).toBe("positive");
    expect(delta(1100, 1000, "el mes anterior", false).tone).toBe("negative");
    expect(delta(500, 0, "el mes anterior").text).toBe("Sin dato del mes anterior");
    expect(contract("frente a el 30/09/2025")).toBe("frente al 30/09/2025");
    expect(signedPercent(-0.0831)).toBe("−8,3 %");
    expect(signedPercent(null)).toBe("—");
  });
});

describe("los tipos y las cuentas que se pueden elegir", () => {
  const accounts = [
    { key: "nomina", name: "Nómina", group: "Efectivo", asset_class: "cash" },
    { key: "fondo", name: "Fondo", group: "Fondos", asset_class: "investment" },
    { key: "plan", name: "Plan", group: "Pensión", asset_class: "investment" },
    { key: "piso", name: "Piso", group: "Vivienda", asset_class: "real_estate" },
  ];

  it("en Patrimonio, todas; en Inversión, solo los productos; la vivienda, solo si entra", () => {
    expect(pickable(accounts, "worth", false, []).groups).toEqual(["Efectivo", "Fondos", "Pensión"]);
    expect(pickable(accounts, "invest", false, []).groups).toEqual(["Fondos", "Pensión"]);
    expect(pickable(accounts, "invest", true, []).groups).toEqual(["Fondos", "Pensión", "Vivienda"]);
  });

  it("con tipos elegidos, solo las cuentas de esos tipos", () => {
    expect(pickable(accounts, "worth", false, ["Fondos"]).accounts).toEqual([{ value: "fondo", label: "Fondo" }]);
  });
});
