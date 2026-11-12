import { describe, expect, it } from "vitest";

import { addDays, categoryOf, dateRange, daysBetween, daysRange, euros, flag, mapsLink, monthsLabel, nights } from "./words";
import { route, pathOf } from "./App";
import { nightsByMonth } from "./Stats";

describe("cómo se dice", () => {
  it("las fechas de un viaje, sin repetir lo que comparten", () => {
    expect(dateRange("2025-03-07", "2025-03-09")).toBe("7–9 mar 2025");
    expect(dateRange("2025-02-28", "2025-03-03")).toBe("28 feb – 3 mar 2025");
    expect(dateRange("2024-12-30", "2025-01-02")).toBe("30 dic 2024 – 2 ene 2025");
  });

  it("las noches, en singular y en plural", () => {
    expect(nights(1)).toBe("1 noche");
    expect(nights(3)).toBe("3 noches");
  });

  it("la bandera sale del código y un código raro no pinta nada", () => {
    expect(flag("BE")).toBe("🇧🇪");
    expect(flag(null)).toBe("");
    expect(flag("be")).toBe("");
  });

  it("euros sin céntimos y días entre fechas", () => {
    expect(euros(1234.4)).toMatch(/1234|1\.234/);
    expect(daysBetween("2025-03-07", "2025-03-09")).toBe(2);
    expect(addDays("2025-02-28", 1)).toBe("2025-03-01");
  });
});

describe("las direcciones", () => {
  const ID = "3f0c2a5e-9a6b-4d51-9c3e-0d9a1b2c3d4e";

  it("cada pantalla tiene la suya y vuelve a ser la misma", () => {
    for (const to of [
      { screen: "map" },
      { screen: "trips" },
      { screen: "journey" },
      { screen: "trip", id: ID },
      { screen: "edit", id: ID },
      { screen: "edit", id: null },
      { screen: "stats" },
    ] as const) {
      expect(route(pathOf(to))).toEqual(to);
    }
  });

  it("lo que no se reconoce es el mapa", () => {
    expect(route("/travel/lo-que-sea")).toEqual({ screen: "map" });
  });
});

describe("el calendario de noches", () => {
  it("cuenta las noches de cada mes de cada año, el año más reciente arriba", () => {
    const months = nightsByMonth({ "2024-04-10": 1, "2024-04-11": 1, "2025-01-31": 1 });
    expect([...months.keys()]).toEqual([2025, 2024]);
    expect(months.get(2024)![3]).toBe(2);
    expect(months.get(2025)![0]).toBe(1);
  });
});

describe("las ideas", () => {
  it("los meses seguidos van juntos y los días, de tantos a tantos", () => {
    expect(monthsLabel([10, 4, 5, 6])).toBe("abr–jun, oct");
    expect(monthsLabel([12])).toBe("dic");
    expect(daysRange(4, 6)).toBe("4–6 días");
    expect(daysRange(null, 1)).toBe("1 día");
    expect(daysRange(null, null)).toBeNull();
  });
});

describe("tipos de sitio", () => {
  it("un sitio sin tipo se enseña como otro", () => {
    expect(categoryOf({ category: "beach" }).icon).toBe("umbrella");
    expect(categoryOf({ category: null }).label).toBe("Otro");
    expect(categoryOf(null).label).toBe("Otro");
  });

  it("en el iPhone abre Apple Maps y en lo demás Google Maps", () => {
    expect(mapsLink(47.507, 19.0456, "Parlamento", true)).toBe(
      "https://maps.apple.com/?ll=47.507000,19.045600&q=Parlamento",
    );
    expect(mapsLink(47.507, 19.0456, "Parlamento", false)).toContain("google.com/maps/search");
  });
});

describe("las secciones de un viaje", () => {
  const id = "3abfed4f-8cde-44ad-b81a-d0039f5a2ba6";
  it("cada una tiene su dirección, de ida y de vuelta", () => {
    for (const screen of ["trip", "days", "tripmap", "bookings", "money", "notes"] as const) {
      expect(route(pathOf({ screen, id }))).toEqual({ screen, id });
    }
  });
});
