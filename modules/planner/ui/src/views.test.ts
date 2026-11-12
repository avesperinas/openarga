import { describe, expect, it } from "vitest";

import { fetchWindow, monthOf, parsePlace, pathOf, scroll, step, switchView, titleOf, visibleDays } from "./views";

const TODAY = "2026-09-30";

describe("la dirección", () => {
  it("sin nada, la semana en el ordenador y tres días en el móvil, hoy", () => {
    expect(parsePlace("/planner", 1280, TODAY)).toEqual({ view: "week", day: TODAY });
    expect(parsePlace("/planner/", 390, TODAY)).toEqual({ view: "three", day: TODAY });
  });

  it("ida y vuelta de cada vista", () => {
    for (const place of [
      { view: "day", day: "2026-10-02" },
      { view: "three", day: "2026-10-02" },
      { view: "week", day: "2026-10-02" },
      { view: "month", day: "2026-10-01" },
      { view: "month", day: "2026-10-19" },
    ] as const) {
      expect(parsePlace(pathOf(place, TODAY), 1280, TODAY)).toEqual(place);
    }
    expect(pathOf({ view: "agenda", day: TODAY }, TODAY)).toBe("/planner/agenda");
    expect(pathOf({ view: "month", day: "2026-10-01" }, TODAY)).toBe("/planner/mes/2026-10");
    expect(pathOf({ view: "month", day: "2026-10-19" }, TODAY)).toBe("/planner/mes/2026-10-19");
  });
});

describe("los días de cada vista", () => {
  it("la semana va de lunes a domingo aunque el día sea un miércoles", () => {
    const days = visibleDays({ view: "week", day: TODAY });
    expect([days[0], days[6]]).toEqual(["2026-09-28", "2026-10-04"]);
  });

  it("el mes son seis semanas y la agenda sesenta días", () => {
    expect(visibleDays({ view: "month", day: "2026-09-01" })).toHaveLength(42);
    expect(visibleDays({ view: "agenda", day: TODAY })).toHaveLength(60);
  });

  it("un paso mide lo que mide la vista, salvo tres días, que va de día en día", () => {
    expect(step({ view: "three", day: TODAY }, 1).day).toBe("2026-10-01");
    expect(step({ view: "three", day: TODAY }, -2).day).toBe("2026-09-28");
    expect(step({ view: "week", day: TODAY }, -1).day).toBe("2026-09-21");
    expect(step({ view: "month", day: "2026-01-01" }, 1).day).toBe("2026-02-01");
  });

  it("el mes pasa semana a semana, y se ven juntas las de dos meses", () => {
    const october = { view: "month", day: "2026-10-01" } as const;
    expect(visibleDays(october)[0]).toBe("2026-09-28");
    const later = scroll(october, 3);
    expect(later.day).toBe("2026-10-19");
    expect([visibleDays(later)[0], visibleDays(later)[41]]).toEqual(["2026-10-19", "2026-11-29"]);
    expect(scroll(later, -3)).toEqual({ view: "month", day: "2026-09-28" });
  });

  it("el mes que manda es el de la mitad de lo que se ve, y de ahí parten las flechas", () => {
    expect(monthOf({ view: "month", day: "2026-10-01" })).toBe("2026-10");
    expect(monthOf({ view: "month", day: "2026-10-19" })).toBe("2026-11");
    expect(monthOf({ view: "month", day: "2026-10-05" })).toBe("2026-10");
    expect(step({ view: "month", day: "2026-10-19" }, 1).day).toBe("2026-12-01");
    expect(step({ view: "month", day: "2026-10-19" }, -1).day).toBe("2026-10-01");
    expect(titleOf({ view: "month", day: "2026-10-19" }).title).toBe("Noviembre 2026");
    expect(switchView({ view: "month", day: "2026-10-19" }, "week", TODAY)).toEqual({ view: "week", day: "2026-11-01" });
  });

  it("al pasar del mes a otra vista se va a hoy si es este mes", () => {
    expect(switchView({ view: "month", day: "2026-09-01" }, "day", TODAY)).toEqual({ view: "day", day: TODAY });
    expect(switchView({ view: "month", day: "2026-11-01" }, "week", TODAY)).toEqual({ view: "week", day: "2026-11-01" });
    expect(switchView({ view: "week", day: TODAY }, "month", TODAY)).toEqual({ view: "month", day: "2026-09-01" });
  });

  it("lo que se pide lleva un paso de margen a cada lado", () => {
    const { from, to } = fetchWindow({ view: "week", day: TODAY });
    expect(from.getDate()).toBe(21);
    expect(to.getDate()).toBe(12);
  });

  it("el mes pide meses enteros: pasar una semana no pide nada nuevo", () => {
    const window = fetchWindow({ view: "month", day: "2026-10-01" });
    expect([window.from.getMonth(), window.from.getDate(), window.to.getMonth(), window.to.getDate()]).toEqual([8, 1, 11, 1]);
    expect(fetchWindow({ view: "month", day: "2026-10-05" })).toEqual(window);
  });
});

describe("el título", () => {
  it("un mes, dos meses y un día", () => {
    expect(titleOf({ view: "week", day: "2026-09-14" })).toEqual({ title: "Septiembre 2026", week: 38 });
    expect(titleOf({ view: "week", day: TODAY }).title).toBe("Sept – oct 2026");
    expect(titleOf({ view: "day", day: TODAY }).title).toBe("Miércoles, 30 de septiembre");
    expect(titleOf({ view: "three", day: "2026-12-30" }).title).toBe("Dic 2026 – ene 2027");
  });
});
