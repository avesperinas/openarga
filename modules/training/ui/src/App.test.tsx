import { renderToString } from "react-dom/server";

import { route } from "./App";
import { TodayScreen } from "./Today";
import type { Today } from "./api";
import { todayLabel } from "./today";

const SETTINGS = { weekly_goal: 5, unit: "kg", default_increments: {} };

const WEEK = { done: 2, goal: 5, monday: "2026-09-14" };

const WITH_PLAN: Today = {
  settings: SETTINGS,
  week: WEEK,
  in_progress: null,
  next: {
    plan_day_id: "d2",
    name: "Pull",
    kind: "pull",
    rotation_number: 3,
    remaining: 2,
    days_in_rotation: 3,
  },
  plan: {
    plan_id: "p",
    name: "Push Pull Leg",
    version_id: "v",
    version: 1,
    valid_from: "2026-09-01",
    days: [
      { id: "d1", name: "Push", kind: "push", position: 1, slots: [] },
      {
        id: "d2",
        name: "Pull",
        kind: "pull",
        position: 2,
        slots: [
          {
            id: "s",
            position: 1,
            exercise: "Remo",
            target_sets: 4,
            rep_min: 6,
            rep_max: 10,
            allow_both: false,
            options: [],
          },
        ],
      },
    ],
  },
};

describe("Hoy", () => {
  it("sin plan dice por qué está vacía en vez de enseñar un hueco", () => {
    const html = renderToString(
      <TodayScreen onOpenSession={() => undefined} onOpenPlan={() => undefined} now={new Date(2026, 8, 15)} initial={{
        status: "ready",
        today: { plan: null, settings: SETTINGS, next: null, in_progress: null, week: WEEK },
      }} />,
    );

    expect(html).toContain("Todavía no hay plan");
    expect(html).toContain("Crear el plan");
  });

  it("enseña la siguiente sesión y la semana contra el objetivo", () => {
    const html = renderToString(<TodayScreen onOpenSession={() => undefined} initial={{ status: "ready", today: WITH_PLAN }} />).replaceAll(
      "<!-- -->",
      "",
    );

    expect(html).toMatch(/Toca ·\s*rotación 3, día 2 de 3/);
    expect(html).toContain("Empezar Pull");
    expect(html).not.toContain("¿Empezar Pull?");
    expect(html).toContain("Esta semana");
    expect(html).toMatch(/class="hint">\d+ de 5 · este mes/);
    expect(html).toMatch(/class="goal-week" role="img" aria-label="Esta semana: L, /);
  });

  it("si la API falla lo dice, y el resto de la pantalla sigue ahí", () => {
    const html = renderToString(<TodayScreen onOpenSession={() => undefined} initial={{ status: "error" }} />);

    expect(html).toContain("No se ha podido cargar");
    expect(html).toContain("Calendario");
  });

  it("sin plan ni histórico ya se ven el calendario, la semana, el mes y lo último", () => {
    const html = renderToString(
      <TodayScreen
        onOpenSession={() => undefined}
        now={new Date(2026, 8, 16)}
        initialSessions={[]}
        initial={{
          status: "ready",
          today: { plan: null, settings: SETTINGS, next: null, in_progress: null, week: WEEK },
        }}
      />,
    ).replaceAll("<!-- -->", "");

    for (const title of ["Esta semana", "Calendario", "Últimos entrenos", "Actividades"]) {
      expect(html).toMatch(new RegExp(`>${title}(<span[^>]*>[^<]*</span>)?</h2>`));
    }
    expect(html).toContain("este mes, 0 sesiones");
    expect(html).toContain("Septiembre de 2026");
    expect(html).toContain("Todavía no hay entrenos");
    expect(html).toContain(">Anotar<");
  });

  it("la fecha va como en el escritorio de arga", () => {
    expect(todayLabel(new Date(2026, 8, 15))).toBe("Martes, 15 de septiembre");
  });
});

describe("Hoy con una sesión a medias", () => {
  it("ofrece continuarla en vez de empezar otra", () => {
    const html = renderToString(
      <TodayScreen
        onOpenSession={() => undefined}
        initial={{ status: "ready", today: { ...WITH_PLAN, in_progress: "s1" } }}
      />,
    ).replaceAll("<!-- -->", "");

    expect(html).toContain("Continuar entreno");
    expect(html).not.toContain("Empezar Pull");
  });
});

describe("rutas", () => {
  it("la sesión tiene su dirección, para recargar a mitad sin perderla", () => {
    expect(route("/training/sesion/5b0e8f7e-4c1a-4d53-9a53-0d3f0c1e2a11")).toEqual({
      screen: "session",
      id: "5b0e8f7e-4c1a-4d53-9a53-0d3f0c1e2a11",
    });
    expect(route("/training/")).toEqual({ screen: "today" });
    expect(route("/training/sesion/otra-cosa")).toEqual({ screen: "today" });
  });
});

describe("Hoy recomienda y deja elegir", () => {
  it("con la rotación empezada, se puede empezar otro día que no toca (T-B05)", () => {
    const today: Today = {
      ...WITH_PLAN,
      rotation: {
        number: 3,
        open: true,
        days: [
          { plan_day_id: "d1", name: "Push", kind: "push", done: true },
          { plan_day_id: "d2", name: "Pull", kind: "pull", done: false },
        ],
      },
    };
    const html = renderToString(
      <TodayScreen onOpenSession={() => undefined} initial={{ status: "ready", today }} />,
    ).replaceAll("<!-- -->", "");

    expect(html).toContain("Empezar Pull");
    expect(html).toContain(">Otro día<");
  });
});

describe("las pestañas tienen dirección", () => {
  it("calendario y plan", () => {
    expect(route("/training/calendario")).toEqual({ screen: "history" });
    expect(route("/training/plan/")).toEqual({ screen: "plan" });
    expect(route("/training/siguiente")).toEqual({ screen: "next" });
  });
});
