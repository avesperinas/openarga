import { describe, expect, it } from "vitest";

import { pathOf, route, type Route } from "./App";
import { groupOf, grouped, quickDates, whenLabel } from "./words";

const ID = "0a0a0a0a-0000-4000-8000-00000000a0a0";

describe("cada pantalla tiene su dirección", () => {
  const cases: [string, Route][] = [
    ["/goals/", { tab: "home" }],
    ["/goals/metas", { tab: "goals" }],
    [`/goals/meta/${ID}`, { tab: "goals", goal: ID }],
    [`/goals/tarea/${ID}`, { tab: "home", task: ID }],
    ["/goals/hechas", { tab: "done" }],
    ["/goals/categorias", { tab: "categories" }],
  ];
  it.each(cases)("%s", (path, expected) => {
    expect(route(path)).toEqual(expected);
    expect(pathOf(expected)).toBe(path);
  });

  it("lo desconocido lleva a la portada, que son las tareas", () => {
    expect(route("/goals/lo-que-sea")).toEqual({ tab: "home" });
  });

  it("`/tareas`, la dirección de antes, sigue abriendo las tareas", () => {
    expect(route("/goals/tareas")).toEqual({ tab: "home" });
  });
});

const TODAY = "2026-09-28";

describe("cuándo, dicho corto", () => {
  it.each([
    ["2026-09-28", null, "hoy"],
    ["2026-09-29", null, "mañana"],
    ["2026-09-27", null, "ayer"],
    ["2026-09-25", null, "hace 3 días"],
    ["2026-10-02", "18:30:00", "vie 2 · 18:30"],
    ["2026-10-14", null, "14 oct"],
    ["2027-01-05", null, "5 ene 2027"],
  ])("%s %s", (due_on, due_time, expected) => {
    expect(whenLabel({ due_on, due_time }, TODAY)).toBe(expected);
  });

  it("sin fecha no dice nada", () => {
    expect(whenLabel({ due_on: null, due_time: null }, TODAY)).toBeNull();
  });
});

describe("la portada por fecha", () => {
  it("agrupa en su orden y deja fuera los grupos vacíos", () => {
    const tasks = [
      { status: "upcoming" as const, due_on: "2026-10-20" },
      { status: "someday" as const, due_on: null },
      { status: "overdue" as const, due_on: "2026-09-26" },
      { status: "today" as const, due_on: "2026-09-28" },
      { status: "upcoming" as const, due_on: "2026-09-29" },
    ];
    expect(grouped(tasks, TODAY).map((group) => [group.id, group.tasks.length])).toEqual([
      ["overdue", 1],
      ["today", 1],
      ["tomorrow", 1],
      ["later", 1],
      ["someday", 1],
    ]);
  });

  it("lo de hoy con la hora pasada va con lo vencido, porque lo dice el servicio", () => {
    expect(groupOf({ status: "overdue", due_on: TODAY }, TODAY)).toBe("overdue");
  });

  it("dentro de una semana es la semana", () => {
    expect(groupOf({ status: "upcoming", due_on: "2026-10-05" }, TODAY)).toBe("week");
  });
});

describe("las fechas a un toque", () => {
  it("el sábado y el lunes son los siguientes a hoy", () => {
    const quick = Object.fromEntries(quickDates(TODAY).map((one) => [one.key, one.value]));
    expect(quick).toEqual({
      none: null,
      today: "2026-09-28",
      tomorrow: "2026-09-29",
      saturday: "2026-10-03",
      monday: "2026-10-05",
    });
  });
});

describe("el anillo de hoy en Tareas (T-B22)", () => {
  it("cuenta lo tachado hoy frente a lo que tocaba hoy, y avisa de lo vencido", async () => {
    const { todayRing } = await import("./Home");
    const task = (status: string, done_at: string | null = null) => ({ status, done_at }) as never;
    const today = "2026-11-02";
    const ring = todayRing(
      [task("overdue"), task("today"), task("someday")],
      [task("done", "2026-11-02T09:00:00Z"), task("done", "2026-11-01T09:00:00Z")],
      today,
    );
    expect(ring).toMatchObject({ value: "1/3", label: "hechas hoy", detail: "1 vencida · 3 pendientes en total", tone: "warning" });
    expect(ring.share).toBeCloseTo(1 / 3);
    expect(todayRing([task("someday")], [], today)).toMatchObject({ share: null, label: "Nada para hoy" });
  });
});
