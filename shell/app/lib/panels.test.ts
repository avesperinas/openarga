import { describe, expect, it } from "vitest";

import { AREA_APPS, type Contributor, groupPanelPages, panelAreaOf, panelEntries, placedAreas, withPanelPages, ask, compose, hidePanel, movePanel, orderOf, plain, showPanel, shownAreas, splitActing, toneOf } from "./panels";

const planner: Contributor = {
  source: "planner",
  name: "Planner",
  panel: {
    area: "day",
    order: 10,
    headlines: [{ text: "Dentista a las 17:00", priority: 40 }],
    tabs: [{ id: "hoy", label: "Agenda", blocks: [{ type: "figure", label: "Ahora", value: "Libre" }] }],
    questions: [{ text: "¿Qué tengo hoy?", words: ["agenda", "hoy", "citas"], tab: "hoy" }],
  },
};

const goals: Contributor = {
  source: "goals",
  name: "KPIs",
  panel: {
    area: "day",
    order: 20,
    headlines: [{ text: "Tienes 2 tareas vencidas", tone: "warning", priority: 60 }],
    tabs: [
      {
        id: "tareas",
        label: "Tareas",
        blocks: [{ type: "tasks", widget: "today", items: [], add: "Añadir" }],
      },
    ],
    questions: [{ text: "¿Qué tengo que hacer?", words: ["tareas", "pendiente"], tab: "tareas" }],
  },
};

const study: Contributor = {
  source: "study",
  name: "Study",
  panel: {
    area: "work",
    tabs: [
      {
        id: "vacaciones",
        label: "Vacaciones",
        blocks: [
          { type: "rings", items: [] },
          { type: "figure", label: "Vacaciones", value: "11 de 23 días" },
        ],
      },
    ],
    questions: [{ text: "¿Cuántas vacaciones me quedan?", words: ["vacaciones", "dias libres"], tab: "vacaciones", block: 1 }],
  },
};

describe("compose", () => {
  it("junta las apps de un área: la frase más importante manda y las pestañas van en su orden", () => {
    const day = compose([goals, planner])[0]!;
    expect(day.key).toBe("day");
    expect(day.apps).toBe("Planner · KPIs");
    expect(day.headline?.text).toBe("Tienes 2 tareas vencidas");
    expect(toneOf(day)).toBe("warning");
    expect(day.tabs.map((tab) => tab.id)).toEqual(["planner.hoy", "goals.tareas"]);
  });

  it("las casillas llevan su app delante, para que tachar vaya a la suya", () => {
    const block = compose([goals])[0]!.tabs[0]!.blocks[0]!;
    expect(block.type === "tasks" && block.widget).toBe("goals/today");
    expect(splitActing("goals/today")).toEqual({ source: "goals", widget: "today" });
  });

  it("sigue el orden del dueño, esconde las que quitó y deja fuera las que no tienen nada", () => {
    expect(compose([planner, study], { order: ["work", "day"] }).map((area) => area.key)).toEqual(["work", "day"]);
    expect(compose([planner, study], { hidden: ["day"] }).map((area) => area.key)).toEqual(["work"]);
    expect(compose([]).length).toBe(0);
  });

  it("el orden guardado se completa con el de siempre y olvida lo que no es un área", () => {
    expect(orderOf(["mind", "nada", "day"])).toEqual(["mind", "day", "money", "health", "work", "home", "leisure"]);
  });
});

describe("ask", () => {
  const areas = compose([planner, goals, study]);

  it("contesta sin tildes ni mayúsculas, con el bloque que responde", () => {
    const first = ask(areas, "Vacaciónes")[0]!;
    expect(first.area).toBe("work");
    expect(first.tab).toBe("study.vacaciones");
    expect(first.block).toEqual({ type: "figure", label: "Vacaciones", value: "11 de 23 días" });
  });

  it("por el principio de una palabra, y con dos letras como mínimo", () => {
    expect(ask(areas, "tare").map((answer) => answer.tab)).toEqual(["goals.tareas"]);
    expect(ask(areas, "t")).toEqual([]);
    expect(ask(areas, "hipoteca")).toEqual([]);
  });

  it("plain quita tildes y mayúsculas", () => {
    expect(plain("  ¿Cuántas Vacaciones? ")).toBe("¿cuantas vacaciones?");
  });
});

describe("qué paneles tienes puestos", () => {
  it("sin elegir, los de partida; con tu elección, los tuyos en tu orden", () => {
    expect(shownAreas()).toEqual(["day", "money", "health"]);
    expect(shownAreas({ order: ["work", "day"], hidden: ["money", "health", "home", "leisure", "mind"] })).toEqual(["work", "day"]);
  });

  it("poner uno lo deja el último; quitarlo lo esconde; moverlo cambia su sitio entre los que ves", () => {
    const added = showPanel(undefined, "work");
    expect(shownAreas(added)).toEqual(["day", "money", "health", "work"]);
    expect(shownAreas(hidePanel(added, "money"))).toEqual(["day", "health", "work"]);
    expect(shownAreas(movePanel(added, "work", -1))).toEqual(["day", "money", "work", "health"]);
    expect(shownAreas(movePanel(added, "day", -1))).toEqual(["day", "money", "health", "work"]);
  });

  it("each area asks only its own apps, and no app is in two", () => {
    expect(AREA_APPS.work).toContain("study");
    const all = Object.values(AREA_APPS).flat();
    expect(new Set(all).size).toBe(all.length);
  });
});

describe("los paneles como widgets", () => {
  it("cada área da dos: el panel entero, alto, y una pestaña suelta que se elige al ponerla", () => {
    const money = panelEntries().filter((entry) => entry.id.startsWith("money"));
    expect(money.map((entry) => [entry.id, entry.sizes[0], entry.option?.endpoint ?? null])).toEqual([
      ["money", "4x6", null],
      ["money.tab", "2x2", "/panels/choices?area=money"],
    ]);
  });

  it("de un widget se sabe su área, y de un escritorio, las áreas que hay que pedir", () => {
    expect(panelAreaOf({ source: "panel", widget: "work.tab" })).toBe("work");
    expect(panelAreaOf({ source: "money", widget: "money" })).toBeNull();
    expect(panelAreaOf({ source: "panel", widget: "nada" })).toBeNull();
    const pages = [
      { items: [{ source: "panel", widget: "day" }, { source: "vitals", widget: "weight" }] },
      { items: [{ source: "panel", widget: "day.tab" }, { source: "panel", widget: "work" }] },
    ];
    expect(placedAreas(pages)).toEqual(["day", "work"]);
  });
});

describe("la pasada de las páginas de panel a widgets", () => {
  const widgets = { id: "w", items: [{ instance_id: "a", source: "vitals", widget: "weight", size: "2x2" as const }] };
  let n = 0;
  const id = () => `id-${++n}`;

  it("los paneles de antes pasan a pantallas con su panel entero, delante y en su orden", () => {
    const desk = withPanelPages({ pages: [widgets] }, ["day", "money"], id);
    expect(desk.pages.map((page) => page.id)).toEqual(["panel-day", "panel-money", "w"]);
    expect(desk.pages[0]!.items[0]).toMatchObject({ source: "panel", widget: "day", size: "4x6" });
  });

  it("si ya hay algún panel puesto, no toca nada", () => {
    const placed = { pages: [{ id: "x", items: [{ instance_id: "p", source: "panel", widget: "work", size: "4x6" as const }] }] };
    expect(withPanelPages(placed, ["day"], id)).toBe(placed);
  });
});

describe("en el ordenador, varios paneles juntos", () => {
  const panel = (area: string, id = area) => ({ instance_id: id, source: "panel", widget: area, size: "4x6" as const });
  const single = (area: string) => ({ id: `panel-${area}`, items: [panel(area)] });
  const widgets = { id: "w", items: [{ instance_id: "a", source: "vitals", widget: "weight", size: "2x2" as const }] };

  it("la pasada en el ordenador pone tres paneles por pantalla", () => {
    let n = 0;
    const desk = withPanelPages({ pages: [widgets] }, ["day", "money", "health", "work"], () => `i${++n}`, 3);
    expect(desk.pages.map((page) => [page.id, page.items.map((item) => item.widget)])).toEqual([
      ["panel-day", ["day", "money", "health"]],
      ["panel-work", ["work"]],
      ["w", ["weight"]],
    ]);
  });

  it("las pantallas de un solo panel que dejó la pasada se juntan de tres en tres, y nada más", () => {
    const before = { pages: [single("day"), single("money"), single("health"), single("work"), widgets] };
    const after = groupPanelPages(before);
    expect(after.pages.map((page) => [page.id, page.items.map((item) => item.widget)])).toEqual([
      ["panel-day", ["day", "money", "health"]],
      ["panel-work", ["work", "weight"]],
    ]);
    expect(groupPanelPages(after)).toBe(after);
  });

  it("lo que tocaste tú no se mueve: una pantalla con widgets o con otro nombre corta el grupo", () => {
    const touched = { id: "panel-money", items: [panel("money"), { instance_id: "x", source: "money", widget: "cash", size: "2x2" as const }] };
    const mine = { id: "1b2c", items: [panel("work")] };
    const desk = { pages: [single("day"), touched, mine, single("health")] };
    expect(groupPanelPages(desk)).toBe(desk);
  });
});

describe("lo que no cabe junto al último panel", () => {
  it("si los widgets de después no caben en el hueco, se quedan en su pantalla", () => {
    const many = { id: "w", items: Array.from({ length: 4 }, (_, i) => ({ instance_id: `k${i}`, source: "vitals", widget: `w${i}`, size: "4x4" as const })) };
    const single = (area: string) => ({ id: `panel-${area}`, items: [{ instance_id: area, source: "panel", widget: area, size: "4x6" as const }] });
    const after = groupPanelPages({ pages: [single("day"), single("money"), many] });
    expect(after.pages.map((page) => page.id)).toEqual(["panel-day", "w"]);
  });
});
